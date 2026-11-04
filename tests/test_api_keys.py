"""API key auth, calendar-scoped event lists, subscriptions, and webhook signatures."""

import json

import jwt
import pytest
import responses
from click.testing import CliRunner

from anymoment.cli.commands import cli
from anymoment.client import Client, api_key_prefix
from anymoment.exceptions import (
    ApiKeyExpiredError,
    ApiKeyNotPermittedError,
    ApiKeyRevokedError,
    AuthenticationError,
    CalendarNotAllowedError,
    InvalidApiKeyError,
    RateLimitError,
    ValidationError,
)
from anymoment.signatures import verify_signature, verify_webhook, webhook_signature
from anymoment.token_manager import save_token

from tests.support import API, CALENDAR_ID, EXIT_AUTH, EXIT_OK, EXIT_RATE_LIMIT, EXIT_REMOTE, EXIT_USAGE, load_fixture

KEY = "am_live_abcd1234_supersecretvalue"
OTHER_KEY = "am_live_ffffffff_envsecretvalue"
PREFIX = "am_live_abcd1234"
SUBSCRIPTION_ID = "770e8400-e29b-41d4-a716-446655440010"
DELIVERY_ID = "880e8400-e29b-41d4-a716-446655440011"


def _auth_header(request) -> str:
    headers = {key.lower(): value for key, value in request.headers.items()}
    return headers.get("authorization", "")


def _has_session_header(request) -> bool:
    return any(key.lower() == "x-auth-token" for key in request.headers)


@pytest.fixture
def runner():
    return CliRunner()


def test_recorded_invalid_api_key_body_matches_live_api():
    """GET with a fake am_live key returns this body. Captured from the public API."""
    assert load_fixture("recorded_invalid_api_key_401.json") == {
        "detail": {"code": "invalid_api_key", "message": "Invalid API key."}
    }


def test_api_key_prefix_drops_the_secret():
    assert api_key_prefix(KEY) == PREFIX
    assert api_key_prefix("am_live_abcd1234_secret_with_underscores") == PREFIX
    assert api_key_prefix("not-a-key") is None


def test_client_sends_bearer_and_skips_saved_token(mock_token_file):
    save_token(API, _session_token())
    client = Client(api_url=API, token="saved-looking-token", api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=[], status=200)
        rsps.add(responses.GET, f"{API}/auth/token/extend", body='"nope"', status=200)
        client.list_calendars()
        sent = rsps.calls[0].request
        assert _auth_header(sent) == f"Bearer {KEY}"
        assert not _has_session_header(sent)
        assert all("/auth/token/extend" not in call.request.url for call in rsps.calls)


def test_env_api_key_beats_token_argument(mock_token_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_API_KEY", KEY)
    client = Client(api_url=API, token="session-token")
    assert client.api_key == KEY
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=[], status=200)
        client.list_calendars()
        assert _auth_header(rsps.calls[0].request) == f"Bearer {KEY}"
        assert not _has_session_header(rsps.calls[0].request)


def test_explicit_api_key_beats_env(mock_token_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_API_KEY", OTHER_KEY)
    client = Client(api_url=API, api_key=KEY)
    assert client.api_key == KEY


@pytest.mark.parametrize(
    "fixture_name, status, exc_type, code",
    [
        ("recorded_invalid_api_key_401.json", 401, InvalidApiKeyError, "invalid_api_key"),
        ("api_key_revoked_401.json", 401, ApiKeyRevokedError, "api_key_revoked"),
        ("api_key_expired_401.json", 401, ApiKeyExpiredError, "api_key_expired"),
        ("api_key_not_permitted_403.json", 403, ApiKeyNotPermittedError, "api_key_not_permitted"),
        ("calendar_not_allowed_403.json", 403, CalendarNotAllowedError, "calendar_not_allowed"),
    ],
)
def test_api_key_errors_are_typed(mock_token_file, fixture_name, status, exc_type, code):
    body = load_fixture(fixture_name)
    client = Client(api_url=API, api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=body, status=status)
        rsps.add(responses.GET, f"{API}/auth/token/extend", body='"refreshed"', status=200)
        with pytest.raises(exc_type) as exc_info:
            client.list_calendars()
        assert all("/auth/token/extend" not in call.request.url for call in rsps.calls)
    err = exc_info.value
    assert err.status_code == status
    assert err.code == code
    assert err.user_message == body["detail"]["message"]
    assert err.message == body["detail"]["message"]
    assert err.next_step
    assert KEY not in err.next_step
    assert "supersecretvalue" not in (err.user_message or "")


def test_rate_limit_reads_retry_after_seconds(mock_token_file):
    body = load_fixture("api_key_rate_limit_429.json")
    client = Client(api_url=API, api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=body, status=429)
        with pytest.raises(RateLimitError) as exc_info:
            client.list_calendars()
    err = exc_info.value
    assert err.retry_after == 30
    assert err.user_message == "Too many requests."
    assert "30" in err.next_step


def test_api_key_list_events_uses_calendar_route(mock_token_file):
    body = load_fixture("calendar_events.json")
    client = Client(api_url=API, api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}/events", json=body, status=200)
        rsps.add(responses.GET, f"{API}/events", json=[], status=200)
        listed = client.list_events(calendar_id=CALENDAR_ID, limit=10)
        urls = [call.request.url for call in rsps.calls]
    assert listed[0]["event"]["display_name"] == "Team standup"
    assert listed[0]["link"]["calendar_id"] == CALENDAR_ID
    assert urls == [f"{API}/calendars/{CALENDAR_ID}/events?limit=10"]


def test_session_list_events_stays_on_events_route(mock_token_file):
    client = Client(api_url=API, token="session-token")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/events", json=[{"id": "e1"}], status=200)
        listed = client.list_events(calendar_id=CALENDAR_ID)
        sent = rsps.calls[0].request
    assert listed == [{"id": "e1"}]
    assert f"{API}/calendars/" not in sent.url
    assert "calendar_id=" in sent.url
    assert _has_session_header(sent)


def test_calendar_limited_events_list_explains_the_route(mock_token_file):
    body = load_fixture("calendar_not_allowed_403.json")
    client = Client(api_url=API, api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/events", json=body, status=403)
        with pytest.raises(CalendarNotAllowedError) as exc_info:
            client.list_events()
    assert "GET /events" in exc_info.value.next_step
    assert "/calendars/{calendar_id}/events" in exc_info.value.next_step


def test_minimal_is_rejected_for_calendar_scoped_keys(mock_token_file):
    client = Client(api_url=API, api_key=KEY)
    with pytest.raises(ValidationError) as exc_info:
        client.list_events(calendar_id=CALENDAR_ID, minimal=True)
    assert "calendar_id" in exc_info.value.next_step


def test_api_key_is_not_refreshed(mock_token_file):
    client = Client(api_url=API, api_key=KEY)
    with pytest.raises(AuthenticationError) as exc_info:
        client.refresh_token()
    assert "cannot be refreshed" in exc_info.value.user_message.lower()


def test_subscriptions_follow_the_api_schema(mock_token_file):
    created = load_fixture("subscription_created.json")
    listed = load_fixture("subscription.json")
    delivery = load_fixture("delivery.json")
    client = Client(api_url=API, api_key=KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions",
            json=created,
            status=201,
        )
        rsps.add(
            responses.GET,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions",
            json=[listed],
            status=200,
        )
        rsps.add(
            responses.PATCH,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions/{SUBSCRIPTION_ID}",
            json=listed,
            status=200,
        )
        rsps.add(
            responses.DELETE,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions/{SUBSCRIPTION_ID}",
            status=204,
        )
        rsps.add(
            responses.GET,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions/{SUBSCRIPTION_ID}/deliveries",
            json=[delivery],
            status=200,
        )
        rsps.add(
            responses.POST,
            f"{API}/calendars/{CALENDAR_ID}/subscriptions/{SUBSCRIPTION_ID}/deliveries/{DELIVERY_ID}/replay",
            json={**delivery, "replay_of_id": DELIVERY_ID, "status": "pending"},
            status=201,
        )
        made = client.create_subscription(
            CALENDAR_ID,
            url="https://example.com/hooks/anymoment",
            event_types=["event.updated"],
            occurrence_offset_seconds=-300,
        )
        rows = client.list_subscriptions(CALENDAR_ID)
        client.update_subscription(CALENDAR_ID, SUBSCRIPTION_ID, is_active=False)
        client.delete_subscription(CALENDAR_ID, SUBSCRIPTION_ID)
        deliveries = client.list_subscription_deliveries(CALENDAR_ID, SUBSCRIPTION_ID, limit=20)
        replayed = client.replay_subscription_delivery(CALENDAR_ID, SUBSCRIPTION_ID, DELIVERY_ID)
        create_body = json.loads(rsps.calls[0].request.body)
        update_body = json.loads(rsps.calls[2].request.body)
        assert "limit=20" in rsps.calls[4].request.url
        assert _auth_header(rsps.calls[0].request) == f"Bearer {KEY}"
    assert made["secret"] == "whsec_shown_once"
    assert rows[0]["secret"] is None
    assert create_body == {
        "url": "https://example.com/hooks/anymoment",
        "event_types": ["event.updated"],
        "occurrence_offset_seconds": -300,
    }
    assert update_body == {"is_active": False}
    assert deliveries[0]["status"] == "delivered"
    assert replayed["status"] == "pending"


def test_webhook_signature_is_hmac_of_timestamp_and_raw_body():
    payload = b'{"id":"1"}'
    timestamp = "1760000000"
    secret = "whsec_shown_once"
    signature = webhook_signature(secret, timestamp, payload)
    headers = {
        "X-AnyMoment-Signature": signature,
        "X-AnyMoment-Timestamp": timestamp,
        "X-AnyMoment-Delivery": DELIVERY_ID,
    }
    assert verify_signature(payload, secret, signature, timestamp, now=1760000000)
    assert verify_webhook(payload, headers, secret, now=1760000000)
    assert not verify_signature(payload, secret, signature, timestamp, now=1760000000 + 301)
    assert not verify_signature(b'{"id":"2"}', secret, signature, timestamp, now=1760000000)
    assert not verify_webhook(payload, {"X-AnyMoment-Timestamp": timestamp}, secret, now=1760000000)


def test_auth_status_hides_the_secret(runner, mock_token_file, mock_config_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "env-token-should-not-print")
    monkeypatch.setenv("ANYMOMENT_API_KEY", OTHER_KEY)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=[], status=200)
        result = runner.invoke(cli, ["--api-key", KEY, "auth", "status", "--json", "--host", API])
    assert result.exit_code == EXIT_OK, result.output
    assert "supersecretvalue" not in result.stdout
    assert "supersecretvalue" not in result.stderr
    assert "envsecretvalue" not in result.stdout
    assert "env-token-should-not-print" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["method"] == "api_key"
    assert payload["source"] == "flag"
    assert payload["key_prefix"] == PREFIX
    assert payload["authenticated"] is True


def test_auth_status_reports_saved_login(runner, mock_token_file, mock_config_file):
    save_token(API, _session_token())
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"email": "a@example.com"}, status=200)
        result = runner.invoke(cli, ["auth", "status", "--json", "--host", API])
    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.stdout)
    assert payload["method"] == "saved_login"
    assert payload["status"] == "valid"
    assert payload["authenticated"] is True
    assert _session_token() not in result.stdout


def test_auth_status_reports_env_token(runner, mock_token_file, mock_config_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "env-token-should-not-print")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"email": "a@example.com"}, status=200)
        result = runner.invoke(cli, ["auth", "status", "--host", API])
    assert result.exit_code == EXIT_OK
    assert "ANYMOMENT_TOKEN" in result.output
    assert "Status: valid" in result.output
    assert "env-token-should-not-print" not in result.output


def test_cli_uses_api_key_for_calendar_events(runner, mock_token_file, mock_config_file, monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "env-token-should-not-print")
    body = load_fixture("calendar_events.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars/{CALENDAR_ID}/events", json=body, status=200)
        rsps.add(responses.GET, f"{API}/events", json=[], status=200)
        result = runner.invoke(
            cli,
            ["events", "list", "--calendar", CALENDAR_ID, "--api-key", KEY, "--json", "--host", API],
        )
        urls = [call.request.url for call in rsps.calls]
        sent = rsps.calls[0].request
    assert result.exit_code == EXIT_OK, result.output
    assert f"/calendars/{CALENDAR_ID}/events" in urls[0]
    assert _auth_header(sent) == f"Bearer {KEY}"
    assert not _has_session_header(sent)
    assert "supersecretvalue" not in result.stdout


def test_cli_invalid_api_key_json(runner, mock_token_file, mock_config_file):
    body = load_fixture("recorded_invalid_api_key_401.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=body, status=401)
        rsps.add(responses.GET, f"{API}/auth/token/extend", body='"refreshed"', status=200)
        result = runner.invoke(
            cli,
            ["calendars", "list", "--api-key", KEY, "--json", "--host", API],
        )
        assert all("/auth/token/extend" not in call.request.url for call in rsps.calls)
    assert result.exit_code == EXIT_AUTH
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "invalid_api_key"
    assert payload["error"]["status"] == 401
    assert payload["error"]["user_message"] == "Invalid API key."
    assert payload["error"]["next_step"]
    assert "supersecretvalue" not in result.stderr


def test_cli_rate_limit_json(runner, mock_token_file, mock_config_file):
    body = load_fixture("api_key_rate_limit_429.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/calendars", json=body, status=429)
        result = runner.invoke(
            cli,
            ["calendars", "list", "--api-key", KEY, "--json", "--host", API],
        )
    assert result.exit_code == EXIT_RATE_LIMIT
    payload = json.loads(result.stderr)
    assert payload["error"]["retry_after"] == 30
    assert payload["error"]["status"] == 429


def test_cli_permission_json(runner, mock_token_file, mock_config_file):
    body = load_fixture("api_key_not_permitted_403.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json=body, status=403)
        result = runner.invoke(cli, ["users", "me", "--api-key", KEY, "--json", "--host", API])
    assert result.exit_code == EXIT_REMOTE
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "api_key_not_permitted"
    assert "auth login" in payload["error"]["next_step"]


def test_subscription_dry_run_makes_no_http(runner, mock_token_file, mock_config_file):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = runner.invoke(
            cli,
            [
                "calendars",
                "subscriptions",
                "create",
                CALENDAR_ID,
                "--url",
                "https://example.com/hooks/anymoment",
                "--event-type",
                "event.updated",
                "--dry-run",
                "--json",
                "--host",
                API,
            ],
        )
        assert list(rsps.calls) == []
    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["op"] == "create-subscription"


def test_subscription_update_without_fields_exits_usage(runner, mock_token_file, mock_config_file):
    result = runner.invoke(
        cli,
        ["calendars", "subscriptions", "update", CALENDAR_ID, SUBSCRIPTION_ID, "--host", API],
    )
    assert result.exit_code == EXIT_USAGE


def test_schema_lists_api_key_and_subscriptions(runner):
    result = runner.invoke(cli, ["schema"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert "--api-key" in payload["flags"]
    assert "auth status" in payload["commands"]
    assert "calendars subscriptions list" in payload["commands"]
    assert "calendars subscriptions replay" in payload["commands"]


def _session_token() -> str:
    return jwt.encode({"sub": "user", "exp": 9999999999}, "test-secret", algorithm="HS256")
