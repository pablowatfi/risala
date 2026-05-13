"""
Normalises raw Gmail / Slack webhook payloads into a common dict shape.
No LLM is needed here — pure parsing.
"""
import re
from datetime import datetime, timezone
from app.graph.state import MessageState


# ── Signature strippers ───────────────────────────────────────────────────────

_SIGNATURE_PATTERNS = [
    r"\n--\s*\n.*",            # standard -- delimiter
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


# ── Source-specific parsers ───────────────────────────────────────────────────

def _parse_gmail(event: dict) -> dict:
    """
    event shape produced by integrations/gmail.py after fetching the full message.
    {
      "source": "gmail_work" | "gmail_personal",
      "message_id": str,
      "thread_id": str,
      "sender": str,
      "subject": str,
      "body": str,
      "received_at": ISO str,
    }
    """
    return {
        "message_id": event["message_id"],
        "source": event["source"],
        "sender": event.get("sender", ""),
        "subject": event.get("subject") or "",
        "body": _strip_signature(event.get("body", "")),
        "thread_id": event.get("thread_id", ""),
        "received_at": event.get("received_at", datetime.now(timezone.utc).isoformat()),
    }


def _parse_slack(event: dict) -> dict:
    """
    event shape from Slack Events API callback (event_callback type).
    """
    inner = event.get("event", event)
    user = inner.get("user", inner.get("username", "unknown"))
    text = inner.get("text", "")
    ts = inner.get("ts", "")
    thread_ts = inner.get("thread_ts", ts)

    received_at = datetime.now(timezone.utc).isoformat()
    if ts:
        try:
            received_at = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
        except ValueError:
            pass

    return {
        "message_id": f"slack_{ts}",
        "source": "slack",
        "sender": user,
        "subject": "",
        "body": text,
        "thread_id": thread_ts,
        "received_at": received_at,
    }


# ── Node ──────────────────────────────────────────────────────────────────────

async def ingestion_node(state: MessageState) -> dict:
    event = state["raw_event"]
    source = event.get("source", "")

    if source.startswith("gmail"):
        normalized = _parse_gmail(event)
    elif source == "slack" or "event" in event:
        normalized = _parse_slack(event)
    else:
        # Fallback: treat as slack-style if unknown
        normalized = _parse_slack(event)

    return {"normalized_message": normalized}
