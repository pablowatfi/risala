"""
Classifies a normalised message as 'job_digest' or 'informational'.
Rule-based — no LLM, no DB. Detection is done via job_source set by ingestion.
"""
from app.graph.state import MessageState


async def triage_node(state: MessageState) -> dict:
    msg = state["normalized_message"]
    job_source = msg.get("job_source")

    category = "job_digest" if job_source else "informational"

    return {
        "classification": {
            "category": category,
        }
    }
