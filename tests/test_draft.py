"""
Draft agent tests — LLM + LLM-as-judge.

Verifies draft generation: content relevance, tone, DB persistence, skip when not needed.
"""
import pytest
from tests.conftest import requires_llm
from tests.fixtures.messages import RECRUITER_EMAIL, NEWSLETTER_EMAIL, URGENT_EMAIL
from app.agents.draft import draft_node

pytestmark = [pytest.mark.integration, requires_llm()]


def _make_state(
    msg: dict,
    needs_draft: bool = True,
    priority: str = "high",
    category: str = "meeting",
    db_message_id: int | None = None,
    research: dict | None = None,
    meeting_options: list | None = None,
) -> dict:
    return {
        "normalized_message": msg,
        "classification": {
            "needs_draft": needs_draft,
            "priority": priority,
            "category": category,
        },
        "db_message_id": db_message_id,
        "research": research,
        "meeting_options": meeting_options or [],
    }


# ── Deterministic assertions ──────────────────────────────────────────────────

class TestDraftGeneration:
    async def test_draft_created_for_recruiter(self):
        result = await draft_node(_make_state(RECRUITER_EMAIL))
        assert result.get("draft"), "Draft should be non-empty for a recruiter email"
        assert len(result["draft"]) > 50, "Draft is suspiciously short"

    async def test_no_draft_when_not_needed(self):
        result = await draft_node(_make_state(NEWSLETTER_EMAIL, needs_draft=False))
        assert result == {}, "draft_node must return empty dict when needs_draft is False"

    async def test_draft_for_urgent_email(self):
        result = await draft_node(_make_state(URGENT_EMAIL))
        assert len(result.get("draft", "")) > 20, "Urgent email should produce a draft reply"

    async def test_draft_does_not_include_send_instruction(self):
        result = await draft_node(_make_state(RECRUITER_EMAIL))
        draft = result.get("draft", "").lower()
        assert "click send" not in draft
        assert "send this email" not in draft

    async def test_draft_persisted_to_db(self, test_db):
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.db.models import Draft, Message

        async with test_db() as session:
            msg_row = Message(
                source="gmail_work",
                thread_id="t-draft-001",
                sender="sarah.johnson@meta.com",
                subject="ML role at Meta",
                body="test body",
                received_at=datetime.now(timezone.utc),
                priority="high",
                category="meeting",
            )
            session.add(msg_row)
            await session.commit()
            await session.refresh(msg_row)
            db_id = msg_row.id

        await draft_node(_make_state(RECRUITER_EMAIL, db_message_id=db_id))

        async with test_db() as session:
            rows = (
                await session.execute(select(Draft).where(Draft.message_id == db_id))
            ).scalars().all()
            assert len(rows) == 1, "Draft should be saved to DB"
            assert rows[0].draft_text, "Persisted draft_text must not be empty"

    async def test_no_db_write_without_message_id(self, test_db):
        from sqlalchemy import select
        from app.db.models import Draft

        await draft_node(_make_state(RECRUITER_EMAIL, db_message_id=None))

        async with test_db() as session:
            rows = (await session.execute(select(Draft))).scalars().all()
            assert len(rows) == 0, "No DB write expected when db_message_id is None"

    async def test_draft_incorporates_meeting_slots(self):
        slots = [
            {"label": "Tuesday May 19 at 2pm PT"},
            {"label": "Thursday May 21 at 4pm PT"},
        ]
        result = await draft_node(_make_state(RECRUITER_EMAIL, meeting_options=slots))
        draft = result.get("draft", "").lower()
        slot_referenced = (
            "tuesday" in draft
            or "thursday" in draft
            or "may 19" in draft
            or "2pm" in draft
            or "4pm" in draft
        )
        assert slot_referenced, (
            "Draft with meeting slots should reference at least one of the available times"
        )


# ── LLM-as-judge quality evaluation ──────────────────────────────────────────

class TestDraftJudge:
    async def test_recruiter_draft_quality(self, judge):
        result = await draft_node(_make_state(RECRUITER_EMAIL))
        draft = result.get("draft", "")

        verdict = await judge(
            output=draft,
            context=(
                "Input: Recruiter email from Meta (Sarah Johnson) offering Senior ML Engineer role "
                "at $280k-$350k TC, asking to schedule a 30-min intro call. "
                "Two time slots offered: Tuesday May 19 at 2pm PT or Thursday May 21 at 4pm PT."
            ),
            criteria=(
                "1. Draft must acknowledge the opportunity (not refuse or ignore it).\n"
                "2. Draft must indicate availability to schedule or propose a next step.\n"
                "3. Tone must be professional — suitable for an email reply.\n"
                "4. Draft must NOT be signed (user fills in their own name).\n"
                "5. Draft must NOT include meta-instructions like 'click send' or '[Your name]' placeholders.\n"
                "6. Draft must be concise — no filler phrases.\n"
                "Deduct 3 points if it refuses to engage with the recruiter. "
                "Deduct 2 points if signed with a name."
            ),
        )
        assert verdict.passed, (
            f"Recruiter draft score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )

    async def test_urgent_draft_quality(self, judge):
        result = await draft_node(_make_state(URGENT_EMAIL))
        draft = result.get("draft", "")

        verdict = await judge(
            output=draft,
            context=(
                "Input: Production outage email from CTO (James). 40% of users affected, "
                "ML ranking service returning 500s. Asked to join a war room call immediately."
            ),
            criteria=(
                "1. Draft must confirm awareness of the situation or availability to join.\n"
                "2. Tone must be urgent and brief — this is a crisis.\n"
                "3. Draft should be 1-4 sentences maximum — no lengthy pleasantries.\n"
                "4. Must not be signed with a placeholder name.\n"
                "Deduct 5 points if it reads like a casual or low-urgency reply."
            ),
        )
        assert verdict.passed, (
            f"Urgent draft score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )
