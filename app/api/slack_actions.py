"""
/slack/actions — receives Interactive Component payloads when users click buttons.
Posts a new message to #message-os-alerts with the requested content.
"""
import json
from fastapi import APIRouter, Form, Request, HTTPException
from app.integrations.slack import verify_slack_signature, post_message
from app.db.session import AsyncSessionLocal
from app.db.models import Message, Draft, Action
from app.config import settings
from sqlalchemy import select

router = APIRouter(prefix="/slack", tags=["slack"])


async def _get_message(db_id: int) -> Message | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Message).where(Message.id == db_id))
        return result.scalar_one_or_none()


async def _get_draft(db_id: int) -> Draft | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Draft).where(Draft.message_id == db_id).order_by(Draft.created_at.desc())
        )
        return result.scalars().first()


async def _record_action(db_id: int, action_type: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(Action(message_id=db_id, action_type=action_type))
        await session.commit()


@router.post("/actions")
async def slack_actions(request: Request, payload: str = Form(...)):
    body_bytes = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body_bytes, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    data = json.loads(payload)
    actions = data.get("actions", [])
    if not actions:
        return {"status": "ignored"}

    action = actions[0]
    action_id = action.get("action_id", "")
    db_id_str = action.get("value", "")

    try:
        db_id = int(db_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid message id")

    channel = settings.SLACK_ALERTS_CHANNEL

    if action_id == "show_draft":
        draft = await _get_draft(db_id)
        text = f"*Draft reply:*\n```{draft.draft_text}```" if draft else "_No draft available._"
        await post_message(channel, text)
        await _record_action(db_id, "show_draft")

    elif action_id == "suggest_slots":
        # Slots were already shown in the original alert; re-post them here for clarity
        msg = await _get_message(db_id)
        subject = msg.subject if msg else "this message"
        await post_message(channel, f"_Slot suggestion already shown in the alert above for: {subject}_")
        await _record_action(db_id, "suggest_slots")

    elif action_id == "ask_more_info":
        msg = await _get_message(db_id)
        draft = await _get_draft(db_id)
        if draft:
            text = f"*Draft — asking for more info:*\n```{draft.draft_text}```"
        else:
            text = f"_Generate a draft first by clicking 'Show Draft' on the original alert._"
        await post_message(channel, text)
        await _record_action(db_id, "ask_more_info")

    elif action_id == "dismiss":
        async with AsyncSessionLocal() as session:
            msg = await session.get(Message, db_id)
            if msg:
                msg.status = "dismissed"
                await session.commit()
        await post_message(channel, f"✓ Alert dismissed.")
        await _record_action(db_id, "dismiss")

    return {"status": "ok"}
