"""
Formats job pipeline results and sends a consolidated Telegram alert
with inline buttons per job (Apply, Research Company, Cover Letter).
Only medium and high match jobs are included.
"""
from app.graph.state import MessageState
from app.integrations.telegram import send_alert, send_message

_MATCH_EMOJI = {"high": "🟢", "medium": "🟡", "low": "⚪"}
_MATCH_LABEL = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def _format_research(research: dict) -> str:
    parts = []
    if research.get("glassdoor_summary"):
        parts.append(research["glassdoor_summary"])
    if research.get("salary_range"):
        parts.append(f"💰 {research['salary_range']}")
    if research.get("reddit_summary"):
        parts.append(research["reddit_summary"])
    return " · ".join(parts) if parts else ""


def _build_job_block(job: dict, research: dict | None) -> tuple[str, list[dict]]:
    """Returns (text_block, button_row) for a single job."""
    emoji = _MATCH_EMOJI.get(job.get("match_tag", "low"), "⚪")
    label = _MATCH_LABEL.get(job.get("match_tag", "low"), "LOW")
    db_id = str(job.get("db_id", ""))

    lines = [
        f"{emoji} <b>{label} — {job['title']} @ {job['company']}</b>",
        f"   {job.get('location', '')}",
    ]

    if research:
        r_text = _format_research(research)
        if r_text:
            lines.append(f"   {r_text}")

    text = "\n".join(l for l in lines if l.strip())

    buttons = [
        {"text": "Apply ↗", "callback_data": f"apply:{db_id}"},
        {"text": "Research Company", "callback_data": f"research:{db_id}"},
        {"text": "Cover Letter", "callback_data": f"cover_letter:{db_id}"},
    ]

    return text, buttons


async def telegram_notify_node(state: MessageState) -> dict:
    scored_jobs = state.get("scored_jobs") or []
    job_research = state.get("job_research") or {}

    visible = [j for j in scored_jobs if j.get("match_tag") in ("medium", "high")]
    discarded = len(scored_jobs) - len(visible)

    if not visible:
        if discarded:
            await send_message(
                f"💼 Job digest processed — {discarded} position(s) were low match, none to report."
            )
        return {}

    source_label = state["normalized_message"].get("job_source", "").capitalize()
    header = f"💼 <b>New Job Matches — {source_label}</b>\n"

    # Build one message per job with its own button row
    for i, job in enumerate(visible):
        ext_id = job.get("external_id", "")
        research = job_research.get(ext_id)

        text, button_row = _build_job_block(job, research)

        if i == 0:
            text = header + "\n" + text

        await send_alert(text, [button_row])

    if discarded:
        await send_message(f"<i>({discarded} low-match position(s) not shown)</i>")

    return {}
