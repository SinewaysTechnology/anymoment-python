"""Tests for CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from anymoment.cli.commands import cli, get_client


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_client(monkeypatch):
    """Mock client for CLI tests.
    
    This fixture ensures get_client() returns a mock client, preventing
    real API calls and token lookups.
    """
    client = MagicMock()
    # Create a wrapper function that always returns the mock client
    def mock_get_client(*args, **kwargs):
        return client
    # Patch get_client at the module level to ensure it's used everywhere
    monkeypatch.setattr("anymoment.cli.commands.get_client", mock_get_client)
    yield client


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "AnyMoment CLI" in result.output


def test_auth_login(runner, mock_token_file):
    """Test login command."""
    # Use mock_token_file to ensure no real token file is written
    # Patch Client.login to avoid real API calls and token saving
    with patch("anymoment.cli.commands.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.login.return_value = "test-token-123"
        
        result = runner.invoke(
            cli,
            ["auth", "login"],
            input="test@example.com\ntest-password\n",
        )
        
        assert result.exit_code == 0
        assert "Login successful" in result.output
        mock_client.login.assert_called_once()


def test_auth_logout(runner, mock_token_file):
    """Test logout command."""
    # Use mock_token_file to ensure we're not deleting real tokens
    with patch("anymoment.cli.commands.delete_token") as mock_delete:
        result = runner.invoke(cli, ["auth", "logout"])
        assert result.exit_code == 0
        mock_delete.assert_called_once()


def test_tokens_list(runner, mock_token_file):
    """Test tokens list command."""
    # Use mock_token_file to ensure we're reading from test data, not real tokens
    with patch("anymoment.cli.commands.list_tokens") as mock_list:
        mock_list.return_value = {
            "https://api.anymoment.sineways.tech": {
                "expired": False,
                "expires_at": "2026-12-31T00:00:00Z",
            }
        }
        result = runner.invoke(cli, ["tokens", "list"])
        assert result.exit_code == 0
        assert "api.anymoment.sineways.tech" in result.output


def test_tokens_clear(runner, mock_token_file):
    """Test tokens clear command."""
    # Use mock_token_file to ensure we're not clearing real tokens
    with patch("anymoment.cli.commands.clear_all_tokens") as mock_clear:
        result = runner.invoke(cli, ["tokens", "clear"])
        assert result.exit_code == 0
        mock_clear.assert_called_once()


def test_config_set_url(runner, mock_config_file):
    """Test config set-url command."""
    # Use mock_config_file to ensure we're not modifying real config
    with patch("anymoment.cli.commands.set_config") as mock_set:
        result = runner.invoke(cli, ["config", "set-url", "https://custom.api.com"])
        assert result.exit_code == 0
        mock_set.assert_called_once_with("default_api_url", "https://custom.api.com")


def test_config_show(runner, mock_config_file):
    """Test config show command."""
    # Use mock_config_file to ensure we're reading from test data, not real config
    # The mock_config_file fixture sets up a temp config, but we need to populate it
    from anymoment.config import set_config
    set_config("default_api_url", "https://api.anymoment.sineways.tech")
    set_config("default_timezone", "UTC")
    set_config("default_calendar_id", None)
    
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "default_api_url" in result.output or "Default Api Url" in result.output


def test_calendars_list(runner, mock_client, sample_calendar, mock_token_file):
    """Test calendars list command."""
    # Use mock_token_file to ensure we're not reading real tokens
    # mock_client fixture already patches get_client, so no real API calls
    mock_client.list_calendars.return_value = [sample_calendar]
    
    result = runner.invoke(cli, ["calendars", "list"])
    if result.exit_code != 0:
        print(f"\n=== DEBUG INFO ===")
        print(f"Exit code: {result.exit_code}")
        print(f"Output:\n{result.output}")
        if result.exception:
            print(f"Exception: {result.exception}")
            import traceback
            traceback.print_exception(type(result.exception), result.exception, result.exception.__traceback__)
    assert result.exit_code == 0, f"Command failed with exit code {result.exit_code}. Output: {result.output}"
    assert "Test Calendar" in result.output


def test_calendars_create(runner, mock_client, sample_calendar, mock_token_file):
    """Test calendars create command."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.create_calendar.return_value = sample_calendar
    
    result = runner.invoke(
        cli,
        ["calendars", "create", "Test Calendar", "--timezone", "UTC"],
    )
    assert result.exit_code == 0
    mock_client.create_calendar.assert_called_once()


def test_calendars_get(runner, mock_client, sample_calendar, mock_token_file):
    """Test calendars get command."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.get_calendar.return_value = sample_calendar
    
    result = runner.invoke(cli, ["calendars", "get", "550e8400-e29b-41d4-a716-446655440000"])
    assert result.exit_code == 0
    assert "Test Calendar" in result.output


def test_events_create(runner, mock_client, sample_event, mock_token_file):
    """Test events create command."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.create_event_from_text.return_value = sample_event
    
    result = runner.invoke(
        cli,
        ["events", "create", "Every Monday at 10 AM"],
    )
    assert result.exit_code == 0
    mock_client.create_event_from_text.assert_called_once()


def test_events_list(runner, mock_client, sample_event, mock_token_file):
    """Test events list command."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.list_events.return_value = [sample_event]
    
    result = runner.invoke(cli, ["events", "list"])
    assert result.exit_code == 0
    assert "Test Event" in result.output


def test_users_me(runner, mock_client, sample_user, mock_token_file):
    """Test users me command."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.get_user_info.return_value = sample_user
    
    result = runner.invoke(cli, ["users", "me"])
    assert result.exit_code == 0
    assert "test@example.com" in result.output


def test_raw_output(runner, mock_client, sample_calendar, mock_token_file):
    """Test --raw output format."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.list_calendars.return_value = [sample_calendar]
    
    result = runner.invoke(cli, ["calendars", "list", "--raw"])
    assert result.exit_code == 0
    # Should be JSON
    import json
    data = json.loads(result.output)
    assert isinstance(data, list)


def test_pipe_output(runner, mock_client, sample_calendar, mock_token_file):
    """Test --pipe output format."""
    # Use mock_token_file to ensure we're not reading real tokens
    mock_client.list_calendars.return_value = [sample_calendar]
    
    result = runner.invoke(cli, ["calendars", "list", "--pipe"])
    assert result.exit_code == 0
    # Should only contain the ID
    assert sample_calendar["id"] in result.output
    assert "Test Calendar" not in result.output


def test_agenda_list(runner, mock_client, mock_token_file):
    """Smoke test: agenda list with explicit start/end."""
    mock_client.get_agenda.return_value = [
        {
            "event": {"id": "ev-1", "name": "Standup", "display_name": "Daily standup", "is_active": True},
            "instances": [
                {"start": "2025-02-03T09:00:00Z", "end": "2025-02-03T09:30:00Z", "is_all_day": False}
            ],
        }
    ]
    result = runner.invoke(
        cli,
        ["agenda", "list", "--start", "2025-02-03T00:00:00Z", "--end", "2025-02-03T23:59:59Z"],
    )
    assert result.exit_code == 0
    mock_client.get_agenda.assert_called_once()
    call_kw = mock_client.get_agenda.call_args[1]
    assert call_kw["start"] == "2025-02-03T00:00:00Z"
    assert call_kw["end"] == "2025-02-03T23:59:59Z"
    assert "Standup" in result.output or "Daily standup" in result.output
    assert "2025-02-03" in result.output


def test_agenda_list_with_calendar(runner, mock_client, mock_token_file):
    """Agenda list with --calendar passes single or comma-separated IDs to client."""
    mock_client.get_agenda.return_value = []
    result = runner.invoke(
        cli,
        [
            "agenda", "list",
            "--start", "2025-02-03T00:00:00Z",
            "--end", "2025-02-03T23:59:59Z",
            "--calendar", "4032c894-59fc-4126-9975-e75771d9550c",
        ],
    )
    assert result.exit_code == 0
    mock_client.get_agenda.assert_called_once()
    call_kw = mock_client.get_agenda.call_args[1]
    assert call_kw["calendar_ids"] == ["4032c894-59fc-4126-9975-e75771d9550c"]


def test_agenda_list_pipe(runner, mock_client, mock_token_file):
    """Agenda list --pipe outputs event IDs only."""
    mock_client.get_agenda.return_value = [
        {"event": {"id": "ev-1", "name": "Meeting"}, "instances": []},
    ]
    result = runner.invoke(
        cli,
        ["agenda", "list", "--start", "2025-02-03T00:00:00Z", "--end", "2025-02-03T23:59:59Z", "--pipe"],
    )
    assert result.exit_code == 0
    assert "ev-1" in result.output
    assert "Meeting" not in result.output


def test_agenda_search(runner, mock_client, mock_token_file):
    """Smoke test: agenda search with query."""
    mock_client.search_events.return_value = [
        {
            "event": {"id": "ev-2", "name": "Team sync", "is_active": True},
            "score": 0.75,
            "instances": None,
        }
    ]
    result = runner.invoke(cli, ["agenda", "search", "sync"])
    assert result.exit_code == 0
    mock_client.search_events.assert_called_once()
    call_kw = mock_client.search_events.call_args[1]
    assert call_kw["q"] == "sync"
    assert "Team sync" in result.output
    assert "score" in result.output.lower() or "0.75" in result.output
