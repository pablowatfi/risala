"""
Classifies a normalised message: priority, category, and pipeline flags.
Also persists the message row to the DB and returns db_message_id.
Uses the fast LLM with structured output.
"""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field
from app.graph.state import MessageState
from app.llm import get_llm
from app.db.session import AsyncSessionLocal
from app.db.models import Message as MessageModel


class TriageResult(BaseModel):
    is_work_related: bool = Field(
        description=(
            "True if the message is related to the user's professional life: work tasks, "
            "job opportunities, colleagues, clients, interviews, or anything requiring a "
            "professional response. False for personal emails, spam, and unsubscribable "
            "newsletters with no professional relevance."
        )
    )
    priority: Literal["high", "medium", "low"] = Field(
        description="Urgency: high=needs attention today, medium=today/tomorrow, low=FYI"
    )
    category: Literal["urgent", "task", "meeting", "research_needed", "informational"] = Field(
        description="Primary category of the message"
    )
    needs_research: bool = Field(
        description="True if web research would meaningfully help the user (e.g. recruiter email, unfamiliar company/product)"
    )
    needs_draft: bool = Field(
        description="True if the user likely needs to reply to this message"
    )
    reasoning: str = Field(description="One sentence explaining the classification")


_PROMPT = """You are an inbox triage assistant. Classify the message below.

Source: {source}
From: {sender}
Subject: {subject}
Body:
{body}

Step 1 — is_work_related:
  TRUE  if the message relates to the user's professional life:
        work tasks, job opportunities, colleagues, clients, interviews,
        recruiters, manager requests, code reviews, production incidents.
  FALSE if it is a personal email, spam, mass mailing, or a newsletter
        the user subscribed to (look for "Unsubscribe" link, date-stamped
        subject, no personal greeting, newsletter@ sender).

Step 2 — classify (only if is_work_related=True; otherwise use low/informational/False/False):

  NEWSLETTERS / DIGESTS:
  - "Unsubscribe" link present, date-stamped subject, newsletter@ sender, no personal greeting
    -> priority=low, category=informational, needs_draft=False, needs_research=False

  URGENT:
  - Production outage, Sev-1, security incident, or explicit "URGENT" from management
    -> priority=high, category=urgent, needs_draft=True

  MEETING:
  - Contains a meeting/call/interview scheduling request
    -> category=meeting, needs_draft=True

  TASK:
  - Explicit action items assigned to the user with deadlines
    -> category=task, needs_draft=False (unless a reply is explicitly expected)

  RESEARCH NEEDED:
  - Recruiter email, unfamiliar company/person where background info would help the reply
    -> category=research_needed, needs_research=True

  INFORMATIONAL:
  - Everything else with no action required
    -> priority=low, category=informational, needs_draft=False
"""


def _parse_received_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


async def triage_node(state: MessageState) -> dict:
    msg = state["normalized_message"]
    llm = get_llm("fast").with_structured_output(TriageResult)

    prompt = _PROMPT.format(
        source=msg.get("source", ""),
        sender=msg.get("sender", ""),
        subject=msg.get("subject", "") or "(no subject)",
        body=(msg.get("body", "") or "")[:3000],
    )

    result: TriageResult = await llm.ainvoke(prompt)

    # Persist the message to DB now that we have both content and classification
    async with AsyncSessionLocal() as session:
        db_msg = MessageModel(
            source=msg.get("source", ""),
            sender=msg.get("sender", ""),
            subject=msg.get("subject"),
            body=msg.get("body", ""),
            thread_id=msg.get("thread_id"),
            received_at=_parse_received_at(msg.get("received_at")),
            priority=result.priority,
            category=result.category,
        )
        session.add(db_msg)
        await session.commit()
        await session.refresh(db_msg)
        db_message_id = db_msg.id

    return {
        "classification": {
            "is_work_related": result.is_work_related,
            "priority": result.priority,
            "category": result.category,
            "needs_research": result.needs_research,
            "needs_draft": result.needs_draft,
            "reasoning": result.reasoning,
        },
        "db_message_id": db_message_id,
    }
