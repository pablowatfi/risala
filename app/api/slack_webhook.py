"""
/slack/events — receives Slack Events API callbacks.
Handles URL verification challenge and message events.
"""
from fastapi import APIRouter, Request, HTTPException
from app.integrations.slack import verify_slack_signature

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/events")
async def slack_events(request: Request):
    body_bytes = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body_bytes, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()

    # Slack sends a one-time challenge during app setup
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    if payload.get("type") != "event_callback":
        return {"status": "ignored"}

    event = payload.get("event", {})
    event_type = event.get("type", "")

    # Only process direct messages and mentions; skip bot messages
    if event_type not in ("message", "app_mention"):
        return {"status": "ignored"}
    if event.get("bot_id"):
        return {"status": "ignored"}

    raw_event = {**payload, "source": "slack"}

    from app.main import get_pipeline
    pipeline = get_pipeline()

    thread_id = event.get("thread_ts") or event.get("ts", "slack_unknown")
    await pipeline.ainvoke(
        {"raw_event": raw_event},
        config={"configurable": {"thread_id": thread_id}},
    )

    return {"status": "ok"}
