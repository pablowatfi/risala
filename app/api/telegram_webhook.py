"""
/telegram/webhook — single endpoint for all Telegram updates.

Handles:
  - Text messages from the user (future: commands like /status)
  - Inline keyboard callback_queries (button taps on alerts)
"""
from fastapi import APIRouter, Request
from telegram import Update
from app.integrations.telegram import get_bot, answer_callback, send_message
from app.db.session import AsyncSessionLocal
from app.db.models import Message, Draft, Action
from sqlalchemy import select

router = APIRouter(prefix="/telegram", tags=["telegram"])


# ── Callback action handlers ──────────────────────────────────────────────────

async def _get_draft(db_id: int) -> Draft | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Draft).where(Draft.message_id == db_id).order_by(Draft.created_at.desc())
        )
        return result.scalars().first()


async def _get_message(db_id: int) -> Message | None:
    async with AsyncSessionLocal() as session:
        return await session.get(Message, db_id)


async def _record_action(db_id: int, action_type: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(Action(message_id=db_id, action_type=action_type))
        await session.commit()


async def _handle_show_draft(db_id: int) -> None:
    draft = await _get_draft(db_id)
    if draft:
        await send_message(f"<b>Draft reply:</b>\n\n<code>{draft.draft_text}</code>")
    else:
        await send_message("No draft available for this message.")
    await _record_action(db_id, "show_draft")


async def _handle_suggest_slots(db_id: int) -> None:
    msg = await _get_message(db_id)
    subject = msg.subject if msg else "this message"
    await send_message(f"Slots were shown in the original alert for: <i>{subject}</i>")
    await _record_action(db_id, "suggest_slots")


async def _handle_ask_more_info(db_id: int) -> None:
    draft = await _get_draft(db_id)
    if draft:
        await send_message(
            f"<b>Draft — asking for more info:</b>\n\n<code>{draft.draft_text}</code>"
        )
    else:
        await send_message("No draft available. The pipeline will generate one if a reply is needed.")
    await _record_action(db_id, "ask_more_info")


async def _handle_dismiss(db_id: int) -> None:
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, db_id)
        if msg:
            msg.status = "dismissed"
            await session.commit()
    await send_message("✓ Alert dismissed.")
    await _record_action(db_id, "dismiss")


_ACTION_HANDLERS = {
    "show_draft": _handle_show_draft,
    "suggest_slots": _handle_suggest_slots,
    "ask_more_info": _handle_ask_more_info,
    "dismiss": _handle_dismiss,
}


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, get_bot())

    # ── Button tap ────────────────────────────────────────────────────────────
    if update.callback_query:
        cq = update.callback_query
        await answer_callback(cq.id)  # clears the loading spinner

        raw = cq.data or ""
        if ":" in raw:
            action, db_id_str = raw.split(":", 1)
            try:
                db_id = int(db_id_str)
            except ValueError:
                return {"ok": True}

            handler = _ACTION_HANDLERS.get(action)
            if handler:
                await handler(db_id)

        return {"ok": True}

    # ── Incoming text message (commands / manual queries) ─────────────────────
    if update.message and update.message.text:
        text = update.message.text.strip()

        if text.startswith("/start"):
            await send_message(
                "👋 <b>MessageOS is running.</b>\n\n"
                "I'll alert you here when new emails or messages arrive.\n\n"
                "Commands:\n"
                "/status — show system status\n"
                "/digest — request a digest right now"
            )

        elif text.startswith("/status"):
            from app.config import settings
            await send_message(
                f"✅ <b>Status:</b> Running\n"
                f"LLM provider: <code>{settings.LLM_PROVIDER}</code>"
            )

        elif text.startswith("/digest"):
            from app.main import send_digest
            await send_digest()

    return {"ok": True}
