"""Pytest fixtures for AnyMoment tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from anymoment.client import Client


@pytest.fixture
def mock_token_file(tmp_path, monkeypatch):
    """Mock token file location.
    
    This fixture ensures tests use a temporary directory for token storage,
    preventing tests from reading or writing real user tokens.
    """
    token_dir = tmp_path / ".anymoment"
    token_dir.mkdir()
    token_file = token_dir / "tokens.json"
    
    # Patch the token file path at module level to ensure all imports use it
    monkeypatch.setattr("anymoment.token_manager.TOKEN_DIR", token_dir)
    monkeypatch.setattr("anymoment.token_manager.TOKEN_FILE", token_file)
    
    # Ensure the file doesn't exist initially
    if token_file.exists():
        token_file.unlink()
    
    return token_file


@pytest.fixture
def mock_config_file(tmp_path, monkeypatch):
    """Mock config file location.
    
    This fixture ensures tests use a temporary directory for config storage,
    preventing tests from reading or writing real user configuration.
    """
    config_dir = tmp_path / ".anymoment"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    
    # Patch the config file path at module level to ensure all imports use it
    monkeypatch.setattr("anymoment.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("anymoment.config.CONFIG_FILE", config_file)
    
    # Ensure the file doesn't exist initially
    if config_file.exists():
        config_file.unlink()
    
    return config_file


@pytest.fixture
def mock_api_response():
    """Create a mock API response.
    
    This fixture ensures all API calls are mocked and never hit real endpoints,
    preventing accidental modification of customer data.
    """
    def _create_response(status_code=200, json_data=None, text=None):
        response = MagicMock()
        response.status_code = status_code
        if json_data:
            response.json.return_value = json_data
            response.text = json.dumps(json_data)
        elif text:
            response.text = text
            response.json.side_effect = ValueError("Not JSON")
        else:
            response.json.return_value = {}
            response.text = "{}"
        return response
    return _create_response


@pytest.fixture
def sample_calendar():
    """Sample calendar data."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "Test Calendar",
        "description": "Test description",
        "timezone": "UTC",
        "color": "#FF5733",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "event_count": 0,
        "google_calendar_ids": [],
        "shared_with": [],
    }


@pytest.fixture
def sample_event():
    """Sample event data."""
    return {
        "id": "660e8400-e29b-41d4-a716-446655440001",
        "name": "Test Event",
        "description": "Test event description",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_user():
    """Sample user data."""
    return {
        "id": "770e8400-e29b-41d4-a716-446655440002",
        "email": "test@example.com",
        "is_active": True,
        "is_verified": True,
    }
