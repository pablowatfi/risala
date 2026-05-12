"""
FastAPI application entry point.
Handles startup (DB init, Gmail push registration, digest scheduler)
and exposes the compiled LangGraph pipeline via get_pipeline().
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.config import settings
from app.db.session import init_db, AsyncSessionLocal
from app.db.models import Message
from app.graph.graph import build_graph
from app.integrations.gmail import register_push_notifications
from app.integrations.slack import post_message
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

_pipeline = None
_scheduler = AsyncIOScheduler()


def get_pipeline():
    return _pipeline


# ── Digest ────────────────────────────────────────────────────────────────────

async def _send_digest() -> None:
    now = datetime.now(timezone.utc)

    # Collect messages created since last digest window (look back ~5 hours)
    from datetime import timedelta
    cutoff = now - timedelta(hours=5)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Message).where(
                and_(Message.created_at >= cutoff, Message.status == "new")
            ).order_by(Message.priority.desc(), Message.received_at.desc())
        )
        messages = result.scalars().all()

    if not messages:
        return

    lines = [f"*Inbox digest — {now.strftime('%H:%M')}*\n"]
    for msg in messages[:20]:
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(msg.priority or "low", "⚪")
        subject = msg.subject or "(no subject)"
        lines.append(f"{priority_icon} [{msg.source}] *{subject[:60]}* — {msg.sender[:40]}")

    await post_message(settings.SLACK_DIGEST_CHANNEL, "\n".join(lines))


def _schedule_digests() -> None:
    for time_str in settings.digest_times_list:
        try:
            hour, minute = map(int, time_str.split(":"))
            _scheduler.add_job(_send_digest, "cron", hour=hour, minute=minute)
        except ValueError:
            logger.warning("Invalid DIGEST_TIMES entry: %s", time_str)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline

    # 1. Init DB tables
    await init_db()

    # 2. Build LangGraph pipeline (no persistent checkpointer for now;
    #    swap in AsyncPostgresSaver once langgraph-checkpoint-postgres is wired)
    _pipeline = build_graph()

    # 3. Register Gmail push notifications (no-op if creds not present)
    for source in ("gmail_work", "gmail_personal"):
        try:
            await register_push_notifications(source)
        except Exception as exc:
            logger.warning("Gmail push registration skipped for %s: %s", source, exc)

    # 4. Start digest scheduler
    _schedule_digests()
    _scheduler.start()

    logger.info("MessageOS started. LLM provider: %s", settings.LLM_PROVIDER)
    yield

    _scheduler.shutdown(wait=False)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="MessageOS", version="0.1.0", lifespan=lifespan)

from app.api.gmail_webhook import router as gmail_router
from app.api.slack_webhook import router as slack_router
from app.api.slack_actions import router as slack_actions_router

app.include_router(gmail_router)
app.include_router(slack_router)
app.include_router(slack_actions_router)


@app.get("/health")
async def health():
    return {"status": "ok", "llm_provider": settings.LLM_PROVIDER}
