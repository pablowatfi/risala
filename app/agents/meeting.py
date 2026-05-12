"""
Checks Google Calendar for free slots when a meeting request is detected.
Only runs when classification.category == 'meeting'.
"""
from app.graph.state import MessageState
from app.integrations.calendar import get_free_slots
from app.config import settings


async def meeting_node(state: MessageState) -> dict:
    if state["classification"].get("category") != "meeting":
        return {}

    slots = await get_free_slots(
        count=settings.MEETING_SLOT_COUNT,
        lookahead_days=settings.MEETING_LOOKAHEAD_DAYS,
    )

    return {"meeting_options": slots}
