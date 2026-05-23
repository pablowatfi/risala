"""
FastAPI application entry point.
Polls Gmail 3× daily for new emails instead of using push notifications.
"""
import json
import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.config import settings
from app.db.session import init_db
from app.graph.graph import build_graph
from app.integrations.gmail import fetch_messages_since, get_current_history_id
from app.integrations.langfuse import get_langfuse_handler
from app.integrations.telegram import delete_webhook, setup_webhook

logger = logging.getLogger(__name__)

_pipeline = None
_scheduler = AsyncIOScheduler()


def get_pipeline():
    return _pipeline


# ── Poll state (historyId per account) ───────────────────────────────────────

def _load_poll_state() -> dict:
    if os.path.exists(settings.GMAIL_POLL_STATE_FILE):
        with open(settings.GMAIL_POLL_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_poll_state(state: dict) -> None:
    with open(settings.GMAIL_POLL_STATE_FILE, "w") as f:
        json.dump(state, f)


# ── Poll job ──────────────────────────────────────────────────────────────────

async def poll_gmail() -> None:
    """
    Fetch emails from both Gmail accounts that arrived since the last poll.
    On the very first run for an account, bookmarks the current position
    without processing any existing emails (avoids flooding on first start).
    """
    state = _load_poll_state()
    pipeline = get_pipeline()
    if not pipeline:
        return

    for source in ("gmail_work", "gmail_personal"):
        history_id = state.get(source)

        if not history_id:
            # First run: bookmark current position, process nothing
            current = await get_current_history_id(source)
            if current:
                state[source] = current
                _save_poll_state(state)
                logger.info("Bookmarked %s at historyId=%s (first run)", source, current)
            continue

        messages, new_history_id = await fetch_messages_since(history_id, source)

        if new_history_id is None:
            # historyId expired — reset to current position
            logger.warning("%s historyId expired, resetting bookmark", source)
            current = await get_current_history_id(source)
            if current:
                state[source] = current
                _save_poll_state(state)
            continue

        logger.info("Poll %s: %d new message(s)", source, len(messages))

        for msg in messages:
            try:
                handler = get_langfuse_handler(
                    trace_name=f"{source}:{msg.get('message_id', 'unknown')}"
                )
                callbacks = [handler] if handler else []
                await pipeline.ainvoke(
                    {"raw_event": msg},
                    config={
                        "configurable": {"thread_id": msg["thread_id"]},
                        "callbacks": callbacks,
                    },
                )
                if handler:
                    handler.flush()
            except Exception as exc:
                logger.error("Pipeline error for message %s: %s", msg.get("message_id"), exc)

        state[source] = new_history_id
        _save_poll_state(state)


def _schedule_polls() -> None:
    for time_str in settings.poll_times_list:
        try:
            hour, minute = map(int, time_str.split(":"))
            _scheduler.add_job(poll_gmail, "cron", hour=hour, minute=minute)
            logger.info("Gmail poll scheduled at %s", time_str)
        except ValueError:
            logger.warning("Invalid POLL_TIMES entry: %s", time_str)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline

    await init_db()
    _pipeline = build_graph()

    if settings.TELEGRAM_BOT_TOKEN and settings.WEBHOOK_BASE_URL != "http://localhost:8000":
        try:
            await setup_webhook(f"{settings.WEBHOOK_BASE_URL}/telegram/webhook")
            logger.info("Telegram webhook registered.")
        except Exception as exc:
            logger.warning("Telegram webhook setup failed: %s", exc)

    _schedule_polls()
    _scheduler.start()

    logger.info(
        "MessageOS started. LLM: %s | Polling at: %s",
        settings.LLM_PROVIDER,
        settings.POLL_TIMES,
    )
    yield

    _scheduler.shutdown(wait=False)
    if settings.TELEGRAM_BOT_TOKEN:
        try:
            await delete_webhook()
        except Exception:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="MessageOS", version="0.1.0", lifespan=lifespan)

from app.api.telegram_webhook import router as telegram_router

app.include_router(telegram_router)


@app.get("/health")
async def health():
    return {"status": "ok", "llm_provider": settings.LLM_PROVIDER, "poll_times": settings.POLL_TIMES}


@app.post("/poll")
async def trigger_poll():
    """Manually trigger a Gmail poll (useful for testing without waiting for schedule)."""
    await poll_gmail()
    return {"status": "ok"}
