"""
Formats the pipeline result and sends a Telegram alert with inline action buttons.
"""
from app.graph.state import MessageState
from app.integrations.telegram import send_alert

_PRIORITY_EMOJI = {"high": "🚨", "medium": "📬", "low": "📄"}
_CATEGORY_LABEL = {
    "urgent": "Urgent",
    "task": "Action Required",
    "meeting": "Meeting Request",
    "research_needed": "Research",
    "informational": "FYI",
}


def _build_text(state: MessageState) -> str:
    msg = state["normalized_message"]
    clf = state["classification"]
    research = state.get("research")
    meeting_options = state.get("meeting_options", [])
    tasks = state.get("tasks", [])

    priority = clf.get("priority", "low")
    category = clf.get("category", "informational")
    emoji = _PRIORITY_EMOJI.get(priority, "📄")
    label = _CATEGORY_LABEL.get(category, category)

    sender = msg.get("sender", "Unknown")
    subject = msg.get("subject") or "(no subject)"
    source = msg.get("source", "")

    lines = [
        f"{emoji} <b>{label}: {subject[:80]}</b>",
        "",
        f"<b>From:</b> {sender}",
        f"<b>Source:</b> {source}",
        f"<b>Priority:</b> {priority.capitalize()}",
    ]

    if research and research.get("summary"):
        lines += ["", "<b>Research:</b>", research["summary"][:600]]

    if tasks:
        lines += ["", "<b>Tasks extracted:</b>"]
        lines += [f"• {t['task']}" for t in tasks[:5]]

    if meeting_options:
        lines += ["", "<b>Available slots:</b>"]
        lines += [f"{i+1}. {s['label']}" for i, s in enumerate(meeting_options)]

    return "\n".join(lines)


def _build_buttons(state: MessageState) -> list[list[dict]]:
    db_id = str(state.get("db_message_id", ""))
    buttons: list[dict] = []

    if state.get("draft"):
        buttons.append({"text": "Show Draft", "callback_data": f"show_draft:{db_id}"})

    if state.get("meeting_options"):
        buttons.append({"text": "Suggest Slots", "callback_data": f"suggest_slots:{db_id}"})

    buttons.append({"text": "Ask for More Info", "callback_data": f"ask_more_info:{db_id}"})
    buttons.append({"text": "❌ Dismiss", "callback_data": f"dismiss:{db_id}"})

    # Two buttons per row
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return rows


async def telegram_notify_node(state: MessageState) -> dict:
    text = _build_text(state)
    buttons = _build_buttons(state)
    await send_alert(text, buttons)
    return {}
