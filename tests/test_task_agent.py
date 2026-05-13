"""
Task agent tests — LLM + LLM-as-judge.

Verifies task extraction from emails: count, structure, due dates, DB persistence.
"""
import pytest
from tests.conftest import requires_llm
from tests.fixtures.messages import TASK_EMAIL, NEWSLETTER_EMAIL
from app.agents.task_agent import task_node

pytestmark = [pytest.mark.integration, requires_llm()]


def _make_state(msg: dict, db_message_id: int | None = None) -> dict:
    return {"normalized_message": msg, "db_message_id": db_message_id}


# ── Deterministic assertions ──────────────────────────────────────────────────

class TestTaskExtraction:
    async def test_task_email_has_tasks(self):
        result = await task_node(_make_state(TASK_EMAIL))
        assert len(result["tasks"]) >= 2, (
            f"TASK_EMAIL has 3 explicit action items, got: {result['tasks']}"
        )

    async def test_task_structure_has_required_keys(self):
        result = await task_node(_make_state(TASK_EMAIL))
        for task in result["tasks"]:
            for key in ("task", "due_date", "owner"):
                assert key in task, f"Task missing key '{key}': {task}"

    async def test_task_email_has_due_dates(self):
        result = await task_node(_make_state(TASK_EMAIL))
        tasks_with_dates = [t for t in result["tasks"] if t.get("due_date")]
        assert len(tasks_with_dates) >= 1, (
            "TASK_EMAIL has 3 explicit deadlines; at least one task should have a due_date"
        )

    async def test_newsletter_has_no_tasks(self):
        result = await task_node(_make_state(NEWSLETTER_EMAIL))
        assert result["tasks"] == [], (
            f"Newsletter should have no tasks, got: {result['tasks']}"
        )

    async def test_tasks_persisted_to_db(self, test_db):
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.db.models import Task, Message

        async with test_db() as session:
            msg_row = Message(
                source="gmail_work",
                thread_id="t-task-persist",
                sender="david.chen@company.com",
                subject="Action items",
                body="test body",
                received_at=datetime.now(timezone.utc),
                priority="high",
                category="task",
            )
            session.add(msg_row)
            await session.commit()
            await session.refresh(msg_row)
            db_id = msg_row.id

        result = await task_node(_make_state(TASK_EMAIL, db_message_id=db_id))
        assert len(result["tasks"]) > 0

        async with test_db() as session:
            rows = (
                await session.execute(select(Task).where(Task.message_id == db_id))
            ).scalars().all()
            assert len(rows) > 0, "Tasks should be persisted to DB when db_message_id is set"

    async def test_no_db_write_without_message_id(self, test_db):
        from sqlalchemy import select
        from app.db.models import Task

        result = await task_node(_make_state(TASK_EMAIL, db_message_id=None))
        assert "tasks" in result

        async with test_db() as session:
            rows = (await session.execute(select(Task))).scalars().all()
            assert len(rows) == 0, "No DB write expected when db_message_id is None"


# ── LLM-as-judge quality evaluation ──────────────────────────────────────────

class TestTaskJudge:
    async def test_task_extraction_quality(self, judge):
        result = await task_node(_make_state(TASK_EMAIL))

        verdict = await judge(
            output=str(result["tasks"]),
            context=(
                "Input: Email from Engineering Manager David Chen with 3 explicit action items:\n"
                "1. Submit quarterly metrics report by Friday May 16th EOD\n"
                "2. Schedule 1:1 onboarding session with Alex Rivera by May 22nd\n"
                "3. Review and approve CI/CD deployment document by May 20th"
            ),
            criteria=(
                "1. At least 2 of the 3 action items must be extracted as separate tasks.\n"
                "2. Each task must be a clear imperative sentence describing an action.\n"
                "3. At least one task must have a due_date populated (deadlines are explicit in the email).\n"
                "4. Tasks should not include noise or paraphrase non-action content.\n"
                "Deduct 3 points for each missed action item. "
                "Deduct 2 points if no tasks have a due_date despite explicit deadlines."
            ),
        )
        assert verdict.passed, (
            f"Task extraction score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )

    async def test_newsletter_no_tasks_quality(self, judge):
        result = await task_node(_make_state(NEWSLETTER_EMAIL))

        verdict = await judge(
            output=str(result["tasks"]),
            context="Input: TLDR Tech daily newsletter — purely informational, no action items.",
            criteria=(
                "1. tasks list must be empty — newsletters contain no action items.\n"
                "2. Penalise with 0 score if any tasks are extracted from a newsletter.\n"
                "A score of 10 means the list is empty and correct."
            ),
        )
        assert verdict.passed, (
            f"Newsletter task score {verdict.score}/10.\n"
            f"Reasoning: {verdict.reasoning}\n"
            f"Issues: {verdict.issues}"
        )
