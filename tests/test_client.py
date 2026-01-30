"""Tests for client module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from anymoment.client import Client
from anymoment.exceptions import (
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)


def test_client_init_default(mock_config_file):
    """Test client initialization with default URL."""
    # Use mock_config_file to avoid reading/writing real config
    client = Client()
    assert client.api_url == "https://api.anymoment.sineways.tech"


def test_client_init_custom_url(mock_config_file):
    """Test client initialization with custom URL."""
    # Use mock_config_file to avoid reading/writing real config
    client = Client(api_url="https://custom.api.com")
    assert client.api_url == "https://custom.api.com"


def test_client_init_with_token(mock_config_file):
    """Test client initialization with token."""
    # Use mock_config_file to avoid reading/writing real config
    token = "test-token-123"
    client = Client(token=token)
    assert client._token == token


@patch("anymoment.client.requests.Session")
@patch("anymoment.client.save_token")
def test_login_success(mock_save_token, mock_session_class, mock_api_response):
    """Test successful login."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=200, text='"test-token-123"')
    mock_session.post.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech")
    token = client.login("test@example.com", "password")
    
    assert token == "test-token-123"
    mock_session.post.assert_called_once()
    # Verify token was saved (but mocked, so no real file I/O)
    mock_save_token.assert_called_once_with("https://api.anymoment.sineways.tech", "test-token-123")


@patch("anymoment.client.requests.Session")
@patch("anymoment.client.save_token")
def test_login_failure(mock_save_token, mock_session_class, mock_api_response):
    """Test login failure."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=401, json_data={"detail": "Invalid credentials"})
    mock_session.post.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech")
    
    with pytest.raises(AuthenticationError):
        client.login("test@example.com", "wrong-password")
    
    # Verify token was NOT saved on failure
    mock_save_token.assert_not_called()


@patch("anymoment.client.requests.Session")
def test_get_user_info(mock_session_class, mock_api_response, sample_user):
    """Test getting user info."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=200, json_data=sample_user)
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    user = client.get_user_info()
    
    assert user == sample_user
    mock_session.request.assert_called_once()


@patch("anymoment.client.requests.Session")
def test_list_calendars(mock_session_class, mock_api_response, sample_calendar):
    """Test listing calendars."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=200, json_data=[sample_calendar])
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    calendars = client.list_calendars()
    
    assert len(calendars) == 1
    assert calendars[0] == sample_calendar


@patch("anymoment.client.requests.Session")
def test_create_calendar(mock_session_class, mock_api_response, sample_calendar):
    """Test creating a calendar."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=201, json_data=sample_calendar)
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    calendar = client.create_calendar(name="Test Calendar", timezone="UTC")
    
    assert calendar == sample_calendar
    mock_session.request.assert_called_once()


@patch("anymoment.client.requests.Session")
def test_get_calendar(mock_session_class, mock_api_response, sample_calendar):
    """Test getting a calendar."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=200, json_data=sample_calendar)
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    calendar = client.get_calendar("550e8400-e29b-41d4-a716-446655440000")
    
    assert calendar == sample_calendar


@patch("anymoment.client.requests.Session")
def test_not_found_error(mock_session_class, mock_api_response):
    """Test handling 404 errors."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=404, json_data={"detail": "Not found"})
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    
    with pytest.raises(NotFoundError):
        client.get_calendar("invalid-id")


@patch("anymoment.client.requests.Session")
def test_validation_error(mock_session_class, mock_api_response):
    """Test handling 400 errors."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=400, json_data={"detail": "Validation error"})
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    
    with pytest.raises(ValidationError):
        client.create_calendar(name="", timezone="UTC")


@patch("anymoment.client.requests.Session")
def test_server_error(mock_session_class, mock_api_response):
    """Test handling 500 errors."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=500, json_data={"detail": "Server error"})
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    
    with pytest.raises(ServerError):
        client.list_calendars()


@patch("anymoment.client.requests.Session")
def test_create_event_from_text(mock_session_class, mock_api_response, sample_event):
    """Test creating an event from natural language."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    
    response = mock_api_response(status_code=201, json_data=sample_event)
    mock_session.request.return_value = response
    
    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    event = client.create_event_from_text("Every Monday at 10 AM")
    
    assert event == sample_event
    # Verify the request was made with correct data
    call_args = mock_session.request.call_args
    assert call_args[1]["json"]["recurrence_text"] == "Every Monday at 10 AM"


@patch("anymoment.client.requests.Session")
def test_get_agenda(mock_session_class, mock_api_response):
    """Test get_agenda: path, params (start/end ISO), return value."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    agenda_response = [
        {"event": {"id": "ev-1", "name": "Meeting"}, "instances": [{"start": "2025-02-03T09:00:00Z", "end": "2025-02-03T10:00:00Z", "is_all_day": False}]}
    ]
    response = mock_api_response(status_code=200, json_data=agenda_response)
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    result = client.get_agenda(start="2025-02-03T00:00:00Z", end="2025-02-09T23:59:59Z")

    assert result == agenda_response
    mock_session.request.assert_called_once()
    call_kw = mock_session.request.call_args[1]
    assert call_kw["method"] == "GET"
    assert call_kw["params"]["start"] == "2025-02-03T00:00:00Z"
    assert call_kw["params"]["end"] == "2025-02-09T23:59:59Z"
    assert call_kw["params"]["use_cache"] is True
    assert call_kw["url"].endswith("/agenda") or "/agenda" in call_kw["url"]


@patch("anymoment.client.requests.Session")
def test_get_agenda_datetime_naive_serialized_as_utc(mock_session_class, mock_api_response):
    """Test get_agenda with naive datetime: serialized params are UTC (Z)."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    response = mock_api_response(status_code=200, json_data=[])
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    start_dt = datetime(2025, 2, 3, 0, 0, 0)
    end_dt = datetime(2025, 2, 9, 23, 59, 59)
    client.get_agenda(start=start_dt, end=end_dt)

    call_kw = mock_session.request.call_args[1]
    assert "Z" in call_kw["params"]["start"] or "+00:00" in call_kw["params"]["start"]
    assert "Z" in call_kw["params"]["end"] or "+00:00" in call_kw["params"]["end"]


@patch("anymoment.client.requests.Session")
def test_get_agenda_datetime_aware(mock_session_class, mock_api_response):
    """Test get_agenda with timezone-aware datetime: serialized params are ISO with offset."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    response = mock_api_response(status_code=200, json_data=[])
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    start_dt = datetime(2025, 2, 3, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2025, 2, 9, 23, 59, 59, tzinfo=timezone.utc)
    client.get_agenda(start=start_dt, end=end_dt)

    call_kw = mock_session.request.call_args[1]
    assert "2025-02-03" in call_kw["params"]["start"]
    assert "2025-02-09" in call_kw["params"]["end"]


@patch("anymoment.client.requests.Session")
def test_get_agenda_with_calendar_ids(mock_session_class, mock_api_response):
    """Test get_agenda with calendar_ids and use_cache=False."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    response = mock_api_response(status_code=200, json_data=[])
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    client.get_agenda(
        start="2025-02-03T00:00:00Z",
        end="2025-02-09T23:59:59Z",
        calendar_ids=["cal-1", "cal-2"],
        use_cache=False,
        include_webhooks=True,
    )

    call_kw = mock_session.request.call_args[1]
    assert call_kw["params"]["calendar_ids"] == ["cal-1", "cal-2"]
    assert call_kw["params"]["use_cache"] is False
    assert call_kw["params"]["include_webhooks"] is True


@patch("anymoment.client.requests.Session")
def test_search_events(mock_session_class, mock_api_response):
    """Test search_events: path, params (q required), return value."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    search_response = [
        {"event": {"id": "ev-1", "name": "Team meeting"}, "score": 0.85, "instances": None}
    ]
    response = mock_api_response(status_code=200, json_data=search_response)
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    result = client.search_events(q="meeting")

    assert result == search_response
    mock_session.request.assert_called_once()
    call_kw = mock_session.request.call_args[1]
    assert call_kw["params"]["q"] == "meeting"
    assert call_kw["params"]["limit"] == 50
    assert call_kw["params"]["offset"] == 0
    assert call_kw["params"]["include_instances"] is True
    assert "/agenda/search" in call_kw["url"]


@patch("anymoment.client.requests.Session")
def test_search_events_with_filters(mock_session_class, mock_api_response):
    """Test search_events with start, end, calendar_ids, is_active, limit, offset."""
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    response = mock_api_response(status_code=200, json_data=[])
    mock_session.request.return_value = response

    client = Client(api_url="https://api.anymoment.sineways.tech", token="test-token")
    client.search_events(
        q="standup",
        start="2025-02-01T00:00:00Z",
        end="2025-02-28T23:59:59Z",
        calendar_ids=["cal-1"],
        is_active=True,
        limit=10,
        offset=5,
        include_instances=False,
    )

    call_kw = mock_session.request.call_args[1]
    assert call_kw["params"]["q"] == "standup"
    assert call_kw["params"]["start"] == "2025-02-01T00:00:00Z"
    assert call_kw["params"]["end"] == "2025-02-28T23:59:59Z"
    assert call_kw["params"]["calendar_ids"] == ["cal-1"]
    assert call_kw["params"]["is_active"] is True
    assert call_kw["params"]["limit"] == 10
    assert call_kw["params"]["offset"] == 5
    assert call_kw["params"]["include_instances"] is False
