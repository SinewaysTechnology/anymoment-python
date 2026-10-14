"""Small natural-date window parser for the CLI.

Understands today, tomorrow, tomorrow 3pm, next fri, this week, next week,
and ISO-8601 timestamps. Resolved instants are returned in UTC.
"""

import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from dateutil import tz as dateutil_tz

_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

_ISO = re.compile(
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?"
)
_CLOCK = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)")


class DateParseError(ValueError):
    """The text is not a window this parser understands."""


def _zone(tz_name: str):
    return dateutil_tz.gettz(tz_name) or dateutil_tz.UTC


def to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str, tz) -> datetime:
    cleaned = text.strip().replace("Z", "+00:00")
    if "T" not in cleaned and " " not in cleaned:
        day = datetime.fromisoformat(cleaned).date()
        return datetime.combine(day, time.min, tzinfo=tz)
    if " " in cleaned and "T" not in cleaned:
        cleaned = cleaned.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _clock(match: re.Match) -> tuple[int, int]:
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise DateParseError("Clock time is out of range.")
    return hour, minute


def _day_bounds(day, tz) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day, time(23, 59, 59), tzinfo=tz)
    return start, end


def _week_bounds(monday, tz) -> tuple[datetime, datetime]:
    sunday = monday + timedelta(days=6)
    start = datetime.combine(monday, time.min, tzinfo=tz)
    end = datetime.combine(sunday, time(23, 59, 59), tzinfo=tz)
    return start, end


def resolve_window(
    text: str,
    tz_name: str = "UTC",
    now: Optional[datetime] = None,
) -> tuple[str, str]:
    """Return UTC ISO start and end for a natural or ISO window."""
    tz = _zone(tz_name)
    if now is None:
        current = datetime.now(tz)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=tz)
    else:
        current = now.astimezone(tz)

    raw = text.strip()
    lowered = re.sub(r"\s+", " ", raw.lower())
    if not lowered:
        raise DateParseError("A date window is required.")

    iso_hits = _ISO.findall(raw)
    if iso_hits and not any(word in lowered for word in ("today", "tomorrow", "next", "this week")):
        start = _parse_iso(iso_hits[0], tz)
        if len(iso_hits) >= 2:
            end = _parse_iso(iso_hits[1], tz)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso_hits[0]):
            end = _day_bounds(start.date(), tz)[1]
        else:
            end = start + timedelta(hours=1)
        return to_utc_iso(start), to_utc_iso(end)

    if lowered in {"today"}:
        start, end = _day_bounds(current.date(), tz)
        return to_utc_iso(start), to_utc_iso(end)
    if lowered in {"tomorrow"}:
        start, end = _day_bounds(current.date() + timedelta(days=1), tz)
        return to_utc_iso(start), to_utc_iso(end)
    if lowered in {"this week", "week"}:
        monday = current.date() - timedelta(days=current.weekday())
        start, end = _week_bounds(monday, tz)
        return to_utc_iso(start), to_utc_iso(end)
    if lowered in {"next week"}:
        monday = current.date() - timedelta(days=current.weekday()) + timedelta(days=7)
        start, end = _week_bounds(monday, tz)
        return to_utc_iso(start), to_utc_iso(end)

    tomorrow_clock = re.fullmatch(r"tomorrow\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", lowered)
    if tomorrow_clock:
        hour, minute = _clock(tomorrow_clock)
        start = datetime.combine(
            current.date() + timedelta(days=1),
            time(hour, minute),
            tzinfo=tz,
        )
        return to_utc_iso(start), to_utc_iso(start + timedelta(hours=1))

    next_day = re.fullmatch(r"next\s+([a-z]+)", lowered)
    if next_day and next_day.group(1) in _WEEKDAYS:
        target = _WEEKDAYS[next_day.group(1)]
        delta = (target - current.weekday()) % 7
        if delta == 0:
            delta = 7
        start, end = _day_bounds(current.date() + timedelta(days=delta), tz)
        return to_utc_iso(start), to_utc_iso(end)

    raise DateParseError(
        "Use a phrase like 'tomorrow 3pm', 'next fri', 'next week', or an ISO timestamp."
    )
