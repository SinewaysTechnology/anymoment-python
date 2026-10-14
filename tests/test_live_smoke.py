"""Read-only live smoke. Skips unless both secrets are present.

Calls GET /auth/me and GET /agenda only. No writes, no admin routes.
"""

import os
from datetime import datetime, time, timezone

import pytest

from anymoment.client import Client

pytestmark = pytest.mark.live

_MISSING = not os.getenv("ANYMOMENT_BASE_URL") or not os.getenv("ANYMOMENT_TEST_TOKEN")
_SKIP = pytest.mark.skipif(_MISSING, reason="ANYMOMENT_BASE_URL or ANYMOMENT_TEST_TOKEN is not set")


def _client():
    return Client(
        api_url=os.environ["ANYMOMENT_BASE_URL"],
        token=os.environ["ANYMOMENT_TEST_TOKEN"],
    )


def _items(result, name):
    if isinstance(result, dict):
        return result[name]
    return getattr(result, name)


@_SKIP
def test_live_me_is_read_only():
    user = _client().get_user_info()
    assert isinstance(user, dict)
    assert user.get("email") or user.get("id")


@_SKIP
def test_live_agenda_returns_events_and_failures():
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end = datetime.combine(today, time(23, 59, 59), tzinfo=timezone.utc)
    result = _client().get_agenda(start=start, end=end)
    events = _items(result, "events")
    failures = _items(result, "failures")
    assert isinstance(events, list)
    assert isinstance(failures, list)
