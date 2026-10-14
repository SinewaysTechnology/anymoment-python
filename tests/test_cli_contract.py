"""CLI harness for 2.0 exit codes and --json output.

Click's CliRunner is the runner. Passing tests cover behavior that already
matches (usage exits 2). `pending` tests are the checklist for the codes
and the compact JSON shape, which 1.0 does not implement.
"""

import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from anymoment.cli.commands import cli
from anymoment.exceptions import (
    AnyMomentException,
    NotFoundError,
    ServerError,
    ValidationError,
)

from tests.support import (
    CALENDAR_ID,
    ERROR_JSON_KEYS,
    EVENT_ID,
    EXIT_AUTH,
    EXIT_NETWORK,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_PERMISSION,
    EXIT_RATE_LIMIT,
    EXIT_UPSTREAM,
    EXIT_USAGE,
    EXIT_VALIDATION,
    Payload,
    exception_type,
    load_fixture,
    pending,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client(monkeypatch):
    client = MagicMock()

    def _get_client(*args, **kwargs):
        return client

    monkeypatch.setattr("anymoment.cli.commands.get_client", _get_client)
    return client


def _raise(name, message, **kwargs):
    cls = exception_type(name)
    try:
        return cls(message, **kwargs)
    except TypeError as exc:
        pytest.fail(f"{name} does not accept {sorted(kwargs)}: {exc}")


def test_unknown_option_exits_usage(runner):
    result = runner.invoke(cli, ["calendars", "list", "--nope"])
    assert result.exit_code == EXIT_USAGE


@pending("missing auth exits 3")
def test_not_authenticated_exits_auth(runner, mock_token_file, mock_config_file):
    result = runner.invoke(cli, ["users", "me"])
    assert result.exit_code == EXIT_AUTH


@pending("not found exits 4")
def test_not_found_exits_4(runner, mock_client, mock_token_file):
    mock_client.get_calendar.side_effect = NotFoundError("Calendar not found")
    result = runner.invoke(cli, ["calendars", "get", CALENDAR_ID])
    assert result.exit_code == EXIT_NOT_FOUND


@pending("validation errors exit 5")
def test_validation_exits_5(runner, mock_client, mock_token_file):
    mock_client.create_calendar.side_effect = ValidationError("Name is required")
    result = runner.invoke(cli, ["calendars", "create", "Work"])
    assert result.exit_code == EXIT_VALIDATION


@pending("permission and read-only errors exit 6")
def test_permission_exits_6(runner, mock_client, mock_token_file):
    mock_client.get_calendar.side_effect = _raise(
        "PermissionDeniedError",
        "This calendar is read-only",
        status_code=403,
        user_message="Family dinner is read-only.",
        next_step="Edit it on the calendar server.",
    )
    result = runner.invoke(cli, ["calendars", "get", CALENDAR_ID])
    assert result.exit_code == EXIT_PERMISSION


@pending("rate limits exit 7")
def test_rate_limit_exits_7(runner, mock_client, mock_token_file):
    mock_client.get_user_info.side_effect = _raise(
        "RateLimitError",
        "Slow down",
        status_code=429,
        retry_after=60,
        user_message="Please wait before trying again.",
    )
    result = runner.invoke(cli, ["users", "me"])
    assert result.exit_code == EXIT_RATE_LIMIT


@pending("agenda failures exit 8 (partial success)")
def test_agenda_failures_exit_partial(runner, mock_client, mock_token_file):
    mock_client.get_agenda.return_value = Payload(load_fixture("agenda_batch.json"))
    result = runner.invoke(
        cli,
        ["agenda", "list", "--start", "2026-10-14T00:00:00Z", "--end", "2026-10-14T23:59:59Z"],
    )
    assert result.exit_code == EXIT_PARTIAL


@pending("delete exits 8 when sync_warnings are present")
def test_delete_with_warnings_exits_partial(runner, mock_client, mock_token_file):
    mock_client.delete_event.return_value = Payload(load_fixture("delete_event.json"))
    result = runner.invoke(cli, ["events", "delete", EVENT_ID])
    assert result.exit_code == EXIT_PARTIAL


@pending("server errors exit 9")
def test_server_error_exits_9(runner, mock_client, mock_token_file):
    mock_client.list_calendars.side_effect = ServerError("Bad gateway", status_code=502)
    result = runner.invoke(cli, ["calendars", "list"])
    assert result.exit_code == EXIT_UPSTREAM


@pending("network failures exit 10")
def test_network_error_exits_10(runner, mock_client, mock_token_file):
    mock_client.list_calendars.side_effect = AnyMomentException("Request failed: timed out")
    result = runner.invoke(cli, ["calendars", "list"])
    assert result.exit_code == EXIT_NETWORK


@pending("agenda list --json prints one object {v: 1, events, failures}")
def test_agenda_json_shape(runner, mock_client, mock_token_file):
    body = load_fixture("agenda_batch.json")
    body["failures"] = []
    mock_client.get_agenda.return_value = Payload(body)
    result = runner.invoke(
        cli,
        [
            "agenda",
            "list",
            "--start",
            "2026-10-14T00:00:00Z",
            "--end",
            "2026-10-14T23:59:59Z",
            "--json",
        ],
    )
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert payload["v"] == 1
    assert isinstance(payload["events"], list)
    assert payload["failures"] == []
    assert payload["events"][0]["event"]["id"] == EVENT_ID


@pending("users me --json prints one object with v and the user email")
def test_me_json_shape(runner, mock_client, mock_token_file, sample_user):
    mock_client.get_user_info.return_value = Payload(sample_user)
    result = runner.invoke(cli, ["users", "me", "--json"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert payload["v"] == 1
    email = payload.get("email") or payload.get("user", {}).get("email")
    assert email == sample_user["email"]


@pending("events delete --json includes sync_warnings and exits 8 when warnings exist")
def test_delete_json_includes_warnings(runner, mock_client, mock_token_file):
    body = load_fixture("delete_event.json")
    mock_client.delete_event.return_value = Payload(body)
    result = runner.invoke(cli, ["events", "delete", EVENT_ID, "--json"])
    assert result.exit_code == EXIT_PARTIAL
    payload = json.loads(result.stdout)
    assert payload["v"] == 1
    assert payload["sync_warnings"][0]["next_step"] == body["sync_warnings"][0]["next_step"]
    assert payload["sync_warnings"][0]["event_name"] == "Team standup"


@pending("--json errors are one stderr object {error: {code, status, user_message, next_step, retry_after}}")
def test_json_error_shape(runner, mock_client, mock_token_file):
    mock_client.get_calendar.side_effect = NotFoundError("Calendar not found")
    result = runner.invoke(cli, ["calendars", "get", CALENDAR_ID, "--json"])
    assert result.exit_code == EXIT_NOT_FOUND
    payload = json.loads(result.stderr)
    assert ERROR_JSON_KEYS <= set(payload["error"])
    assert payload["error"]["status"] == 404
    assert payload["error"]["user_message"]


@pending("auth resend-verification --json prints {v, status}")
def test_resend_verification_json(runner, mock_token_file, mock_config_file, monkeypatch):
    client = MagicMock()
    client.resend_verification.return_value = Payload(load_fixture("resend_200_sent.json"))
    monkeypatch.setattr("anymoment.cli.commands.Client", lambda *args, **kwargs: client)
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = runner.invoke(cli, ["auth", "resend-verification", "--json"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert payload["v"] == 1
    assert payload["status"] == "sent"


@pending("auth resend-verification exits 7 and reports retry_after when the API returns 429")
def test_resend_verification_rate_limit_json(runner, mock_token_file, mock_config_file, monkeypatch):
    client = MagicMock()
    client.resend_verification.side_effect = _raise(
        "RateLimitError",
        "Slow down",
        status_code=429,
        retry_after=60,
        user_message="Please wait before requesting another verification email.",
    )
    monkeypatch.setattr("anymoment.cli.commands.Client", lambda *args, **kwargs: client)
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = runner.invoke(cli, ["auth", "resend-verification", "--json"])
    assert result.exit_code == EXIT_RATE_LIMIT
    payload = json.loads(result.stderr)
    assert payload["error"]["retry_after"] == 60
    assert payload["error"]["status"] == 429
