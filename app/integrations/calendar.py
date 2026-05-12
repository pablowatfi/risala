"""
Google Calendar read-only integration.
Finds free slots using the freebusy API.
NEVER creates or modifies events.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.config import settings

_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _load_credentials() -> Credentials:
    import json
    with open(settings.GMAIL_WORK_TOKEN_FILE) as f:
        token_data = json.load(f)
    return Credentials.from_authorized_user_info(token_data, _SCOPES)


def _get_local_tz() -> ZoneInfo:
    import subprocess
    try:
        result = subprocess.run(["date", "+%Z"], capture_output=True, text=True)
        tz_name = result.stdout.strip()
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def _find_free_slots(
    busy_periods: list[dict],
    start: datetime,
    end: datetime,
    slot_duration_minutes: int = 60,
    count: int = 3,
) -> list[dict]:
    """Returns up to `count` free slots of `slot_duration_minutes` within [start, end]."""
    slots: list[dict] = []
    cursor = start

    while cursor + timedelta(minutes=slot_duration_minutes) <= end and len(slots) < count:
        slot_end = cursor + timedelta(minutes=slot_duration_minutes)

        # Only suggest slots during business hours (9am–6pm)
        if cursor.hour < 9 or slot_end.hour > 18:
            cursor += timedelta(minutes=30)
            continue

        # Check against busy periods
        overlaps = any(
            cursor < datetime.fromisoformat(b["end"]) and
            slot_end > datetime.fromisoformat(b["start"])
            for b in busy_periods
        )

        if not overlaps:
            local_tz = _get_local_tz()
            local_start = cursor.astimezone(local_tz)
            slots.append({
                "start": cursor.isoformat(),
                "end": slot_end.isoformat(),
                "label": local_start.strftime("%a %b %-d, %-I:%M %p"),
            })

        cursor += timedelta(minutes=30)

    return slots


async def get_free_slots(count: int = 3, lookahead_days: int = 7) -> list[dict]:
    """Fetches freebusy data and returns a list of free slot dicts."""
    try:
        creds = _load_credentials()
    except FileNotFoundError:
        return []

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=lookahead_days)

    def _fetch():
        service = build("calendar", "v3", credentials=creds)
        body = {
            "timeMin": now.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": settings.GOOGLE_CALENDAR_ID}],
        }
        return service.freebusy().query(body=body).execute()

    result = await asyncio.to_thread(_fetch)
    busy = result.get("calendars", {}).get(settings.GOOGLE_CALENDAR_ID, {}).get("busy", [])
    return _find_free_slots(busy, now, time_max, count=count)
