"""Outgoing webhook contract: event types and the version 1 payload.

The server signs the canonical JSON bytes. verify_webhook still checks the
raw request body, which is those bytes on the wire.
"""

import json
from typing import Any, Optional

from anymoment.exceptions import ValidationError

PAYLOAD_VERSION = 1

EVENT_CREATED = "event.created"
EVENT_UPDATED = "event.updated"
EVENT_DELETED = "event.deleted"
OCCURRENCE_DUE = "occurrence.due"

CHANGE_TYPES = (EVENT_CREATED, EVENT_UPDATED, EVENT_DELETED, OCCURRENCE_DUE)

OFFSET_LIMIT_SECONDS = 7 * 24 * 3600
SECRET_MIN_LENGTH = 16
SECRET_MAX_LENGTH = 256

PAUSED_SUBSCRIPTION_REQUIRED = "subscription_required"

_EVENT_KEYS = ("id", "name", "description", "location", "timezone", "is_active")


def _invalid(message: str) -> ValidationError:
    return ValidationError(message, status_code=None, user_message=message)


def normalize_event_types(values: Optional[list[str]]) -> list[str]:
    if not values:
        raise _invalid(
            "Choose at least one event type: "
            + ", ".join(CHANGE_TYPES)
            + "."
        )
    cleaned: list[str] = []
    for item in values:
        if item not in CHANGE_TYPES:
            raise _invalid(
                f"Unknown event type: {item}. Use one of {', '.join(CHANGE_TYPES)}."
            )
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def normalize_offset(value: int) -> int:
    if value < -OFFSET_LIMIT_SECONDS or value > OFFSET_LIMIT_SECONDS:
        raise _invalid("Occurrence offset must be within 7 days.")
    return value


def normalize_secret(value: str) -> str:
    if not (SECRET_MIN_LENGTH <= len(value) <= SECRET_MAX_LENGTH):
        raise _invalid("Secret must be 16 to 256 characters.")
    return value


def canonical_webhook_body(payload: dict[str, Any]) -> bytes:
    """UTF-8 JSON, sorted keys, no extra whitespace. These are the signed bytes."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_webhook_payload(
    *,
    change_type: str,
    event_id: str,
    calendar_id: str,
    event: dict[str, Any],
    occurrence_time: Optional[str] = None,
) -> dict[str, Any]:
    """Version 1 delivery body.

    occurrence.due sets occurrence_time. The other change types leave it null.
    """
    if change_type not in CHANGE_TYPES:
        raise _invalid(
            f"Unknown event type: {change_type}. Use one of {', '.join(CHANGE_TYPES)}."
        )
    if change_type == OCCURRENCE_DUE and not occurrence_time:
        raise _invalid("occurrence.due needs occurrence_time.")
    snapshot = {key: event.get(key) for key in _EVENT_KEYS}
    when = occurrence_time if change_type == OCCURRENCE_DUE else None
    return {
        "version": PAYLOAD_VERSION,
        "event_id": str(event_id),
        "calendar_id": str(calendar_id),
        "change_type": change_type,
        "event": snapshot,
        "occurrence_time": when,
    }


def parse_webhook_payload(payload: Any) -> dict[str, Any]:
    """Return the payload when it is a version 1 delivery body."""
    if not isinstance(payload, dict):
        raise _invalid("Webhook payload must be a JSON object.")
    if payload.get("version") != PAYLOAD_VERSION:
        raise _invalid("Webhook payload version must be 1.")
    change_type = payload.get("change_type")
    if change_type not in CHANGE_TYPES:
        raise _invalid(
            f"Unknown event type: {change_type}. Use one of {', '.join(CHANGE_TYPES)}."
        )
    for key in ("event_id", "calendar_id"):
        if not isinstance(payload.get(key), str) or not payload.get(key):
            raise _invalid(f"Webhook payload needs {key}.")
    event = payload.get("event")
    if not isinstance(event, dict):
        raise _invalid("Webhook payload needs an event object.")
    for key in ("id", "name", "timezone", "is_active"):
        if key not in event:
            raise _invalid(f"Webhook event needs {key}.")
    when = payload.get("occurrence_time")
    if change_type == OCCURRENCE_DUE:
        if not isinstance(when, str) or not when:
            raise _invalid("occurrence.due needs occurrence_time.")
    elif when is not None:
        raise _invalid("occurrence_time is only set for occurrence.due.")
    return payload
