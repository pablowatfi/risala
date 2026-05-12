"""
Formats and posts the final alert to #message-os-alerts.
Builds a Slack Block Kit message with action buttons.
"""
from app.graph.state import MessageState
from app.integrations.slack import post_alert
from app.config import settings

_PRIORITY_EMOJI = {"high": "🚨", "medium": "📬", "low": "📄"}
_CATEGORY_LABEL = {
    "urgent": "Urgent",
    "task": "Action Required",
    "meeting": "Meeting Request",
    "research_needed": "Research",
    "informational": "FYI",
}


def _build_blocks(state: MessageState) -> list[dict]:
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

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {label}: {subject[:60]}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*From:*\n{sender}"},
                {"type": "mrkdwn", "text": f"*Source:*\n{source}"},
                {"type": "mrkdwn", "text": f"*Priority:*\n{priority.capitalize()}"},
                {"type": "mrkdwn", "text": f"*Category:*\n{label}"},
            ],
        },
    ]

    if research and research.get("summary"):
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Research:*\n{research['summary'][:500]}"},
        })

    if tasks:
        task_lines = "\n".join(f"• {t['task']}" for t in tasks[:5])
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Extracted tasks:*\n{task_lines}"},
        })

    if meeting_options:
        slot_lines = "\n".join(
            f"{i+1}. {s['label']}" for i, s in enumerate(meeting_options)
        )
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Available slots:*\n{slot_lines}"},
        })

    # Action buttons
    db_id = str(state.get("db_message_id", ""))
    actions: list[dict] = []

    if state.get("draft"):
        actions.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Show Draft"},
            "action_id": "show_draft",
            "value": db_id,
        })

    if meeting_options:
        actions.append({
            "type": "button",
            "text": {"type": "plain_text", "text": "Suggest Slots"},
            "action_id": "suggest_slots",
            "value": db_id,
        })

    actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "Ask for More Info"},
        "action_id": "ask_more_info",
        "value": db_id,
    })
    actions.append({
        "type": "button",
        "text": {"type": "plain_text", "text": "Dismiss"},
        "action_id": "dismiss",
        "value": db_id,
        "style": "danger",
    })

    blocks.append({"type": "divider"})
    blocks.append({"type": "actions", "elements": actions})

    return blocks


async def slack_notify_node(state: MessageState) -> dict:
    blocks = _build_blocks(state)
    await post_alert(
        channel=settings.SLACK_ALERTS_CHANNEL,
        blocks=blocks,
        fallback_text=f"New message alert: {state['normalized_message'].get('subject', '')}",
    )
    return {}
