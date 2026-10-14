"""Verify an AnyMoment webhook delivery.

The signature is hex HMAC-SHA256 over the exact string ``{timestamp}.{raw body}``.
``X-AnyMoment-Delivery`` identifies the attempt. It is not part of the signature.
"""

import hashlib
import hmac
from typing import Mapping, Optional, Union

SIGNATURE_HEADER = "X-AnyMoment-Signature"
TIMESTAMP_HEADER = "X-AnyMoment-Timestamp"
DELIVERY_HEADER = "X-AnyMoment-Delivery"

DEFAULT_TOLERANCE_SECONDS = 300

Payload = Union[bytes, str]


def _payload_bytes(payload: Payload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    return payload.encode("utf-8")


def webhook_signature(secret: str, timestamp: str, payload: Payload) -> str:
    """Hex HMAC-SHA256 of ``{timestamp}.{raw body}``."""
    message = timestamp.encode("utf-8") + b"." + _payload_bytes(payload)
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted and value is not None:
            text = str(value).strip()
            return text or None
    return None


def delivery_id(headers: Mapping[str, str]) -> Optional[str]:
    """Value of X-AnyMoment-Delivery, if the request sent one."""
    return _header(headers, DELIVERY_HEADER)


def verify_signature(
    payload: Payload,
    secret: str,
    signature: str,
    timestamp: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Return True when the signature matches and the timestamp is fresh.

    Pass the raw request body. Re-encoding JSON changes the bytes and the
    signature will not match. ``now`` is the current unix time, for tests.
    """
    if not secret or not signature or not timestamp:
        return False
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    if now is None:
        import time

        now = time.time()
    if abs(now - sent_at) > tolerance_seconds:
        return False
    expected = webhook_signature(secret, timestamp, payload)
    try:
        return hmac.compare_digest(expected, signature.strip().lower())
    except (TypeError, ValueError):
        return False


def verify_webhook(
    payload: Payload,
    headers: Mapping[str, str],
    secret: str,
    *,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: Optional[float] = None,
) -> bool:
    """Verify X-AnyMoment-Signature against X-AnyMoment-Timestamp and the raw body."""
    signature = _header(headers, SIGNATURE_HEADER)
    timestamp = _header(headers, TIMESTAMP_HEADER)
    if signature is None or timestamp is None:
        return False
    return verify_signature(
        payload,
        secret,
        signature,
        timestamp,
        tolerance_seconds=tolerance_seconds,
        now=now,
    )
