"""occurrence.due payload, signature bytes, and subscription gates."""

import json

import pytest
import responses

from anymoment.client import Client
from anymoment.exceptions import AuthenticationError, SubscriptionRequiredError, ValidationError
from anymoment.signatures import verify_webhook, webhook_signature
from anymoment.webhooks import (
    OCCURRENCE_DUE,
    build_webhook_payload,
    canonical_webhook_body,
    parse_webhook_payload,
)

from tests.support import API, CALENDAR_ID, load_fixture


def test_occurrence_due_payload_is_canonical_and_signed():
    payload = build_webhook_payload(
        change_type=OCCURRENCE_DUE,
        event_id="660e8400-e29b-41d4-a716-446655440001",
        calendar_id=CALENDAR_ID,
        event={
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "name": "Month-end close",
            "description": None,
            "location": None,
            "timezone": "Europe/Madrid",
            "is_active": True,
        },
        occurrence_time="2026-11-30T08:00:00+00:00",
    )
    recorded = load_fixture("occurrence_due_payload.json")
    assert payload == recorded
    raw = canonical_webhook_body(payload)
    assert raw == json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    parsed = parse_webhook_payload(json.loads(raw))
    assert parsed["change_type"] == "occurrence.due"
    secret = "whsec_shown_once"
    timestamp = "1760000000"
    signature = webhook_signature(secret, timestamp, raw)
    assert verify_webhook(
        raw,
        {
            "X-AnyMoment-Signature": signature,
            "X-AnyMoment-Timestamp": timestamp,
            "X-AnyMoment-Delivery": "880e8400-e29b-41d4-a716-446655440011",
        },
        secret,
        now=1760000000,
    )


def test_unknown_event_type_is_rejected_before_http(mock_token_file):
    client = Client(api_url=API, api_key="am_live_0123abcd_secret")
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        with pytest.raises(ValidationError) as exc_info:
            client.create_subscription(
                CALENDAR_ID,
                url="https://example.com/hooks/anymoment",
                event_types=["not.a.type"],
            )
        assert len(rsps.calls) == 0
    assert "occurrence.due" in exc_info.value.user_message


def test_missing_token_422_is_authentication_error(mock_token_file):
    body = load_fixture("recorded_missing_token_422.json")
    client = Client(api_url=API)
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/events/from-recurrence-text/preview",
            json=body,
            status=422,
        )
        with pytest.raises(AuthenticationError) as exc_info:
            client.preview_event_from_text(
                name="Payroll",
                recurrence_text="last business day of the month, Spain holidays",
                start="2026-01-01T00:00:00Z",
                end="2026-06-30T00:00:00Z",
                timezone="Europe/Madrid",
            )
    err = exc_info.value
    assert err.status_code == 422
    assert "ANYMOMENT_API_KEY" in err.next_step


def test_subscription_required_403_and_402(mock_token_file):
    client = Client(api_url=API, token="test-token")
    forbidden = load_fixture("subscription_required_403.json")
    payment = load_fixture("subscription_required_402.json")
    with responses.RequestsMock(assert_all_requests_are_fired=True) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}/webhook-url", json=forbidden, status=403)
        rsps.add(responses.POST, f"{API}/calendars/{CALENDAR_ID}/subscriptions", json=payment, status=402)
        with pytest.raises(SubscriptionRequiredError) as denied:
            client.get_calendar_webhook_url(CALENDAR_ID)
        with pytest.raises(SubscriptionRequiredError) as paid:
            client.create_subscription(
                CALENDAR_ID,
                url="https://example.com/hooks/anymoment",
                event_types=["occurrence.due"],
            )
    assert denied.value.status_code == 403
    assert denied.value.code == "subscription_required"
    assert "active trial" in denied.value.next_step
    assert paid.value.status_code == 402
    assert paid.value.code == "subscription_required"
