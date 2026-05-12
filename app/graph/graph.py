from langgraph.graph import StateGraph, END
from app.graph.state import MessageState
from app.agents.ingestion import ingestion_node
from app.agents.triage import triage_node
from app.agents.research import research_node
from app.agents.meeting import meeting_node
from app.agents.task_agent import task_node
from app.agents.draft import draft_node
from app.agents.telegram_notify import telegram_notify_node

# ── Routing functions ────────────────────────────────────────────────────────
# Each function decides where to go next in the sequential pipeline.
# Research → Meeting → Task → Draft → Notify, skipping steps not needed.

def _route_after_triage(state: MessageState) -> str:
    if state["classification"].get("needs_research"):
        return "research"
    category = state["classification"].get("category", "informational")
    if category == "meeting":
        return "meeting"
    return "task_agent"


def _route_after_research(state: MessageState) -> str:
    category = state["classification"].get("category", "informational")
    if category == "meeting":
        return "meeting"
    return "task_agent"


def _route_after_meeting(state: MessageState) -> str:
    return "task_agent"


def _route_after_task(state: MessageState) -> str:
    if state["classification"].get("needs_draft"):
        return "draft"
    return "telegram_notify"


def _route_after_draft(state: MessageState) -> str:
    priority = state["classification"].get("priority", "low")
    if priority in ("high", "medium"):
        return "telegram_notify"
    return END


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    g = StateGraph(MessageState)

    g.add_node("ingestion", ingestion_node)
    g.add_node("triage", triage_node)
    g.add_node("research", research_node)
    g.add_node("meeting", meeting_node)
    g.add_node("task_agent", task_node)
    g.add_node("draft", draft_node)
    g.add_node("telegram_notify", telegram_notify_node)

    g.set_entry_point("ingestion")
    g.add_edge("ingestion", "triage")

    g.add_conditional_edges("triage", _route_after_triage, {
        "research": "research",
        "meeting": "meeting",
        "task_agent": "task_agent",
    })
    g.add_conditional_edges("research", _route_after_research, {
        "meeting": "meeting",
        "task_agent": "task_agent",
    })
    g.add_edge("meeting", "task_agent")
    g.add_conditional_edges("task_agent", _route_after_task, {
        "draft": "draft",
        "telegram_notify": "telegram_notify",
    })
    g.add_conditional_edges("draft", _route_after_draft, {
        "telegram_notify": "telegram_notify",
        END: END,
    })
    g.add_edge("telegram_notify", END)

    return g.compile(checkpointer=checkpointer)
