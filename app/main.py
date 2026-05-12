"""
FastAPI application entry point.
Handles startup (DB init, Gmail push registration, Telegram webhook, digest scheduler).
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlalchemy import and_, select

from app.config import settings
from app.db.models import Message
from app.db.session import AsyncSessionLocal, init_db
from app.graph.graph import build_graph
from app.integrations.gmail import register_push_notifications
from app.integrations.telegram import send_message, setup_webhook, delete_webhook

logger = logging.getLogger(__name__)

_pipeline = None
_scheduler = AsyncIOScheduler()


def get_pipeline():
    return _pipeline


# ── Digest ────────────────────────────────────────────────────────────────────

async def send_digest() -> None:
    """Send a digest of recent messages. Also callable via /digest Telegram command."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=5)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(
                and_(Message.created_at >= cutoff, Message.status == "new")
            ).order_by(Message.priority.desc(), Message.received_at.desc())
        )
        messages = result.scalars().all()

    if not messages:
        await send_message("📭 No new messages since the last digest.")
        return

    priority_icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}
    lines = [f"<b>Inbox digest — {now.strftime('%H:%M UTC')}</b>\n"]
    for msg in messages[:20]:
        icon = priority_icon.get(msg.priority or "low", "⚪")
        subject = msg.subject or "(no subject)"
        lines.append(f"{icon} <b>{subject[:60]}</b>\n   {msg.source} · {msg.sender[:40]}")

    await send_message("\n\n".join(lines))


def _schedule_digests() -> None:
    for time_str in settings.digest_times_list:
        try:
            hour, minute = map(int, time_str.split(":"))
            _scheduler.add_job(send_digest, "cron", hour=hour, minute=minute)
        except ValueError:
            logger.warning("Invalid DIGEST_TIMES entry: %s", time_str)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline

    # 1. Init DB tables
    await init_db()

    # 2. Build LangGraph pipeline
    _pipeline = build_graph()

    # 3. Register Telegram webhook
    if settings.TELEGRAM_BOT_TOKEN and settings.WEBHOOK_BASE_URL != "http://localhost:8000":
        try:
            await setup_webhook(f"{settings.WEBHOOK_BASE_URL}/telegram/webhook")
            logger.info("Telegram webhook registered.")
        except Exception as exc:
            logger.warning("Telegram webhook setup failed: %s", exc)

    # 4. Register Gmail push notifications (no-op if creds not present)
    for source in ("gmail_work", "gmail_personal"):
        try:
            await register_push_notifications(source)
        except Exception as exc:
            logger.warning("Gmail push registration skipped for %s: %s", source, exc)

    # 5. Start digest scheduler
    _schedule_digests()
    _scheduler.start()

    logger.info("MessageOS started. LLM provider: %s", settings.LLM_PROVIDER)
    yield

    _scheduler.shutdown(wait=False)
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            await delete_webhook()
        except Exception:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="MessageOS", version="0.1.0", lifespan=lifespan)

from app.api.gmail_webhook import router as gmail_router
from app.api.telegram_webhook import router as telegram_router

app.include_router(gmail_router)
app.include_router(telegram_router)


@app.get("/health")
async def health():
    return {"status": "ok", "llm_provider": settings.LLM_PROVIDER}
