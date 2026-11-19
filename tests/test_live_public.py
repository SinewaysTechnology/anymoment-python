"""Unauthenticated checks against the production API.

Authenticated expansion, subscription create, and instance lists need a key.
Those are covered with recorded bodies in the default suite.
"""

import os

import pytest
import requests

pytestmark = pytest.mark.live

API = os.environ.get("ANYMOMENT_BASE_URL", "https://api.anymoment.sineways.tech").rstrip("/")


def test_live_health_and_root():
    health = requests.get(f"{API}/health", timeout=20)
    root = requests.get(f"{API}/", timeout=20)
    assert health.status_code == 200
    assert health.json().get("status") == "healthy"
    assert root.status_code == 200
    assert "AnyMoment" in root.json().get("message", "")


def test_live_openapi_has_business_days_and_subscriptions():
    spec = requests.get(f"{API}/openapi.json", timeout=30).json()
    schemas = spec["components"]["schemas"]
    assert "last_business_day" in schemas["MonthlyType"]["enum"]
    assert "nth_business_day" in schemas["MonthlyType"]["enum"]
    assert set(schemas["BusinessDayRoll"]["enum"]) == {
        "none",
        "forward",
        "backward",
        "nearest",
        "skip",
    }
    calendar = schemas["BusinessCalendar"]["properties"]
    assert {"country", "subdiv", "weekend_days", "closures", "extra_workdays"} <= set(calendar)
    create = schemas["AdvancedRecurrentEventCreate"]["properties"]
    assert "roll" in create and "business_calendar" in create
    subscription = schemas["SubscriptionOut"]["properties"]
    assert "paused_reason" in subscription
    assert "occurrence_offset_seconds" in schemas["SubscriptionCreate"]["properties"]


def test_live_preview_and_subscription_require_a_credential():
    preview = requests.post(
        f"{API}/events/from-recurrence-text/preview",
        json={
            "name": "Payroll",
            "recurrence_text": "last business day of the month, Spain holidays",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-06-30T00:00:00Z",
            "timezone": "Europe/Madrid",
        },
        timeout=20,
    )
    created = requests.post(
        f"{API}/calendars/00000000-0000-4000-8000-000000000001/subscriptions",
        json={"url": "https://example.com/hook", "event_types": ["occurrence.due"]},
        timeout=20,
    )
    bad_key = requests.get(
        f"{API}/calendars",
        params={"limit": 1},
        headers={"Authorization": "Bearer am_live_00000000_notasecret"},
        timeout=20,
    )
    assert preview.status_code == 422
    assert created.status_code == 422
    assert preview.json()["detail"][0]["loc"][-1] == "x-auth-token"
    assert created.json()["detail"][0]["loc"][-1] == "x-auth-token"
    assert bad_key.status_code == 401
    assert bad_key.json()["detail"]["code"] == "invalid_api_key"
