"""
/gmail/push  — receives Google Pub/Sub push notifications for both Gmail accounts.
Decodes the notification, determines which account it came from, fetches the
new messages, and fires the LangGraph pipeline for each one.
"""
import base64
import json
from fastapi import APIRouter, Request, HTTPException
from app.integrations.gmail import fetch_messages_since
from app.config import settings

router = APIRouter(prefix="/gmail", tags=["gmail"])


def _source_for_address(address: str) -> str | None:
    if address == settings.GMAIL_WORK_ADDRESS:
        return "gmail_work"
    if address == settings.GMAIL_PERSONAL_ADDRESS:
        return "gmail_personal"
    return None


@router.post("/push")
async def gmail_push(request: Request):
    body = await request.json()

    # Pub/Sub wraps the notification in a base64-encoded data field
    message = body.get("message", {})
    data_b64 = message.get("data", "")
    if not data_b64:
        raise HTTPException(status_code=400, detail="Missing data field")

    notification = json.loads(base64.b64decode(data_b64).decode())
    email_address = notification.get("emailAddress", "")
    history_id = notification.get("historyId", "")

    if not history_id:
        return {"status": "ignored"}

    source = _source_for_address(email_address)
    if not source:
        return {"status": "unknown_account"}

    messages = await fetch_messages_since(history_id, source)

    # Import here to avoid circular imports; pipeline is built in main.py
    from app.main import get_pipeline
    pipeline = get_pipeline()

    for msg in messages:
        await pipeline.ainvoke(
            {"raw_event": msg},
            config={"configurable": {"thread_id": msg["thread_id"]}},
        )

    return {"status": "ok", "processed": len(messages)}
