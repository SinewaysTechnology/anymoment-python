"""Human CLI: aliases, profiles, completion, color, and the calendar picker."""

import json

from click.testing import CliRunner

from anymoment.cli.commands import cli
from anymoment.cli.human import color_enabled
from anymoment.config import get_config, set_config

from tests.support import EXIT_OK, EXIT_USAGE


def test_color_respects_no_color_and_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert color_enabled() is False
    monkeypatch.setenv("NO_COLOR", "1")
    assert color_enabled() is False


def test_profile_stores_its_own_config(monkeypatch, mock_config_file, tmp_path):
    monkeypatch.setenv("ANYMOMENT_PROFILE", "work")
    set_config("default_timezone", "America/New_York")
    assert get_config("default_timezone") == "America/New_York"
    monkeypatch.delenv("ANYMOMENT_PROFILE", raising=False)
    assert get_config("default_timezone") == "UTC"


def test_profile_flag_is_applied(monkeypatch, mock_config_file, mock_token_file):
    monkeypatch.delenv("ANYMOMENT_PROFILE", raising=False)
    from unittest.mock import MagicMock

    client = MagicMock()
    client.get_user_info.return_value = {"email": "a@example.com"}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["--profile", "work", "users", "me", "--json"])
    assert result.exit_code == EXIT_OK
    assert json.loads(result.stdout)["email"] == "a@example.com"


def test_aliases_and_shortcuts(monkeypatch, mock_token_file, sample_calendar):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.list_calendars.return_value = [sample_calendar]
    client.get_agenda.return_value = {"events": [], "failures": []}
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    runner = CliRunner()
    listed = runner.invoke(cli, ["ls"])
    assert listed.exit_code == EXIT_OK
    assert "Test Calendar" in listed.output
    agenda = runner.invoke(cli, ["a", "list", "--start", "2026-10-14T00:00:00Z", "--end", "2026-10-14T23:59:59Z"])
    assert agenda.exit_code == EXIT_OK
    today = runner.invoke(cli, ["today", "--json"])
    assert today.exit_code == EXIT_OK
    assert "start" in json.loads(today.stdout)


def test_ambiguous_calendar_does_not_prompt_without_a_tty(monkeypatch, mock_token_file):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.list_calendars.return_value = [
        {"id": "cal-1", "name": "Work"},
        {"id": "cal-2", "name": "Work"},
    ]
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(cli, ["events", "list", "--calendar", "Work"])
    assert result.exit_code == EXIT_USAGE
    assert "picker" in result.stderr.lower()
    client.list_events.assert_not_called()


def test_completion_snippets():
    runner = CliRunner()
    bash = runner.invoke(cli, ["completion", "bash"])
    fish = runner.invoke(cli, ["completion", "fish"])
    assert bash.exit_code == EXIT_OK
    assert "_ANYMOMENT_COMPLETE=bash_source" in bash.stdout
    assert fish.exit_code == EXIT_OK
    assert "fish_source" in fish.stdout


def test_read_only_agenda_line(monkeypatch, mock_token_file):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.get_agenda.return_value = [
        {
            "event": {
                "id": "ev-1",
                "name": "Dentist",
                "display_name": "Dentist",
                "is_active": True,
                "external_origin": {"read_only": True, "provider_label": "CalDAV"},
            },
            "instances": [],
        }
    ]
    monkeypatch.setattr("anymoment.cli.commands.get_client", lambda *args, **kwargs: client)
    result = CliRunner().invoke(
        cli,
        ["agenda", "list", "--start", "2026-10-14T00:00:00Z", "--end", "2026-10-14T23:59:59Z"],
    )
    assert result.exit_code == EXIT_OK
    assert "read-only" in result.stdout
    assert "Dentist" in result.stdout
