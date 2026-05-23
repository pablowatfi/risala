"""
Normalises raw Gmail webhook payloads into a common dict shape.
Detects LinkedIn/Wellfound job digest senders and annotates with job_source.
No LLM needed — pure parsing.
"""
import re
from datetime import datetime, timezone
from app.graph.state import MessageState


# ── Signature strippers ───────────────────────────────────────────────────────

_SIGNATURE_PATTERNS = [
    r"\n--\s*\n.*",
    r"\nSent from my .*",
    r"\nGet Outlook for .*",
    r"\nBest,?\n.*",
    r"\nRegards,?\n.*",
    r"\nThanks,?\n.*",
    r"\nCheers,?\n.*",
]
_SIGNATURE_RE = re.compile("|".join(_SIGNATURE_PATTERNS), re.DOTALL | re.IGNORECASE)


def _strip_signature(body: str) -> str:
    return _SIGNATURE_RE.sub("", body).strip()


# ── Job source detection ──────────────────────────────────────────────────────

_LINKEDIN_DOMAINS = {"linkedin.com", "e.linkedin.com", "em.linkedin.com", "jobs.linkedin.com"}
_WELLFOUND_DOMAINS = {"wellfound.com", "angel.co", "notifications.wellfound.com"}


def _detect_job_source(sender: str) -> str | None:
    """Return 'linkedin', 'wellfound', or None based on sender domain."""
    # Extract domain from "Display Name <addr@domain.com>" or plain "addr@domain.com"
    match = re.search(r"@([\w.\-]+)", sender)
    if not match:
        return None
    domain = match.group(1).lower()

    if any(domain == d or domain.endswith("." + d) for d in _LINKEDIN_DOMAINS):
        return "linkedin"
    if any(domain == d or domain.endswith("." + d) for d in _WELLFOUND_DOMAINS):
        return "wellfound"
    return None


# ── Gmail parser ──────────────────────────────────────────────────────────────

def _parse_gmail(event: dict) -> dict:
    sender = event.get("sender", "")
    job_source = _detect_job_source(sender)
    return {
        "message_id": event["message_id"],
        "source": event["source"],
        "sender": sender,
        "subject": event.get("subject") or "",
        "body": _strip_signature(event.get("body", "")),
        "thread_id": event.get("thread_id", ""),
        "received_at": event.get("received_at", datetime.now(timezone.utc).isoformat()),
        "job_source": job_source,  # "linkedin" | "wellfound" | None
        "type": "job_digest" if job_source else "email",
    }


# ── Node ──────────────────────────────────────────────────────────────────────

async def ingestion_node(state: MessageState) -> dict:
    event = state["raw_event"]
    normalized = _parse_gmail(event)
    return {"normalized_message": normalized}
