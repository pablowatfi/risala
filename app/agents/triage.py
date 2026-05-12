"""
Classifies a normalised message: priority, category, and pipeline flags.
Uses the fast LLM with structured output.
"""
from typing import Literal
from pydantic import BaseModel, Field
from app.graph.state import MessageState
from app.llm import get_llm


class TriageResult(BaseModel):
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

Rules:
- priority=high: deadline today, urgent request, recruiter/interview, time-sensitive
- category=meeting: contains a meeting/interview/call request or invite
- category=task: contains explicit action items or requests
- category=research_needed: company/product/person you'd want to look up first
- needs_draft=true: sender expects a reply
"""


async def triage_node(state: MessageState) -> dict:
    msg = state["normalized_message"]
    llm = get_llm("fast").with_structured_output(TriageResult)

    prompt = _PROMPT.format(
        source=msg.get("source", ""),
        sender=msg.get("sender", ""),
        subject=msg.get("subject", "") or "(no subject)",
        body=(msg.get("body", "") or "")[:3000],  # cap to avoid token overflow
    )

    result: TriageResult = await llm.ainvoke(prompt)

    return {
        "classification": {
            "priority": result.priority,
            "category": result.category,
            "needs_research": result.needs_research,
            "needs_draft": result.needs_draft,
            "reasoning": result.reasoning,
        }
    }
