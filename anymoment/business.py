"""Business-day rules for POST /events.

Monthly types, roll, and the holiday calendar match the API:
last and nth business days are chosen inside the month, then roll runs.
Holiday dates come from the holidays package. This module does not invent them.
"""

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from dateutil import tz as dateutil_tz

from anymoment.exceptions import ValidationError

LAST_BUSINESS_DAY = "last_business_day"
NTH_BUSINESS_DAY = "nth_business_day"
DAY_OF_MONTH = "day_of_month"

ROLL_NONE = "none"
ROLL_FORWARD = "forward"
ROLL_BACKWARD = "backward"
ROLL_NEAREST = "nearest"
ROLL_SKIP = "skip"
ROLL_VALUES = frozenset(
    {ROLL_NONE, ROLL_FORWARD, ROLL_BACKWARD, ROLL_NEAREST, ROLL_SKIP}
)
ROLL_SEARCH_DAYS = 62
DEFAULT_WEEKEND_DAYS = (5, 6)

_RULE_ALIASES = {
    "last": LAST_BUSINESS_DAY,
    "last_business_day": LAST_BUSINESS_DAY,
    "last-business-day": LAST_BUSINESS_DAY,
    "first": NTH_BUSINESS_DAY,
    "nth": NTH_BUSINESS_DAY,
    "nth_business_day": NTH_BUSINESS_DAY,
    "nth-business-day": NTH_BUSINESS_DAY,
    "day": DAY_OF_MONTH,
    "day_of_month": DAY_OF_MONTH,
    "day-of-month": DAY_OF_MONTH,
}

_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class BusinessDayError(ValidationError):
    """The business-day fields cannot be turned into an event or a preview."""

    def __init__(self, message: str):
        super().__init__(message, status_code=None, user_message=message)


def normalize_rule(value: str) -> str:
    key = str(value or "").strip().lower()
    rule = _RULE_ALIASES.get(key)
    if rule is None:
        raise BusinessDayError(
            "Business-day rule must be last, first, nth, or day "
            "(last_business_day, nth_business_day, or day_of_month)."
        )
    return rule


def normalize_roll(value: Optional[str]) -> str:
    if value is None or str(value).strip() == "":
        return ROLL_NONE
    text = str(value).strip().lower()
    if text not in ROLL_VALUES:
        raise BusinessDayError(
            "roll must be one of none, forward, backward, nearest, skip."
        )
    return text


def normalize_weekend_days(value: Optional[Any]) -> Optional[list[int]]:
    if value is None:
        return None
    if isinstance(value, str):
        pieces = [piece.strip() for piece in value.split(",") if piece.strip()]
    elif isinstance(value, (list, tuple)):
        pieces = list(value)
    else:
        raise BusinessDayError("weekend_days must be a list of integers from 0 to 6.")
    days: list[int] = []
    for piece in pieces:
        try:
            number = int(piece)
        except (TypeError, ValueError) as exc:
            raise BusinessDayError(
                "weekend_days must be integers from 0 (Monday) through 6 (Sunday)."
            ) from exc
        if number < 0 or number > 6:
            raise BusinessDayError(
                "weekend_days must be integers from 0 (Monday) through 6 (Sunday)."
            )
        if number in days:
            raise BusinessDayError("weekend_days must not contain duplicates.")
        days.append(number)
    if len(days) >= 7:
        raise BusinessDayError("weekend_days must leave at least one working day.")
    return days


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise BusinessDayError(f"Could not read a date from {value!r}.") from exc


def _date_list(value: Optional[Any], name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [piece.strip() for piece in value.split(",") if piece.strip()]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise BusinessDayError(f"{name} must be a list of YYYY-MM-DD dates.")
    seen: list[str] = []
    for item in items:
        day = _as_date(item).isoformat()
        if day not in seen:
            seen.append(day)
    return seen


def business_calendar_payload(
    country: Optional[str] = None,
    subdiv: Optional[str] = None,
    weekend_days: Optional[Any] = None,
    closures: Optional[Any] = None,
    extra_workdays: Optional[Any] = None,
) -> Optional[dict[str, Any]]:
    """Return a BusinessCalendar object, or None when the caller set nothing."""
    weekends = normalize_weekend_days(weekend_days)
    closed = _date_list(closures, "closures")
    extra = _date_list(extra_workdays, "extra_workdays")
    country_code = None
    if country is not None and str(country).strip():
        country_code = str(country).strip().upper()
        if len(country_code) != 2 or not country_code.isalpha():
            raise BusinessDayError("country must be an ISO 3166-1 alpha-2 code, such as ES.")
    subdiv_code = None
    if subdiv is not None and str(subdiv).strip():
        subdiv_code = str(subdiv).strip()
    if country_code is None and subdiv_code is None and weekends is None and not closed and not extra:
        return None
    if country_code:
        _assert_supported_country(country_code, subdiv_code)
    elif subdiv_code:
        raise BusinessDayError("subdiv needs a country code.")
    payload: dict[str, Any] = {}
    if country_code is not None:
        payload["country"] = country_code
    if subdiv_code is not None:
        payload["subdiv"] = subdiv_code
    if weekends is not None:
        payload["weekend_days"] = weekends
    if closed:
        payload["closures"] = closed
    if extra:
        payload["extra_workdays"] = extra
    return payload


class _Calendar:
    def __init__(self, payload: Optional[dict[str, Any]]):
        data = payload or {}
        weekends = data.get("weekend_days", list(DEFAULT_WEEKEND_DAYS))
        self.country = data.get("country")
        self.subdiv = data.get("subdiv")
        self.weekend_days = frozenset(int(day) for day in weekends)
        self.closures = frozenset(_as_date(item) for item in data.get("closures") or [])
        self.extra_workdays = frozenset(
            _as_date(item) for item in data.get("extra_workdays") or []
        )


def _holidays_module():
    try:
        import holidays
    except ImportError as exc:  # pragma: no cover
        raise BusinessDayError(
            "The holidays package is not installed. Install anymoment to preview business days."
        ) from exc
    return holidays


def _assert_supported_country(country: str, subdiv: Optional[str]) -> None:
    holidays = _holidays_module()
    try:
        holidays.country_holidays(country, subdiv=subdiv or None, years=date.today().year)
    except NotImplementedError as exc:
        raise BusinessDayError(str(exc)) from exc
    except Exception as exc:
        raise BusinessDayError(
            f"Country {country} is not a holiday calendar this package can load."
        ) from exc


def _is_bank_holiday(day: date, country: Optional[str], subdiv: Optional[str]) -> bool:
    if not country:
        return False
    holidays = _holidays_module()
    calendar_year = holidays.country_holidays(country, subdiv=subdiv or None, years=day.year)
    return day in calendar_year


def is_business_day(day: date, spec: _Calendar) -> bool:
    """extra_workdays win over closures, weekends, and holidays."""
    if day in spec.extra_workdays:
        return True
    if day in spec.closures:
        return False
    if day.weekday() in spec.weekend_days:
        return False
    if spec.country and _is_bank_holiday(day, spec.country, spec.subdiv):
        return False
    return True


def business_days_in_month(year: int, month: int, spec: _Calendar) -> list[date]:
    last = calendar.monthrange(year, month)[1]
    return [
        date(year, month, day)
        for day in range(1, last + 1)
        if is_business_day(date(year, month, day), spec)
    ]


def nth_business_day(
    year: int,
    month: int,
    n: int,
    from_end: bool,
    spec: _Calendar,
) -> Optional[date]:
    if n < 1:
        return None
    days = business_days_in_month(year, month, spec)
    index = len(days) - n if from_end else n - 1
    if index < 0 or index >= len(days):
        return None
    return days[index]


def roll_date(day: date, roll: str, spec: _Calendar) -> Optional[date]:
    roll = normalize_roll(roll)
    if roll == ROLL_NONE:
        return day
    if is_business_day(day, spec):
        return day
    if roll == ROLL_SKIP:
        return None
    if roll == ROLL_FORWARD:
        return _seek(day, 1, spec)
    if roll == ROLL_BACKWARD:
        return _seek(day, -1, spec)
    for step in range(1, ROLL_SEARCH_DAYS + 1):
        later = day + timedelta(days=step)
        earlier = day - timedelta(days=step)
        if is_business_day(later, spec):
            return later
        if is_business_day(earlier, spec):
            return earlier
    return None


def _seek(day: date, step: int, spec: _Calendar) -> Optional[date]:
    cursor = day
    for _ in range(ROLL_SEARCH_DAYS):
        cursor += timedelta(days=step)
        if is_business_day(cursor, spec):
            return cursor
    return None


def monthly_config(
    rule: str,
    *,
    interval: int = 1,
    nth: Optional[int] = None,
    from_end: Optional[bool] = None,
    day: Optional[int] = None,
    range_start: Optional[str] = None,
    range_end: Optional[str] = None,
) -> dict[str, Any]:
    """MonthlyScheduleConfig for a business-day or day-of-month rule."""
    alias = str(rule).strip().lower()
    kind = normalize_rule(rule)
    if interval < 1:
        raise BusinessDayError("interval must be a positive integer.")
    config: dict[str, Any] = {"interval": interval, "type": kind}
    if kind == LAST_BUSINESS_DAY:
        pass
    elif kind == NTH_BUSINESS_DAY:
        number = 1 if alias == "first" and nth is None else nth
        if number is None:
            raise BusinessDayError("nth business day needs n, the count from the start or the end.")
        if number < 1 or number > 31:
            raise BusinessDayError("n must be from 1 to 31.")
        config["n"] = int(number)
        config["from_end"] = bool(from_end)
    else:
        if day is None:
            raise BusinessDayError("day of month needs day, from 1 to 31.")
        if day < 1 or day > 31:
            raise BusinessDayError("day must be from 1 to 31.")
        config["day"] = int(day)
    if range_start:
        config["range_start"] = range_start
    if range_end:
        config["range_end"] = range_end
    return config


def _month_date(
    year: int,
    month: int,
    rule: str,
    spec: _Calendar,
    *,
    nth: Optional[int],
    from_end: bool,
    day: Optional[int],
    roll: str,
) -> Optional[date]:
    kind = normalize_rule(rule)
    alias = str(rule).strip().lower()
    if kind == LAST_BUSINESS_DAY:
        chosen = nth_business_day(year, month, 1, True, spec)
    elif kind == NTH_BUSINESS_DAY:
        number = 1 if alias == "first" and nth is None else nth
        if number is None:
            raise BusinessDayError("nth business day needs n.")
        chosen = nth_business_day(year, month, int(number), from_end, spec)
    else:
        if day is None:
            raise BusinessDayError("day of month needs day.")
        last = calendar.monthrange(year, month)[1]
        if day > last:
            return None
        chosen = date(year, month, int(day))
    if chosen is None:
        return None
    return roll_date(chosen, roll, spec)


def _add_months(year: int, month: int, step: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1


def preview_occurrences(
    rule: str,
    *,
    start: Any,
    end: Any,
    timezone: str = "UTC",
    at: Optional[str] = None,
    interval: int = 1,
    nth: Optional[int] = None,
    from_end: bool = False,
    day: Optional[int] = None,
    roll: str = ROLL_NONE,
    country: Optional[str] = None,
    subdiv: Optional[str] = None,
    weekend_days: Optional[Any] = None,
    closures: Optional[Any] = None,
    extra_workdays: Optional[Any] = None,
) -> dict[str, Any]:
    """Expand one monthly rule. This does not call the API.

    start and end are inclusive calendar dates. at is HH:MM in timezone.
    """
    window_start = _as_date(start)
    window_end = _as_date(end)
    if window_end < window_start:
        raise BusinessDayError("The preview end is before the start.")
    if interval < 1:
        raise BusinessDayError("interval must be a positive integer.")
    roll_value = normalize_roll(roll)
    calendar_body = business_calendar_payload(
        country=country,
        subdiv=subdiv,
        weekend_days=weekend_days,
        closures=closures,
        extra_workdays=extra_workdays,
    )
    spec = _Calendar(calendar_body)
    clock = _parse_clock(at) if at else None
    zone = dateutil_tz.gettz(timezone)
    if zone is None:
        raise BusinessDayError(f"Unknown timezone {timezone!r}.")
    occurrences = []
    year, month = window_start.year, window_start.month
    while True:
        current = date(year, month, 1)
        if current > window_end:
            break
        chosen = _month_date(
            year,
            month,
            rule,
            spec,
            nth=nth,
            from_end=from_end,
            day=day,
            roll=roll_value,
        )
        if chosen is not None and window_start <= chosen <= window_end:
            row: dict[str, Any] = {
                "date": chosen.isoformat(),
                "weekday": _WEEKDAY_NAMES[chosen.weekday()],
            }
            if clock is not None:
                local = datetime.combine(chosen, clock, tzinfo=zone)
                row["local_start"] = local.strftime("%Y-%m-%dT%H:%M:%S")
                row["utc_start"] = local.astimezone(dateutil_tz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            occurrences.append(row)
        year, month = _add_months(year, month, interval)
    return {
        "rule": normalize_rule(rule) if str(rule).strip().lower() != "first" else NTH_BUSINESS_DAY,
        "label": _label(rule, nth=nth, from_end=from_end, day=day),
        "country": spec.country,
        "subdiv": spec.subdiv,
        "timezone": timezone,
        "time": clock.strftime("%H:%M") if clock else None,
        "roll": roll_value,
        "interval": interval,
        "weekend_days": sorted(spec.weekend_days),
        "occurrences": occurrences,
    }


def _label(rule: str, *, nth: Optional[int], from_end: bool, day: Optional[int]) -> str:
    alias = str(rule).strip().lower()
    kind = normalize_rule(rule)
    if kind == LAST_BUSINESS_DAY or (kind == NTH_BUSINESS_DAY and from_end and nth == 1):
        return "last business day of the month"
    if alias == "first" or (kind == NTH_BUSINESS_DAY and not from_end and (nth in (None, 1))):
        return "first business day of the month"
    if kind == NTH_BUSINESS_DAY:
        direction = "from the end" if from_end else "of the month"
        return f"business day {nth} {direction}"
    return f"day {day} of the month"


def _parse_clock(value: str) -> time:
    text = str(value).strip()
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise BusinessDayError("time must be HH:MM.") from exc
    return time(parsed.hour, parsed.minute)
