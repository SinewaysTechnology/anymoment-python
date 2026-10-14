"""Agent-facing CLI: JSON fields, dry-run, batch, schema, and env login."""

from anymoment import __version__

import io
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import responses
from click.testing import CliRunner

from anymoment.cli.commands import cli
from anymoment.dates import resolve_window

from tests.support import CALENDAR_ID, EVENT_ID, EXIT_AUTH, EXIT_OK, EXIT_USAGE


def test_package_version_is_2():
    assert __version__ == "2.0.1"


def test_natural_windows_are_stable():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)  # Wednesday
    start, end = resolve_window("tomorrow 3pm", "UTC", now=now)
    assert start == "2026-10-15T15:00:00Z"
    assert end == "2026-10-15T16:00:00Z"
    start, end = resolve_window("next fri", "UTC", now=now)
    assert start == "2026-10-16T00:00:00Z"
    assert end == "2026-10-16T23:59:59Z"
    start, end = resolve_window("next week", "UTC", now=now)
    assert start == "2026-10-19T00:00:00Z"
    assert end == "2026-10-25T23:59:59Z"


def test_fields_filter(monkeypatch, mock_token_file):
    client = MagicMock()
    client.get_user_info.return_value = {"email": "a@example.com", "id": "u1", "extra": "nope"}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["users", "me", "--json", "--fields", "email"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert payload["v"] == 1
    assert payload["email"] == "a@example.com"
    assert "extra" not in payload
    assert "id" not in payload


def test_jsonl_lists_one_object_per_line(monkeypatch, mock_token_file, sample_calendar):
    client = MagicMock()
    client.list_calendars.return_value = [sample_calendar, {**sample_calendar, "id": "other", "name": "Other"}]
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["calendars", "list", "--jsonl"])
    assert result.exit_code == EXIT_OK
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["name"] == "Test Calendar"


def test_dry_run_create_previews(monkeypatch, mock_token_file):
    client = MagicMock()
    client.preview_event_from_text.return_value = {"name": "Event"}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["events", "create", "Tomorrow at 9", "--dry-run", "--json"])
    assert result.exit_code == EXIT_OK
    client.extract_and_create_events.assert_not_called()
    client.preview_event_from_text.assert_called_once()
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True


class _TtyBuffer(io.BytesIO):
    def isatty(self) -> bool:
        return True


def _no_http(argv, monkeypatch, tty=False):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "test-token")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = CliRunner().invoke(cli, argv, input=_TtyBuffer() if tty else None)
        calls = list(rsps.calls)
    return result, calls


def test_toplevel_create_dry_run_makes_no_http(monkeypatch, mock_token_file, mock_config_file):
    result, calls = _no_http(
        ["create", "Tomorrow at 9", "--dry-run", "--json", "--host", "https://api.test.anymoment"],
        monkeypatch,
    )
    assert result.exit_code == EXIT_OK, result.output
    assert calls == []
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["op"] == "create"
    assert payload["target"] == "Tomorrow at 9"


def test_toplevel_update_dry_run_makes_no_http(monkeypatch, mock_token_file, mock_config_file):
    result, calls = _no_http(
        ["update", EVENT_ID, "--title", "Lunch", "--dry-run", "--json", "--host", "https://api.test.anymoment"],
        monkeypatch,
    )
    assert result.exit_code == EXIT_OK, result.output
    assert calls == []
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["op"] == "update"
    assert payload["target"] == EVENT_ID


def test_toplevel_update_without_fields_exits_usage(monkeypatch, mock_token_file, mock_config_file):
    result, calls = _no_http(
        ["update", EVENT_ID, "--host", "https://api.test.anymoment"],
        monkeypatch,
    )
    assert result.exit_code == EXIT_USAGE
    assert calls == []


def test_events_update_without_fields_exits_usage(monkeypatch, mock_token_file, mock_config_file):
    result, calls = _no_http(
        ["events", "update", EVENT_ID, "--host", "https://api.test.anymoment"],
        monkeypatch,
    )
    assert result.exit_code == EXIT_USAGE
    assert calls == []


def test_toplevel_yes_skips_confirm_and_dry_run_still_makes_no_http(
    monkeypatch, mock_token_file, mock_config_file
):
    blocked, blocked_calls = _no_http(
        ["update", EVENT_ID, "--title", "Lunch", "--host", "https://api.test.anymoment"],
        monkeypatch,
        tty=True,
    )
    assert blocked.exit_code == EXIT_USAGE, blocked.output
    assert blocked_calls == []

    allowed, allowed_calls = _no_http(
        [
            "create",
            "Tomorrow at 9",
            "--yes",
            "--dry-run",
            "--json",
            "--host",
            "https://api.test.anymoment",
        ],
        monkeypatch,
        tty=True,
    )
    assert allowed.exit_code == EXIT_OK, allowed.output
    assert allowed_calls == []
    assert json.loads(allowed.stdout)["dry_run"] is True


def test_toplevel_yes_sends_create(monkeypatch, mock_token_file, mock_config_file):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "test-token")
    host = "https://api.test.anymoment"
    body = {
        "summary": {"total_extracted": 0, "successfully_created": 0, "failed_to_create": 0},
        "created_events": [],
    }
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{host}/events/extract", json=body, status=200)
        result = CliRunner().invoke(
            cli,
            ["create", "Tomorrow at 9", "--yes", "--host", host],
            input=_TtyBuffer(),
        )
        assert result.exit_code == EXIT_OK, result.output
        assert len(rsps.calls) == 1
        assert rsps.calls[0].request.method == "POST"
        assert rsps.calls[0].request.url == f"{host}/events/extract"


def test_dry_run_delete_skips_the_api(monkeypatch, mock_token_file):
    client = MagicMock()
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["events", "delete", EVENT_ID, "--dry-run", "--json"])
    assert result.exit_code == EXIT_OK
    client.delete_event.assert_not_called()
    assert json.loads(result.stdout)["op"] == "delete"


def test_idempotency_key_replays_delete(monkeypatch, mock_token_file, mock_config_file):
    client = MagicMock()
    client.delete_event.return_value = {"message": "deleted", "sync_warnings": []}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    runner = CliRunner()
    args = ["events", "delete", EVENT_ID, "--json", "--idempotency-key", "same-key"]
    first = runner.invoke(cli, args)
    second = runner.invoke(cli, args)
    assert first.exit_code == EXIT_OK
    assert second.exit_code == EXIT_OK
    assert json.loads(first.stdout) == json.loads(second.stdout)
    client.delete_event.assert_called_once()


def test_schema_and_help_json():
    runner = CliRunner()
    schema = runner.invoke(cli, ["schema"])
    helped = runner.invoke(cli, ["help", "--json"])
    assert schema.exit_code == EXIT_OK
    assert helped.exit_code == EXIT_OK
    left = json.loads(schema.stdout)
    right = json.loads(helped.stdout)
    assert left == right
    assert left["exit_codes"]["auth"] == EXIT_AUTH
    assert left["exit_codes"]["rate_limited"] == 6
    assert "agenda show" in left["commands"]
    assert "auth resend-verification" in left["commands"]


def test_agenda_one_call(monkeypatch, mock_token_file):
    client = MagicMock()
    client.get_agenda.return_value = {"events": [], "failures": []}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["agenda", "next week", "--json"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.stdout)
    assert payload["events"] == []
    assert payload["start"] < payload["end"]
    client.get_agenda.assert_called_once()


def test_env_token_skips_prompt(monkeypatch, mock_config_file):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "env-token")
    seen = {}

    class Fake:
        def __init__(self, api_url=None, token=None):
            seen["token"] = token

        def _set_token(self, token):
            seen["saved"] = token

    monkeypatch.setattr("anymoment.cli.commands.Client", Fake)
    result = CliRunner().invoke(cli, ["auth", "login", "--json"])
    assert result.exit_code == EXIT_OK
    assert seen["token"] == "env-token"
    assert seen["saved"] == "env-token"


def test_login_without_tty_does_not_prompt(monkeypatch, mock_config_file):
    monkeypatch.delenv("ANYMOMENT_TOKEN", raising=False)
    result = CliRunner().invoke(cli, ["auth", "login"])
    assert result.exit_code == EXIT_AUTH
    assert "password" in result.stderr.lower() or "ANYMOMENT_TOKEN" in result.stderr


def test_batch_stdin(monkeypatch, mock_token_file):
    client = MagicMock()
    client.delete_event.return_value = {"message": "deleted"}
    client.link_event_to_calendar.return_value = {"link": {"event_id": EVENT_ID}}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    body = "\n".join(
        [
            json.dumps({"op": "delete", "id": EVENT_ID}),
            json.dumps({"op": "link", "calendar_id": CALENDAR_ID, "event_id": EVENT_ID}),
        ]
    )
    result = CliRunner().invoke(cli, ["events", "batch", "--json"], input=body)
    assert result.exit_code == EXIT_OK
    client.delete_event.assert_called_once_with(EVENT_ID)
    client.link_event_to_calendar.assert_called_once_with(CALENDAR_ID, EVENT_ID)


def test_batch_without_stdin_is_usage():
    result = CliRunner().invoke(cli, ["events", "batch"])
    assert result.exit_code == EXIT_USAGE
