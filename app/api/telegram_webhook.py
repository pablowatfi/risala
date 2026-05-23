"""
/telegram/webhook — single endpoint for all Telegram updates.

Handles:
  - Text commands (/start, /status)
  - Inline keyboard callbacks from job alerts (apply, research, cover_letter, dismiss)
"""
import json

from fastapi import APIRouter, Request
from sqlalchemy import select
from telegram import Update

from app.agents.research import generate_cover_letter
from app.db.models import JobAction, JobPosting, JobResearch
from app.db.session import AsyncSessionLocal
from app.integrations.telegram import answer_callback, get_bot, send_message

router = APIRouter(prefix="/telegram", tags=["telegram"])


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_job(db_id: int) -> JobPosting | None:
    async with AsyncSessionLocal() as session:
        return await session.get(JobPosting, db_id)


async def _get_research(job_posting_id: int) -> JobResearch | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobResearch)
            .where(JobResearch.job_posting_id == job_posting_id)
            .order_by(JobResearch.created_at.desc())
        )
        return result.scalars().first()


async def _record_action(job_posting_id: int, action_type: str) -> None:
    async with AsyncSessionLocal() as session:
        session.add(JobAction(job_posting_id=job_posting_id, action_type=action_type))
        await session.commit()


# ── Action handlers ───────────────────────────────────────────────────────────

async def _handle_apply(db_id: int) -> None:
    job = await _get_job(db_id)
    if job and job.apply_url:
        await send_message(
            f"🔗 <b>Apply — {job.title} @ {job.company}</b>\n\n{job.apply_url}"
        )
    else:
        await send_message("No application URL stored for this job.")
    await _record_action(db_id, "apply_link")


async def _handle_research(db_id: int) -> None:
    job = await _get_job(db_id)
    research = await _get_research(db_id)

    if not job:
        await send_message("Job not found.")
        return

    lines = [f"🔍 <b>Company Research — {job.company}</b>\n"]

    if research:
        if research.glassdoor_summary:
            lines.append(f"<b>Glassdoor:</b> {research.glassdoor_summary}")
        if research.salary_range:
            lines.append(f"<b>Salary:</b> {research.salary_range}")
        if research.reddit_summary:
            lines.append(f"<b>Reddit:</b> {research.reddit_summary}")
        if research.news_summary:
            lines.append(f"<b>News:</b> {research.news_summary}")

        if research.sources_json:
            try:
                sources = json.loads(research.sources_json)[:3]
                if sources:
                    lines.append("\n<b>Sources:</b>")
                    lines += [f"• <a href='{s['url']}'>{s['title'][:60]}</a>" for s in sources]
            except Exception:
                pass
    else:
        lines.append("No research data available for this company.")

    await send_message("\n".join(lines))
    await _record_action(db_id, "research_company")


async def _handle_cover_letter(db_id: int) -> None:
    job = await _get_job(db_id)
    if not job:
        await send_message("Job not found.")
        return

    await send_message(f"⏳ Generating cover letter for {job.title} @ {job.company}…")

    letter = await generate_cover_letter(
        title=job.title,
        company=job.company,
        description=job.description or "",
    )

    async with AsyncSessionLocal() as session:
        j = await session.get(JobPosting, db_id)
        if j:
            j.cover_letter = letter
            await session.commit()

    await send_message(
        f"📝 <b>Cover Letter Draft — {job.title} @ {job.company}</b>\n\n"
        f"<code>{letter}</code>"
    )
    await _record_action(db_id, "cover_letter")


async def _handle_dismiss(db_id: int) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(JobPosting, db_id)
        if job:
            job.status = "dismissed"
            await session.commit()
    await send_message("✓ Job dismissed.")
    await _record_action(db_id, "dismiss")


_ACTION_HANDLERS = {
    "apply": _handle_apply,
    "research": _handle_research,
    "cover_letter": _handle_cover_letter,
    "dismiss": _handle_dismiss,
}


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, get_bot())

    if update.callback_query:
        cq = update.callback_query
        await answer_callback(cq.id)

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

    if update.message and update.message.text:
        text = update.message.text.strip()

        if text.startswith("/start"):
            await send_message(
                "👋 <b>MessageOS is running.</b>\n\n"
                "I monitor your Gmail for LinkedIn and Wellfound job digest emails.\n"
                "When new matching positions arrive I'll alert you here.\n\n"
                "Commands:\n"
                "/status — show system status"
            )

        elif text.startswith("/status"):
            from app.config import settings
            await send_message(
                f"✅ <b>Status:</b> Running\n"
                f"LLM provider: <code>{settings.LLM_PROVIDER}</code>"
            )

    return {"ok": True}
