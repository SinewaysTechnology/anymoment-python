"""Build POST /events bodies from exact fields. No natural-language parser."""

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

from dateutil import tz as dateutil_tz
from dateutil.rrule import rrulestr

from anymoment.exceptions import ValidationError

# Integer values for RecurrentEvent.recurrence.
# The public create-event example uses 1 with days_of_week (weekly) and 4 with
# scheduled_datetime (a single occurrence). Daily, monthly, and yearly sit between
# those two. EXTERNAL_RULES is 7 and is not produced here.
DAILY = 0
WEEKLY = 1
MONTHLY = 2
YEARLY = 3
ONCE = 4

_DAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_UNSUPPORTED = {
    "BYSETPOS",
    "BYHOUR",
    "BYMINUTE",
    "BYSECOND",
    "BYYEARDAY",
    "BYWEEKNO",
    "WKST",
    "BYEASTER",
}
_MAX_COUNT = 1000


class ScheduleError(ValidationError):
    """The fields cannot be turned into a POST /events body."""

    def __init__(self, message: str):
        super().__init__(
            message,
            status_code=None,
            user_message=message,
            next_step=(
                "Check the start, end, and RRULE. "
                "For EXDATE, RDATE, or a rule this command cannot represent, use `am events import`."
            ),
        )


def build_scheduled_event(
    title: str,
    start: str,
    end: Optional[str] = None,
    all_day: bool = False,
    rrule: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """Return an AdvancedRecurrentEventCreate body.

    POST /events accepts name, description, and components. It has no location
    field, so a location is stored as a final description line.
    """
    if not title or not str(title).strip():
        raise ScheduleError("title is required.")
    if not start or not str(start).strip():
        raise ScheduleError("start is required.")
    zone = dateutil_tz.gettz(timezone) or dateutil_tz.UTC
    start_local = _as_local(start, zone, all_day)
    end_local = _as_local(end, zone, all_day) if end else None
    if end_local is not None and end_local < start_local:
        raise ScheduleError("end is before start.")

    if rrule:
        recurrence, config = _rrule_config(rrule, start_local, all_day)
    else:
        recurrence, config = _span_config(start_local, end_local, all_day)

    event_config: dict[str, Any] = {
        "recurrence": recurrence,
        "is_all_day": bool(all_day),
        "timezone": timezone or "UTC",
        "config": config,
    }
    if not all_day:
        event_config["start_time"] = start_local.strftime("%H:%M")
        if end_local is not None:
            if end_local.date() != start_local.date() and not rrule:
                raise ScheduleError(
                    "A timed event must start and end on the same day. "
                    "Use --all-day for a multi-day event."
                )
            event_config["end_time"] = end_local.strftime("%H:%M")

    body: dict[str, Any] = {
        "name": str(title).strip(),
        "components": [{"operator": "OR", "event_config": event_config}],
    }
    stored_description = _description(description, location)
    if stored_description is not None:
        body["description"] = stored_description
    return body


def record_to_kwargs(
    record: Any,
    default_timezone: str,
    default_calendar_id: Optional[str],
) -> dict[str, Any]:
    """Map one JSON object onto create_scheduled_event keyword arguments."""
    if not isinstance(record, dict):
        raise ScheduleError("Each event must be a JSON object.")
    title = record.get("title", record.get("name"))
    start = record.get("start")
    if not title or not start:
        raise ScheduleError("Each event needs a title (or name) and a start.")
    all_day = record.get("all_day", record.get("all-day", False))
    if not isinstance(all_day, bool):
        raise ScheduleError("all_day must be true or false.")
    calendar = record.get("calendar_id", record.get("calendar", default_calendar_id))
    timezone = record.get("timezone") or default_timezone or "UTC"
    return {
        "title": title,
        "start": start,
        "end": record.get("end"),
        "all_day": all_day,
        "rrule": record.get("rrule"),
        "description": record.get("description"),
        "location": record.get("location"),
        "timezone": timezone,
        "calendar_id": calendar or None,
    }


def load_event_records(text: str) -> list[Any]:
    """Read one JSON object, a JSON array, an `{events: [...]}` document, or JSONL."""
    stripped = text.strip()
    if not stripped:
        raise ScheduleError("The event file is empty.")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None
    if data is None:
        records: list[Any] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ScheduleError(f"Line {line_no} is not valid JSON.") from exc
        if not records:
            raise ScheduleError("The event file is empty.")
        return records
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        return list(data["events"])
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ScheduleError("Expected a JSON object, a JSON array, or JSONL.")


def summarize_agenda(events: list[Any]) -> dict[str, Any]:
    """Count agenda rows per calendar and per month."""
    calendars: dict[Optional[str], dict[str, Any]] = {}
    months: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0, "instances": 0})
    instance_total = 0
    for item in events:
        event = item.get("event") if isinstance(item, dict) else None
        if not isinstance(event, dict):
            event = item if isinstance(item, dict) else {}
        instances = item.get("instances") if isinstance(item, dict) else None
        if not isinstance(instances, list):
            instances = []
        instance_total += len(instances)
        calendar_ids = event.get("calendar_ids")
        if not isinstance(calendar_ids, list) or not calendar_ids:
            keys: list[Optional[str]] = [None]
        else:
            keys = [str(calendar_id) for calendar_id in calendar_ids]
        name = _calendar_name(event) if len(keys) == 1 else None
        seen_months = set()
        for key in keys:
            bucket = calendars.setdefault(
                key,
                {"calendar_id": key, "name": None, "events": 0, "instances": 0},
            )
            bucket["events"] += 1
            bucket["instances"] += len(instances)
            if name and not bucket["name"]:
                bucket["name"] = name
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            month = _month_of(instance.get("start"))
            if month is None:
                continue
            months[month]["instances"] += 1
            seen_months.add(month)
        for month in seen_months:
            months[month]["events"] += 1
    by_calendar = sorted(
        calendars.values(),
        key=lambda row: (row["calendar_id"] is None, row["calendar_id"] or ""),
    )
    by_month = [
        {"month": month, "events": counts["events"], "instances": counts["instances"]}
        for month, counts in sorted(months.items())
    ]
    return {
        "events": len(events),
        "instances": instance_total,
        "by_calendar": by_calendar,
        "by_month": by_month,
    }


def _description(description: Optional[str], location: Optional[str]) -> Optional[str]:
    text = description.strip() if isinstance(description, str) else None
    if isinstance(location, str) and location.strip():
        line = f"Location: {location.strip()}"
        return f"{text}\n{line}" if text else line
    return text or None


def _as_local(value: str, zone: Any, all_day: bool) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        if len(text) == 10:
            parsed = datetime.fromisoformat(text)
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ScheduleError(f"Could not read a date or time from {value!r}.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    else:
        parsed = parsed.astimezone(zone)
    if all_day:
        return parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed.replace(microsecond=0)


def _local_stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _span_config(
    start_local: datetime,
    end_local: Optional[datetime],
    all_day: bool,
) -> tuple[int, dict[str, Any]]:
    if (
        all_day
        and end_local is not None
        and end_local.date() > start_local.date()
    ):
        last = end_local.replace(hour=23, minute=59, second=59)
        return DAILY, {
            "interval": 1,
            "range_start": _local_stamp(start_local),
            "range_end": _local_stamp(last),
        }
    return ONCE, {"scheduled_datetime": _local_stamp(start_local)}


def _rrule_config(rrule: str, start_local: datetime, all_day: bool) -> tuple[int, dict[str, Any]]:
    text = rrule.strip()
    upper = text.upper()
    if "EXDATE" in upper or "RDATE" in upper or "EXRULE" in upper:
        raise ScheduleError("EXDATE, RDATE, and EXRULE need `am events import`.")
    if upper.startswith("RRULE:"):
        text = text.split(":", 1)[1]
    parts: dict[str, str] = {}
    for piece in text.split(";"):
        if not piece.strip():
            continue
        if "=" not in piece:
            raise ScheduleError(f"Could not read RRULE part {piece!r}.")
        key, value = piece.split("=", 1)
        name = key.strip().upper()
        if name in parts:
            raise ScheduleError(f"RRULE repeats {name}.")
        parts[name] = value.strip()
    unknown = sorted(set(parts) & _UNSUPPORTED)
    if unknown:
        raise ScheduleError(
            f"RRULE {', '.join(unknown)} is not supported by `am events add`."
        )
    freq = parts.get("FREQ", "").upper()
    if freq not in {"DAILY", "WEEKLY", "MONTHLY", "YEARLY"}:
        raise ScheduleError("RRULE needs FREQ=DAILY, WEEKLY, MONTHLY, or YEARLY.")
    if "COUNT" in parts and "UNTIL" in parts:
        raise ScheduleError("RRULE cannot set both COUNT and UNTIL.")
    interval = _positive_int(parts.get("INTERVAL"), "INTERVAL")
    config: dict[str, Any] = {}
    if freq == "DAILY":
        if "BYDAY" in parts or "BYMONTHDAY" in parts or "BYMONTH" in parts:
            raise ScheduleError("A daily RRULE cannot also set BYDAY, BYMONTHDAY, or BYMONTH.")
        recurrence = DAILY
        config = {"interval": interval}
    elif freq == "WEEKLY":
        days = _weekdays(parts.get("BYDAY"), start_local)
        recurrence = WEEKLY
        config = {"interval": interval, "days_of_week": days}
    elif freq == "MONTHLY":
        recurrence = MONTHLY
        config = {"interval": interval, **_monthly(parts, start_local)}
    else:
        recurrence = YEARLY
        config = {"interval": interval, **_yearly(parts, start_local)}
    config["range_start"] = _local_stamp(start_local)
    until = _until(parts, start_local, all_day)
    if until is not None:
        config["range_end"] = _local_stamp(until)
    return recurrence, config


def _positive_int(value: Optional[str], name: str) -> int:
    if value is None or value == "":
        return 1
    try:
        number = int(value)
    except ValueError as exc:
        raise ScheduleError(f"RRULE {name} must be a positive integer.") from exc
    if number < 1:
        raise ScheduleError(f"RRULE {name} must be a positive integer.")
    return number


def _weekdays(value: Optional[str], start_local: datetime) -> list[int]:
    if not value:
        return [start_local.weekday()]
    days = []
    for piece in value.split(","):
        ordinal, day = _byday(piece)
        if ordinal is not None:
            raise ScheduleError("A weekly RRULE cannot use a numbered weekday such as 1MO.")
        if day not in days:
            days.append(day)
    if not days:
        raise ScheduleError("RRULE BYDAY did not include a weekday.")
    return days


def _byday(value: str) -> tuple[Optional[int], int]:
    text = value.strip().upper()
    if len(text) >= 2 and text[-2:] in _DAY:
        day = _DAY[text[-2:]]
        prefix = text[:-2]
        if not prefix:
            return None, day
        try:
            return int(prefix), day
        except ValueError as exc:
            raise ScheduleError(f"Could not read BYDAY value {value!r}.") from exc
    raise ScheduleError(f"Could not read BYDAY value {value!r}.")


def _monthly(parts: dict[str, str], start_local: datetime) -> dict[str, Any]:
    if "BYMONTHDAY" in parts and "BYDAY" in parts:
        raise ScheduleError("A monthly RRULE cannot set both BYMONTHDAY and BYDAY.")
    if "BYMONTH" in parts:
        raise ScheduleError("Monthly BYMONTH is not supported by `am events add`.")
    if "BYMONTHDAY" in parts:
        days = parts["BYMONTHDAY"].split(",")
        if len(days) != 1:
            raise ScheduleError("A monthly RRULE can set one BYMONTHDAY.")
        day = _positive_int(days[0], "BYMONTHDAY")
        if day > 31:
            raise ScheduleError("BYMONTHDAY must be from 1 to 31.")
        return {"type": "day_of_month", "day": day}
    if "BYDAY" in parts:
        pieces = [piece for piece in parts["BYDAY"].split(",") if piece.strip()]
        if len(pieces) != 1:
            raise ScheduleError("A monthly RRULE can set one BYDAY.")
        ordinal, day = _byday(pieces[0])
        week = 1 if ordinal is None else ordinal
        if week == -1:
            week = 5
        if week < 1 or week > 5:
            raise ScheduleError("Monthly BYDAY ordinal must be 1, 2, 3, 4, 5, or -1.")
        return {"type": "day_of_week", "day_of_week": day, "week_of_month": week}
    return {"type": "day_of_month", "day": start_local.day}


def _yearly(parts: dict[str, str], start_local: datetime) -> dict[str, Any]:
    if "BYDAY" in parts:
        raise ScheduleError("Yearly BYDAY is not supported by `am events add`. Use `am events import`.")
    month = start_local.month
    day = start_local.day
    if "BYMONTH" in parts:
        months = parts["BYMONTH"].split(",")
        if len(months) != 1:
            raise ScheduleError("A yearly RRULE can set one BYMONTH.")
        month = _positive_int(months[0], "BYMONTH")
        if month > 12:
            raise ScheduleError("BYMONTH must be from 1 to 12.")
    if "BYMONTHDAY" in parts:
        days = parts["BYMONTHDAY"].split(",")
        if len(days) != 1:
            raise ScheduleError("A yearly RRULE can set one BYMONTHDAY.")
        day = _positive_int(days[0], "BYMONTHDAY")
        if day > 31:
            raise ScheduleError("BYMONTHDAY must be from 1 to 31.")
    return {"month": month, "day": day}


def _until(parts: dict[str, str], start_local: datetime, all_day: bool) -> Optional[datetime]:
    if "UNTIL" in parts:
        return _parse_until(parts["UNTIL"], start_local)
    if "COUNT" not in parts:
        return None
    count = _positive_int(parts["COUNT"], "COUNT")
    if count > _MAX_COUNT:
        raise ScheduleError(f"RRULE COUNT cannot be above {_MAX_COUNT}.")
    body = ";".join(f"{key}={value}" for key, value in parts.items() if key != "COUNT")
    naive = start_local.replace(tzinfo=None)
    try:
        occurrences = list(rrulestr(f"RRULE:{body};COUNT={count}", dtstart=naive))
    except (ValueError, TypeError) as exc:
        raise ScheduleError("Could not expand RRULE COUNT.") from exc
    if not occurrences:
        raise ScheduleError("RRULE COUNT produced no occurrences.")
    last = occurrences[-1]
    if all_day:
        last = last.replace(hour=23, minute=59, second=59)
    return last


def _parse_until(value: str, start_local: datetime) -> datetime:
    text = value.strip().upper()
    if len(text) == 8 and text.isdigit():
        parsed = datetime.strptime(text, "%Y%m%d")
        return parsed.replace(hour=23, minute=59, second=59)
    basic = text[:-1] if text.endswith("Z") else text
    try:
        if "T" in basic and len(basic) >= 15 and basic[8] == "T":
            parsed = datetime.strptime(basic[:15], "%Y%m%dT%H%M%S")
        else:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is not None and start_local.tzinfo is not None:
                parsed = parsed.astimezone(start_local.tzinfo).replace(tzinfo=None)
            return parsed
    except ValueError as exc:
        raise ScheduleError(f"Could not read RRULE UNTIL {value!r}.") from exc
    if text.endswith("Z") and start_local.tzinfo is not None:
        parsed = parsed.replace(tzinfo=dateutil_tz.UTC).astimezone(start_local.tzinfo)
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _month_of(value: Any) -> Optional[str]:
    if not isinstance(value, str) or len(value) < 7 or value[4] != "-":
        return None
    year, month = value[:4], value[5:7]
    if year.isdigit() and month.isdigit():
        return f"{year}-{month}"
    return None


def _calendar_name(event: dict[str, Any]) -> Optional[str]:
    origin = event.get("external_origin")
    if isinstance(origin, dict) and origin.get("calendar_name"):
        return str(origin["calendar_name"])
    for warning in event.get("sync_warnings") or []:
        if isinstance(warning, dict) and warning.get("calendar_name"):
            return str(warning["calendar_name"])
    return None
