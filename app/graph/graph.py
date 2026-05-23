from langgraph.graph import StateGraph, END
from app.graph.state import MessageState
from app.agents.ingestion import ingestion_node
from app.agents.triage import triage_node
from app.agents.job_pipeline import job_pipeline_node
from app.agents.telegram_notify import telegram_notify_node


def _route_after_triage(state: MessageState) -> str:
    category = state["classification"].get("category", "informational")
    if category == "job_digest":
        return "job_pipeline"
    return END


def build_graph(checkpointer=None):
    g = StateGraph(MessageState)

    g.add_node("ingestion", ingestion_node)
    g.add_node("triage", triage_node)
    g.add_node("job_pipeline", job_pipeline_node)
    g.add_node("telegram_notify", telegram_notify_node)

    g.set_entry_point("ingestion")
    g.add_edge("ingestion", "triage")

    g.add_conditional_edges("triage", _route_after_triage, {
        "job_pipeline": "job_pipeline",
        END: END,
    })

    g.add_edge("job_pipeline", "telegram_notify")
    g.add_edge("telegram_notify", END)

    return g.compile(checkpointer=checkpointer)
