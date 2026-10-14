"""Helpers for the 2.0 contract tests.

Fixtures in tests/fixtures are the response shapes the SDK must honor.
`pending` marks behavior the 1.0 client does not implement yet.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
API = "https://api.test.anymoment"

# CLI exit codes the 2.0 command surface uses.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 3
EXIT_NOT_FOUND = 4
EXIT_VALIDATION = 5
EXIT_PERMISSION = 6
EXIT_RATE_LIMIT = 7
EXIT_PARTIAL = 8
EXIT_UPSTREAM = 9
EXIT_NETWORK = 10

EVENT_ID = "660e8400-e29b-41d4-a716-446655440001"
CALENDAR_ID = "550e8400-e29b-41d4-a716-446655440000"

SYNC_WARNING_KEYS = {
    "reason",
    "event_name",
    "calendar_name",
    "user_message",
    "next_step",
}
EXPORT_WARNING_KEYS = {"reason", "account_email", "user_message"}
FAILURE_KEYS = {"event_id", "event_name", "message", "reason", "is_google_synced"}
ERROR_JSON_KEYS = {"code", "status", "user_message", "next_step", "retry_after"}


def pending(reason: str):
    """Checklist row. strict=True fails CI if the test starts passing.

    Remove the marker in the same change that implements the behavior.
    """
    return pytest.mark.xfail(strict=True, reason=f"2.0: {reason}")


def load_fixture(name: str):
    """Load a vendored JSON document or a text body."""
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return text


def field(obj, name):
    """Read a response field from either a dict or an attribute object."""
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def require_attr(obj, name):
    """2.0 result objects expose attributes. A raw dict or None does not count."""
    if obj is None or isinstance(obj, dict):
        pytest.fail(
            f"expected an object with .{name}, got {type(obj).__name__}. "
            "2.0 returns a result object rather than the raw JSON dict."
        )
    return getattr(obj, name)


def exception_type(name: str):
    """Return a 2.0 exception class, or fail the test if it is not defined yet."""
    from anymoment import exceptions

    cls = getattr(exceptions, name, None)
    if cls is None:
        pytest.fail(f"{name} is not defined")
    return cls


class Payload(dict):
    """Dict that also supports attribute access.

    CLI tests use this so the command can read either style while the
    assertions stay on the JSON the process prints.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc
