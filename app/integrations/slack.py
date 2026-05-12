"""
Slack SDK wrapper — posting messages and verifying request signatures.
"""
import hashlib
import hmac
import time
from slack_sdk.web.async_client import AsyncWebClient
from app.config import settings

_client: AsyncWebClient | None = None


def get_slack_client() -> AsyncWebClient:
    global _client
    if _client is None:
        _client = AsyncWebClient(token=settings.SLACK_BOT_TOKEN)
    return _client


async def post_alert(channel: str, blocks: list[dict], fallback_text: str = "") -> None:
    client = get_slack_client()
    await client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text=fallback_text,
    )


async def post_message(channel: str, text: str) -> None:
    client = get_slack_client()
    await client.chat_postMessage(channel=channel, text=text)


def verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Returns True if the request genuinely came from Slack."""
    if abs(time.time() - float(timestamp)) > 300:
        return False  # replay attack window

    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
