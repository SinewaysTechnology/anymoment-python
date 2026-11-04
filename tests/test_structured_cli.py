"""Structured create, ICS import, batch-add errors, auth checks, and agenda counts."""

import json
from pathlib import Path

import jwt
import responses
from click.testing import CliRunner

import anymoment_entry
from anymoment.cli.commands import cli
from anymoment.client import Client, normalize_batch_add
from anymoment.exceptions import ServerError
from anymoment.schedule import build_scheduled_event, load_event_records, summarize_agenda
from anymoment.token_manager import peek_token, save_token

from tests.support import (
    API,
    CALENDAR_ID,
    EVENT_ID,
    EXIT_AUTH,
    EXIT_OK,
    EXIT_REMOTE,
    EXIT_USAGE,
    load_fixture,
)


def _body(request):
    return json.loads(request.body)


def _token(monkeypatch):
    monkeypatch.setenv("ANYMOMENT_TOKEN", "test-token")


def test_once_event_matches_post_events_shape():
    body = build_scheduled_event(
        title="Dentist",
        start="2026-10-16T15:00:00",
        end="2026-10-16T15:30:00",
        timezone="UTC",
        location="Clinic",
        description="Checkup",
    )
    assert set(body) == {"name", "description", "components"}
    assert body["name"] == "Dentist"
    assert body["description"] == "Checkup\nLocation: Clinic"
    component = body["components"][0]
    assert component["operator"] == "OR"
    config = component["event_config"]
    assert config["recurrence"] == 4
    assert config["start_time"] == "15:00"
    assert config["end_time"] == "15:30"
    assert config["is_all_day"] is False
    assert config["timezone"] == "UTC"
    assert config["config"] == {"scheduled_datetime": "2026-10-16T15:00:00"}
    assert "location" not in body


def test_weekly_rrule_uses_the_documented_recurrence_value():
    body = build_scheduled_event(
        title="Standup",
        start="2026-10-19T09:00:00",
        end="2026-10-19T09:15:00",
        rrule="FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        timezone="UTC",
    )
    config = body["components"][0]["event_config"]
    assert config["recurrence"] == 1
    assert config["config"]["interval"] == 1
    assert config["config"]["days_of_week"] == [0, 1, 2, 3, 4]
    assert config["start_time"] == "09:00"


def test_all_day_omits_clock_times():
    body = build_scheduled_event(
        title="Holiday",
        start="2026-12-25",
        all_day=True,
        timezone="UTC",
    )
    config = body["components"][0]["event_config"]
    assert config["is_all_day"] is True
    assert "start_time" not in config
    assert "end_time" not in config
    assert config["recurrence"] == 4


def test_unsupported_rrule_names_import():
    try:
        build_scheduled_event(
            title="Odd",
            start="2026-10-16T09:00:00",
            rrule="FREQ=WEEKLY;BYDAY=MO;EXDATE=20261023T090000Z",
        )
    except Exception as exc:
        assert "am events import" in exc.user_message or "am events import" in (exc.next_step or "")
    else:
        raise AssertionError("EXDATE should not be sent as a structured component")


def test_jsonl_and_json_array_load():
    records = load_event_records('{"title": "A", "start": "2026-10-16"}\n{"title": "B", "start": "2026-10-17"}\n')
    assert [row["title"] for row in records] == ["A", "B"]
    wrapped = load_event_records('{"events": [{"title": "C", "start": "2026-10-16"}]}')
    assert wrapped[0]["title"] == "C"


def test_events_add_posts_components_and_links(mock_token_file, mock_config_file, monkeypatch):
    _token(monkeypatch)
    created = {"id": EVENT_ID, "name": "Dentist", "sync_warnings": []}
    link = load_fixture("link_event.json")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/events", json=created, status=201)
        rsps.add(
            responses.POST,
            f"{API}/calendars/{CALENDAR_ID}/events/{EVENT_ID}",
            json=link,
            status=201,
        )
        result = CliRunner().invoke(
            cli,
            [
                "events",
                "add",
                "--title",
                "Dentist",
                "--start",
                "2026-10-16T15:00:00",
                "--end",
                "2026-10-16T15:30:00",
                "--calendar",
                CALENDAR_ID,
                "--location",
                "Clinic",
                "--timezone",
                "UTC",
                "--json",
                "--host",
                API,
            ],
        )
        create_body = _body(rsps.calls[0].request)
        link_body = _body(rsps.calls[1].request)
    assert result.exit_code == EXIT_OK, result.output
    assert create_body["name"] == "Dentist"
    assert create_body["components"][0]["event_config"]["recurrence"] == 4
    assert "Location: Clinic" in create_body["description"]
    assert "location" not in create_body
    assert link_body == {}
    payload = json.loads(result.stdout)
    assert payload["event"]["id"] == EVENT_ID
    assert payload["warnings"][0]["user_message"]


def test_events_add_file_jsonl(mock_token_file, mock_config_file, tmp_path: Path, monkeypatch):
    _token(monkeypatch)
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"title": "One", "start": "2026-10-16T09:00:00", "timezone": "UTC"}),
                json.dumps({"name": "Two", "start": "2026-10-17T09:00:00", "timezone": "UTC"}),
            ]
        ),
        encoding="utf-8",
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/events", json={"id": EVENT_ID, "name": "One"}, status=201)
        rsps.add(responses.POST, f"{API}/events", json={"id": EVENT_ID, "name": "Two"}, status=201)
        result = CliRunner().invoke(
            cli,
            ["events", "add", "--file", str(path), "--json", "--host", API],
        )
        names = [_body(call.request)["name"] for call in rsps.calls]
    assert result.exit_code == EXIT_OK, result.output
    assert names == ["One", "Two"]
    payload = json.loads(result.stdout)
    assert [row["ok"] for row in payload["results"]] == [True, True]


def test_events_add_dry_run_makes_no_http(mock_token_file, mock_config_file):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        result = CliRunner().invoke(
            cli,
            [
                "events",
                "add",
                "--title",
                "Dentist",
                "--start",
                "2026-10-16T15:00:00",
                "--timezone",
                "UTC",
                "--dry-run",
                "--json",
                "--host",
                API,
            ],
        )
        calls = list(rsps.calls)
    assert result.exit_code == EXIT_OK, result.output
    assert calls == []
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["request"]["components"][0]["event_config"]["recurrence"] == 4


def test_events_add_bad_rrule_is_usage(mock_token_file, mock_config_file):
    result = CliRunner().invoke(
        cli,
        [
            "events",
            "add",
            "--title",
            "Odd",
            "--start",
            "2026-10-16T09:00:00",
            "--rrule",
            "FREQ=HOURLY",
            "--timezone",
            "UTC",
            "--host",
            API,
        ],
    )
    assert result.exit_code == EXIT_USAGE
    assert "FREQ" in result.stderr


def test_events_import_posts_ics_and_links(mock_token_file, mock_config_file, tmp_path: Path, monkeypatch):
    _token(monkeypatch)
    path = tmp_path / "one.ics"
    path.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Imported\nEND:VEVENT\nEND:VCALENDAR\n", encoding="utf-8")
    imported = {
        "events": [
            {"event": {"id": EVENT_ID, "name": "Imported"}, "error": None, "event_index": 0, "summary": "Imported"}
        ],
        "total_events": 1,
        "successful_imports": 1,
        "failed_imports": 0,
        "errors": [],
    }
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/events/from-ics", json=imported, status=200)
        rsps.add(
            responses.POST,
            f"{API}/calendars/{CALENDAR_ID}/events/{EVENT_ID}",
            json={"link": {"event_id": EVENT_ID}, "google_export_warnings": []},
            status=201,
        )
        result = CliRunner().invoke(
            cli,
            ["events", "import", str(path), "--name", "Imported", "--calendar", CALENDAR_ID, "--json", "--host", API],
        )
        sent = _body(rsps.calls[0].request)
        link_url = rsps.calls[1].request.url
    assert result.exit_code == EXIT_OK, result.output
    assert "BEGIN:VCALENDAR" in sent["ics_content"]
    assert sent["name"] == "Imported"
    assert link_url.endswith(f"/calendars/{CALENDAR_ID}/events/{EVENT_ID}")
    assert json.loads(result.stdout)["successful_imports"] == 1


def test_batch_add_reports_each_warning(mock_token_file, mock_config_file, monkeypatch):
    _token(monkeypatch)
    warning = load_fixture("link_event.json")["google_export_warnings"][0]
    body = [
        {"link": {"event_id": EVENT_ID, "calendar_id": CALENDAR_ID}, "google_export_warnings": [warning]},
        {"link": {"event_id": "660e8400-e29b-41d4-a716-446655440002", "calendar_id": CALENDAR_ID}, "google_export_warnings": []},
    ]
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/calendars/{CALENDAR_ID}/events", json=body, status=201)
        result = CliRunner().invoke(
            cli,
            ["calendars", "batch-add-events", CALENDAR_ID, EVENT_ID, "--json", "--host", API],
        )
    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.stdout)
    assert payload["results"][0]["warnings"][0]["user_message"] == warning["user_message"]
    assert payload["results"][0]["event_id"] == EVENT_ID
    assert payload["results"][1]["ok"] is True


def test_batch_add_server_traceback_is_a_clear_error(mock_token_file, mock_config_file, monkeypatch):
    _token(monkeypatch)
    traceback = (
        'Traceback (most recent call last):\n'
        '  File "app/recurrence/routers.py", line 10, in batch_add\n'
        "TypeError: cannot unpack non-iterable NoneType object\n"
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(
            responses.POST,
            f"{API}/calendars/{CALENDAR_ID}/events",
            body=traceback,
            status=500,
            content_type="text/plain",
        )
        result = CliRunner().invoke(
            cli,
            ["calendars", "batch-add-events", CALENDAR_ID, EVENT_ID, "--json", "--host", API],
        )
    assert result.exit_code == EXIT_REMOTE
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    assert "cannot unpack" not in result.stderr
    payload = json.loads(result.stderr)
    assert payload["error"]["status"] == 500
    assert "server failed" in payload["error"]["user_message"].lower()
    assert payload["error"]["next_step"]


def test_normalize_batch_add_accepts_a_bare_link_list():
    normalized = normalize_batch_add([{"id": "link-1", "event_id": EVENT_ID, "calendar_id": CALENDAR_ID}])
    assert normalized["results"][0]["ok"] is True
    assert normalized["results"][0]["event_id"] == EVENT_ID
    assert normalized["warnings"] == []


def test_normalize_batch_add_rejects_a_plain_string():
    try:
        normalize_batch_add("nope")
    except ServerError as exc:
        assert "unexpected" in exc.user_message.lower()
    else:
        raise AssertionError("a plain body should not be treated as links")


def test_failed_login_does_not_save_credentials(mock_token_file, mock_config_file):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/token", json={"detail": "Invalid credentials"}, status=401)
        result = CliRunner().invoke(
            cli,
            ["auth", "login", "--email", "a@example.com", "--password", "wrong", "--host", API],
        )
    assert result.exit_code == EXIT_AUTH
    assert peek_token(API) is None
    status = CliRunner().invoke(cli, ["auth", "status", "--host", API])
    assert "Status: saved" not in status.output
    assert "not authenticated" in status.output.lower()


def test_login_does_not_save_a_rejected_token(mock_token_file, mock_config_file):
    token = jwt.encode({"sub": "user", "exp": 9999999999}, "test-secret", algorithm="HS256")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{API}/auth/token", body=f'"{token}"', status=200)
        rsps.add(responses.GET, f"{API}/auth/me", json={"detail": "Invalid token"}, status=401)
        result = CliRunner().invoke(
            cli,
            ["auth", "login", "--email", "a@example.com", "--password", "secret", "--json", "--host", API],
        )
    assert result.exit_code == EXIT_AUTH, result.output
    assert peek_token(API) is None
    assert "Status: saved" not in result.output


def test_auth_status_reports_valid_expired_and_invalid(mock_token_file, mock_config_file):
    current = jwt.encode({"sub": "user", "exp": 9999999999}, "test-secret", algorithm="HS256")
    expired = jwt.encode({"sub": "user", "exp": 1}, "test-secret", algorithm="HS256")
    runner = CliRunner()

    save_token(API, current)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"email": "a@example.com"}, status=200)
        valid = runner.invoke(cli, ["auth", "status", "--json", "--host", API])
    assert json.loads(valid.stdout)["status"] == "valid"

    save_token(API, expired)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"detail": "Invalid token"}, status=401)
        old = runner.invoke(cli, ["auth", "status", "--host", API])
    assert old.exit_code == EXIT_OK
    assert "Status: expired" in old.output
    assert "Status: saved" not in old.output

    save_token(API, current)
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"detail": "Invalid token"}, status=401)
        rejected = runner.invoke(cli, ["auth", "status", "--json", "--host", API])
    assert json.loads(rejected.stdout)["status"] == "invalid"
    assert json.loads(rejected.stdout)["authenticated"] is False


def test_agenda_list_json_includes_calendar_and_month_counts(mock_token_file):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.get_agenda.return_value = load_fixture("agenda_batch.json")

    def _get_client(*args, **kwargs):
        return client

    import anymoment.cli.commands as commands

    original = commands.get_client
    commands.get_client = _get_client
    try:
        result = CliRunner().invoke(
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
    finally:
        commands.get_client = original
    assert result.exit_code == EXIT_OK, result.output
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert summary["events"] == 2
    assert summary["instances"] == 2
    assert summary["by_calendar"][0]["calendar_id"] == CALENDAR_ID
    assert summary["by_calendar"][0]["events"] == 2
    assert summary["by_month"] == [{"month": "2026-10", "events": 2, "instances": 2}]
    assert summary["by_calendar"][0]["name"] == "Work"


def test_agenda_list_human_summary(mock_token_file, monkeypatch):
    client = __import__("unittest").mock.MagicMock()
    client.get_agenda.return_value = load_fixture("agenda_batch.json")
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(
        cli,
        ["agenda", "list", "--start", "2026-10-14T00:00:00Z", "--end", "2026-10-14T23:59:59Z"],
    )
    assert result.exit_code == EXIT_OK, result.output
    assert "Calendars:" in result.output
    assert "2026-10" in result.output
    assert "Work" in result.output


def test_summarize_agenda_counts_an_event_on_two_calendars():
    summary = summarize_agenda(
        [
            {
                "event": {"calendar_ids": ["cal-a", "cal-b"], "name": "Shared"},
                "instances": [{"start": "2026-11-02T10:00:00Z"}],
            }
        ]
    )
    assert summary["events"] == 1
    assert [row["calendar_id"] for row in summary["by_calendar"]] == ["cal-a", "cal-b"]
    assert summary["by_month"][0]["month"] == "2026-11"


def test_old_python_exits_with_install_help(monkeypatch, capsys):
    monkeypatch.setattr("anymoment_entry.sys.version_info", (3, 9, 6, "final", 0))
    try:
        anymoment_entry.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Python 3.9 should stop before the CLI starts")
    message = capsys.readouterr().err
    assert "Python 3.10" in message
    assert "3.9.6" in message
    assert 'uv tool install "anymoment[cli]"' in message
    assert 'pipx install "anymoment[cli]"' in message
    assert "requires a different Python" in message


def test_schema_lists_add_and_import():
    payload = json.loads(CliRunner().invoke(cli, ["schema"]).stdout)
    assert "events add" in payload["commands"]
    assert "events import" in payload["commands"]


def test_check_credentials_does_not_refresh(mock_token_file):
    client = Client(api_url=API, token="not-a-jwt")
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.GET, f"{API}/auth/me", json={"detail": "Invalid token"}, status=401)
        rsps.add(responses.GET, f"{API}/auth/token/extend", body='"refreshed"', status=200)
        status = client.check_credentials()
        extended = [call for call in rsps.calls if call.request.url.endswith("/auth/token/extend")]
    assert status == "invalid"
    assert extended == []
