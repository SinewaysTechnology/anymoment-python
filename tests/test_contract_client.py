"""SDK contract for the shapes in tests/fixtures.

Passing tests cover behavior 1.0 already matches.
`pending` tests are the 2.0 checklist: they fail until the client grows
the result objects, the error fields, and resend_verification().
"""

import pytest
import responses

from anymoment.client import Client
from anymoment.exceptions import AuthenticationError

from tests.support import (
    API,
    CALENDAR_ID,
    EVENT_ID,
    exception_type,
    field,
    load_fixture,
    pending,
    require_attr,
)


@pytest.fixture
def client(mock_token_file):
    return Client(api_url=API, token="test-token")


def _calls(rsps, suffix):
    return [
        call
        for call in rsps.calls
        if call.request.url.split("?")[0].rstrip("/").endswith(suffix)
    ]


def _status(result, body):
    if isinstance(result, dict):
        return result["status"]
    return result.status


def test_recorded_invalid_token_raises_authentication_error(client):
    """A captured 401 detail string stays on AuthenticationError.message.

    AnyMoment token 401s refresh once, then surface the original error.
    """
    body = load_fixture("recorded_invalid_token_401.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.GET,
            f"{API}/auth/token/extend",
            body='"refreshed-token"',
            status=200,
        )
        rsps.add(responses.GET, f"{API}/auth/me", json=body, status=401)
        with pytest.raises(AuthenticationError) as exc_info:
            client.get_user_info()
        assert len(_calls(rsps, "/auth/token/extend")) == 1
        assert len(_calls(rsps, "/auth/me")) == 2
    assert exc_info.value.status_code == 401
    assert exc_info.value.message == "Invalid token"


def test_login_failure_does_not_refresh(mock_token_file):
    """Login handles its own 401. It must not call token extend."""
    client = Client(api_url=API)
    body = load_fixture("recorded_invalid_token_401.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/token", json=body, status=401)
        rsps.add(
            responses.GET,
            f"{API}/auth/token/extend",
            body='"refreshed-token"',
            status=200,
        )
        with pytest.raises(AuthenticationError):
            client.login("user@example.com", "wrong-password")
        assert _calls(rsps, "/auth/token/extend") == []


@pending("get_agenda returns an object with .events and .failures")
def test_get_agenda_exposes_events_and_failures(client):
    body = load_fixture("agenda_batch.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/agenda", json=body, status=200)
        result = client.get_agenda(
            start="2026-10-14T00:00:00Z",
            end="2026-10-14T23:59:59Z",
        )
    events = require_attr(result, "events")
    failures = require_attr(result, "failures")
    assert field(field(events[0], "event"), "display_name") == "Team standup"
    assert field(field(events[1], "event"), "external_origin")["read_only"] is True
    assert field(failures[0], "event_id") == body["failures"][0]["event_id"]
    assert field(failures[0], "event_name") == "Imported dentist"
    assert field(failures[0], "message") == "Could not expand this event."
    assert field(failures[0], "is_google_synced") is True


@pending("top-level user_message and next_step are parsed, not stringified")
def test_top_level_user_message_and_next_step(client):
    body = load_fixture("resend_502.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}", json=body, status=502)
        with pytest.raises(Exception) as exc_info:
            client.get_calendar(CALENDAR_ID)
    err = exc_info.value
    assert err.status_code == 502
    assert err.user_message == body["user_message"]
    assert err.next_step == body["next_step"]
    assert err.message == body["user_message"]


@pending("CalDAV detail {code, message, next_step} maps onto code, user_message, and next_step")
def test_caldav_error_fields(client):
    body = load_fixture("error_caldav.json")
    detail = body["detail"]
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/caldav/accounts", json=body, status=401)
        rsps.add(
            responses.GET,
            f"{API}/auth/token/extend",
            body='"refreshed-token"',
            status=200,
        )
        with pytest.raises(Exception) as exc_info:
            client._request("GET", "/caldav/accounts")
    err = exc_info.value
    assert err.status_code == 401
    assert err.code == detail["code"]
    assert err.user_message == detail["message"]
    assert err.next_step == detail["next_step"]


@pending("a CalDAV auth_failed 401 does not refresh the AnyMoment token")
def test_caldav_auth_failed_does_not_refresh(client):
    body = load_fixture("error_caldav.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/caldav/accounts", json=body, status=401)
        rsps.add(
            responses.GET,
            f"{API}/auth/token/extend",
            body='"refreshed-token"',
            status=200,
        )
        with pytest.raises(Exception):
            client._request("GET", "/caldav/accounts")
        assert _calls(rsps, "/auth/token/extend") == []


@pending("422 validation errors raise UnprocessableError and keep the detail list")
def test_recorded_422_is_unprocessable(client):
    body = load_fixture("recorded_agenda_422.json")
    unprocessable = exception_type("UnprocessableError")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/agenda", json=body, status=422)
        with pytest.raises(unprocessable) as exc_info:
            client.get_agenda(start="2026-10-14T00:00:00Z", end="2026-10-14T23:59:59Z")
    err = exc_info.value
    assert err.status_code == 422
    assert err.details == body or field(err, "raw") == body or err.details.get("detail") == body["detail"]


@pending("403 raises PermissionDeniedError with user_message")
def test_forbidden_is_permission_denied(client):
    body = load_fixture("error_forbidden.json")
    denied = exception_type("PermissionDeniedError")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}", json=body, status=403)
        with pytest.raises(denied) as exc_info:
            client.get_calendar(CALENDAR_ID)
    err = exc_info.value
    assert err.status_code == 403
    assert err.user_message == body["detail"]


@pending("plain-text unverified login raises EmailNotVerifiedError")
def test_unverified_login_is_its_own_error(mock_token_file):
    client = Client(api_url=API)
    not_verified = exception_type("EmailNotVerifiedError")
    text = load_fixture("unverified_401.txt")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/auth/token",
            body=text,
            status=401,
            content_type="text/plain",
        )
        with pytest.raises(not_verified) as exc_info:
            client.login("user@example.com", "secret")
    assert "verify" in exc_info.value.user_message.lower()


@pytest.mark.parametrize(
    "fixture_name, expected",
    [("resend_200_sent.json", "sent"), ("resend_200_already_verified.json", "already_verified")],
)
@pending("resend_verification() returns the 200 {status} body")
def test_resend_verification_ok(client, fixture_name, expected):
    body = load_fixture(fixture_name)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/resend-verification", json=body, status=200)
        result = client.resend_verification()
        assert _calls(rsps, "/auth/resend-verification")
        sent = rsps.calls[-1].request
        assert sent.method == "POST"
        assert "x-auth-token" in {key.lower() for key in sent.headers}
    assert _status(result, body) == expected


@pending("resend 429 raises RateLimitError with retry_after from retry_after_seconds")
def test_resend_verification_rate_limit(client):
    body = load_fixture("resend_429.json")
    limited = exception_type("RateLimitError")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/resend-verification", json=body, status=429)
        with pytest.raises(limited) as exc_info:
            client.resend_verification()
    err = exc_info.value
    assert err.status_code == 429
    assert err.retry_after == body["retry_after_seconds"]
    assert err.user_message == body["user_message"]


@pending("resend 502 raises an error with top-level user_message and next_step")
def test_resend_verification_upstream(client):
    body = load_fixture("resend_502.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/resend-verification", json=body, status=502)
        with pytest.raises(Exception) as exc_info:
            client.resend_verification()
    err = exc_info.value
    assert err.status_code == 502
    assert err.user_message == body["user_message"]
    assert err.next_step == body["next_step"]


@pending("update_event returns an object that carries .sync_warnings")
def test_update_event_exposes_sync_warnings(client):
    body = load_fixture("event_with_sync_warnings.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.PUT, f"{API}/events/{EVENT_ID}", json=body, status=200)
        result = client.update_event(EVENT_ID, name="Team standup")
    warnings = require_attr(result, "sync_warnings")
    assert field(warnings[0], "next_step") == "Upgrade"
    assert field(warnings[0], "event_name") == "Team standup"


@pending("toggle_event returns an object that carries .sync_warnings")
def test_toggle_event_exposes_sync_warnings(client):
    body = load_fixture("event_with_sync_warnings.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.PATCH, f"{API}/events/{EVENT_ID}/toggle", json=body, status=200)
        result = client.toggle_event(EVENT_ID)
    warnings = require_attr(result, "sync_warnings")
    assert field(warnings[0], "reason") == "trial_paused"


@pending("delete_event returns the {message, sync_warnings} body instead of None")
def test_delete_event_returns_sync_warnings(client):
    body = load_fixture("delete_event.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.DELETE, f"{API}/events/{EVENT_ID}", json=body, status=200)
        result = client.delete_event(EVENT_ID)
    warnings = require_attr(result, "sync_warnings")
    assert field(result, "message") == body["message"]
    assert field(warnings[0], "calendar_name") == "Work"


@pending("unlink_event_from_calendar returns sync_warnings instead of None")
def test_unlink_event_returns_sync_warnings(client):
    body = load_fixture("unlink_event.json")
    path = f"/calendars/{CALENDAR_ID}/events/{EVENT_ID}"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.DELETE, f"{API}{path}", json=body, status=200)
        result = client.unlink_event_from_calendar(CALENDAR_ID, EVENT_ID)
    warnings = require_attr(result, "sync_warnings")
    assert field(warnings[0], "user_message")


@pending("batch_remove_events_from_calendar returns an object with .sync_warnings")
def test_batch_unlink_exposes_sync_warnings(client):
    body = load_fixture("batch_unlink.json")
    path = f"/calendars/{CALENDAR_ID}/events/batch-unlink"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}{path}", json=body, status=200)
        result = client.batch_remove_events_from_calendar(CALENDAR_ID, [EVENT_ID])
    warnings = require_attr(result, "sync_warnings")
    assert field(warnings[0], "next_step") == "Upgrade"


@pending("link_event_to_calendar returns an object with .google_export_warnings")
def test_link_event_exposes_export_warnings(client):
    body = load_fixture("link_event.json")
    path = f"/calendars/{CALENDAR_ID}/events/{EVENT_ID}"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}{path}", json=body, status=201)
        result = client.link_event_to_calendar(CALENDAR_ID, EVENT_ID)
    warnings = require_attr(result, "google_export_warnings")
    assert field(warnings[0], "reason") == "account_needs_reauth"
    assert field(warnings[0], "user_message")
    link = require_attr(result, "link")
    assert field(link, "event_id") == EVENT_ID


@pending("any 2xx response is success, including 202")
def test_accepted_status_is_success(client):
    body = {"id": EVENT_ID, "name": "Team standup"}
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/events/from-recurrence-text",
            json=body,
            status=202,
        )
        result = client.create_event_from_text("Tomorrow at 9")
    assert field(result, "id") == EVENT_ID
