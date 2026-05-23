"""
Gmail integration — OAuth token management and message fetching.
Uses scheduled polling (3×/day) instead of push notifications.
NEVER sends email.
"""
import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from app.config import settings

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",  # labeling only
]

_ACCOUNTS = {
    "gmail_work": {
        "token_file": settings.GMAIL_WORK_TOKEN_FILE,
        "address": settings.GMAIL_WORK_ADDRESS,
    },
    "gmail_personal": {
        "token_file": settings.GMAIL_PERSONAL_TOKEN_FILE,
        "address": settings.GMAIL_PERSONAL_ADDRESS,
    },
}


def _load_or_refresh_creds(token_file: str) -> Credentials | None:
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, _SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds if creds and creds.valid else None


def run_oauth_flow(account: str) -> None:
    """Run once interactively to get tokens. Call from CLI, not from the app."""
    token_file = _ACCOUNTS[account]["token_file"]
    flow = InstalledAppFlow.from_client_secrets_file(settings.GMAIL_CREDENTIALS_FILE, _SCOPES)
    creds = flow.run_local_server(port=0)
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, "w") as f:
        f.write(creds.to_json())


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _parse_gmail_message(raw_msg: dict, source: str) -> dict:
    raw_data = base64.urlsafe_b64decode(raw_msg["raw"] + "==")
    parsed = message_from_bytes(raw_data)

    date_str = parsed.get("Date", "")
    try:
        from email.utils import parsedate_to_datetime
        received_at = parsedate_to_datetime(date_str).astimezone(timezone.utc).isoformat()
    except Exception:
        received_at = datetime.now(timezone.utc).isoformat()

    return {
        "source": source,
        "message_id": raw_msg["id"],
        "thread_id": raw_msg.get("threadId", ""),
        "sender": _decode_header_value(parsed.get("From", "")),
        "subject": _decode_header_value(parsed.get("Subject", "")),
        "body": _extract_body(parsed),
        "received_at": received_at,
    }


async def fetch_message(message_id: str, source: str) -> dict | None:
    """Fetch a single Gmail message by ID for the given account source."""
    token_file = _ACCOUNTS[source]["token_file"]
    creds = await asyncio.to_thread(_load_or_refresh_creds, token_file)
    if not creds:
        return None

    def _fetch():
        service = build("gmail", "v1", credentials=creds)
        return service.users().messages().get(
            userId="me", id=message_id, format="raw"
        ).execute()

    raw_msg = await asyncio.to_thread(_fetch)
    return _parse_gmail_message(raw_msg, source)


async def get_current_history_id(source: str) -> str | None:
    """Return the current historyId for an account (used to bookmark position on first run)."""
    token_file = _ACCOUNTS[source]["token_file"]
    creds = await asyncio.to_thread(_load_or_refresh_creds, token_file)
    if not creds:
        return None

    def _fetch():
        service = build("gmail", "v1", credentials=creds)
        return service.users().getProfile(userId="me").execute().get("historyId")

    return await asyncio.to_thread(_fetch)


async def fetch_messages_since(history_id: str, source: str) -> tuple[list[dict], str | None]:
    """
    Fetch messages added since history_id for the given account.
    Returns (messages, new_history_id). new_history_id should be stored for the next poll.
    Returns ([], None) if credentials are unavailable or history is too old.
    """
    token_file = _ACCOUNTS[source]["token_file"]
    creds = await asyncio.to_thread(_load_or_refresh_creds, token_file)
    if not creds:
        return [], None

    def _fetch():
        service = build("gmail", "v1", credentials=creds)
        try:
            response = service.users().history().list(
                userId="me",
                startHistoryId=history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX",
            ).execute()
        except Exception:
            # historyId too old or invalid — caller should reset
            return [], None

        messages = []
        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added["message"]["id"]
                raw = service.users().messages().get(
                    userId="me", id=msg_id, format="raw"
                ).execute()
                messages.append(_parse_gmail_message(raw, source))

        new_history_id = response.get("historyId")
        return messages, new_history_id

    return await asyncio.to_thread(_fetch)
