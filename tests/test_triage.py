"""
Triage agent tests — LLM + LLM-as-judge.

Each test runs the real triage agent on a dummy message and uses a second
LLM call (the judge) to verify the classification is correct.
"""
import pytest
from tests.conftest import requires_llm
from tests.fixtures.messages import (
    RECRUITER_EMAIL,
    TASK_EMAIL,
    NEWSLETTER_EMAIL,
    URGENT_EMAIL,
    SLACK_MESSAGE,
)
from app.agents.triage import triage_node

pytestmark = [pytest.mark.integration, requires_llm()]


def _make_state(msg: dict) -> dict:
    return {"raw_event": msg, "normalized_message": msg}


# ── Classification correctness ────────────────────────────────────────────────

class TestTriageClassification:
    """Deterministic assertions on classification fields — no judge needed."""

    async def test_recruiter_email_is_high_priority(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]
        assert clf["priority"] in ("high", "medium"), (
            f"Recruiter email should be high/medium priority, got: {clf['priority']}"
        )

    async def test_recruiter_email_is_meeting_category(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]
        assert clf["category"] == "meeting", (
            f"Recruiter email with slot request should be 'meeting', got: {clf['category']}"
        )

    async def test_recruiter_email_needs_research(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]
        assert clf["needs_research"] is True, (
            "Recruiter email from Meta should trigger research (unfamiliar company/comp data)"
        )

    async def test_recruiter_email_needs_draft(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]
        assert clf["needs_draft"] is True, "Recruiter expects a reply"

    async def test_task_email_category(self):
        result = await triage_node(_make_state(TASK_EMAIL))
        clf = result["classification"]
        assert clf["category"] in ("task", "urgent"), (
            f"Email with explicit action items should be 'task', got: {clf['category']}"
        )

    async def test_task_email_is_high_priority(self):
        result = await triage_node(_make_state(TASK_EMAIL))
        clf = result["classification"]
        assert clf["priority"] in ("high", "medium"), (
            "Task email from manager with deadlines should be at least medium priority"
        )

    async def test_newsletter_is_low_priority(self):
        result = await triage_node(_make_state(NEWSLETTER_EMAIL))
        clf = result["classification"]
        assert clf["priority"] == "low", (
            f"Newsletter should be low priority, got: {clf['priority']}"
        )

    async def test_newsletter_is_informational(self):
        result = await triage_node(_make_state(NEWSLETTER_EMAIL))
        clf = result["classification"]
        assert clf["category"] == "informational", (
            f"Newsletter should be informational, got: {clf['category']}"
        )

    async def test_newsletter_no_draft_needed(self):
        result = await triage_node(_make_state(NEWSLETTER_EMAIL))
        clf = result["classification"]
        assert clf["needs_draft"] is False, "Newsletter does not require a reply"

    async def test_urgent_email_is_high_priority(self):
        result = await triage_node(_make_state(URGENT_EMAIL))
        clf = result["classification"]
        assert clf["priority"] == "high", (
            "Production outage email must be high priority"
        )

    async def test_db_message_id_set(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        assert result.get("db_message_id") is not None, (
            "triage_node must set db_message_id after saving to DB"
        )

    async def test_classification_has_required_keys(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]
        for key in ("is_work_related", "priority", "category", "needs_research", "needs_draft", "reasoning"):
            assert key in clf, f"Missing classification key: {key}"

    async def test_recruiter_email_is_work_related(self):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        assert result["classification"]["is_work_related"] is True

    async def test_newsletter_is_not_work_related(self):
        result = await triage_node(_make_state(NEWSLETTER_EMAIL))
        assert result["classification"]["is_work_related"] is False, (
            "A subscribed newsletter should not be treated as a work-related message"
        )

    async def test_urgent_email_is_work_related(self):
        result = await triage_node(_make_state(URGENT_EMAIL))
        assert result["classification"]["is_work_related"] is True


# ── LLM-as-judge quality evaluation ──────────────────────────────────────────

class TestTriageJudge:
    """Use a second LLM call to evaluate reasoning quality."""

    async def test_recruiter_classification_quality(self, judge):
        result = await triage_node(_make_state(RECRUITER_EMAIL))
        clf = result["classification"]

        verdict = await judge(
            output=str(clf),
            context=(
                "Input: Email from a Meta recruiter offering a Senior ML Engineer role, "
                "asking to schedule a 30-min intro call. Compensation mentioned."
            ),
            criteria=(
                "1. priority must be 'high' or 'medium' — recruiter outreach with scheduling ask is time-sensitive.\n"
                "2. category must be 'meeting' — there is a clear request to schedule a call.\n"
                "3. needs_research must be True — Meta is a major company worth researching; comp data is useful.\n"
                "4. needs_draft must be True — recruiter expects a reply.\n"
                "5. reasoning must be coherent and specific to the message content.\n"
                "Deduct points for wrong category, wrong priority, or missing research flag."
            ),
        )
        assert verdict.passed, (
            f"Triage quality score {verdict.score}/10 (need {7}+).\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )

    async def test_newsletter_classification_quality(self, judge):
        result = await triage_node(_make_state(NEWSLETTER_EMAIL))
        clf = result["classification"]

        verdict = await judge(
            output=str(clf),
            context="Input: A daily tech newsletter from TLDR — purely informational, no action required.",
            criteria=(
                "1. is_work_related must be False — a subscribed newsletter is not a professional communication.\n"
                "2. priority must be 'low' — newsletters are not urgent.\n"
                "3. category must be 'informational' — no action items, not a meeting, not a task.\n"
                "4. needs_draft must be False — no reply needed to a newsletter.\n"
                "5. needs_research should be False — newsletter is self-contained information.\n"
                "Give 0 if is_work_related is True. Heavily penalise anything that would interrupt the user."
            ),
        )
        assert verdict.passed, (
            f"Newsletter triage score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )

    async def test_urgent_classification_quality(self, judge):
        result = await triage_node(_make_state(URGENT_EMAIL))
        clf = result["classification"]

        verdict = await judge(
            output=str(clf),
            context=(
                "Input: Production outage email from the CTO. "
                "40% of users affected, ML service returning 500s, asking to join a war room call immediately."
            ),
            criteria=(
                "1. priority must be 'high' — production outage is the most urgent possible scenario.\n"
                "2. category should be 'urgent' or 'meeting' — there is an explicit join-the-call request.\n"
                "3. needs_draft must be True — a reply confirming availability is expected.\n"
                "4. reasoning must mention the severity/urgency of the situation.\n"
                "Give 0 if priority is not 'high'."
            ),
        )
        assert verdict.passed, (
            f"Urgent triage score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )
