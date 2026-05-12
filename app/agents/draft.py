"""
Generates a suggested reply draft. Never sends. Persists to DB.
Only runs when classification.needs_draft is True.
"""
from app.graph.state import MessageState
from app.llm import get_llm
from app.db.session import AsyncSessionLocal
from app.db.models import Draft

_PROMPT = """You are a professional email/message assistant. Write a draft reply for the user.

Original message
From: {sender}
Subject: {subject}
Body:
{body}

{research_section}
{meeting_section}

Guidelines:
- Match the tone of the original (professional if email, casual if Slack)
- Be concise — no filler phrases
- Do NOT sign the message (the user will fill in their name)
- Do NOT send — this is a draft only"""


def _research_section(research: dict | None) -> str:
    if not research or not research.get("summary"):
        return ""
    return f"Background research:\n{research['summary']}\n"


def _meeting_section(meeting_options: list) -> str:
    if not meeting_options:
        return ""
    lines = ["Available meeting slots:"]
    for i, slot in enumerate(meeting_options, 1):
        lines.append(f"  {i}. {slot['label']}")
    return "\n".join(lines) + "\n"


async def draft_node(state: MessageState) -> dict:
    if not state["classification"].get("needs_draft"):
        return {}

    msg = state["normalized_message"]
    llm = get_llm("smart")

    prompt = _PROMPT.format(
        sender=msg.get("sender", ""),
        subject=msg.get("subject", "") or "(no subject)",
        body=(msg.get("body", "") or "")[:3000],
        research_section=_research_section(state.get("research")),
        meeting_section=_meeting_section(state.get("meeting_options", [])),
    )

    response = await llm.ainvoke(prompt)
    draft_text = response.content

    # Persist draft to DB
    db_message_id = state.get("db_message_id")
    if db_message_id:
        async with AsyncSessionLocal() as session:
            session.add(Draft(message_id=db_message_id, draft_text=draft_text))
            await session.commit()

    return {"draft": draft_text}
