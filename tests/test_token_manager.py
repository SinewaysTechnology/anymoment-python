"""Tests for token_manager module."""

import json
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from anymoment.exceptions import TokenError
from anymoment.token_manager import (
    clear_all_tokens,
    delete_token,
    get_token,
    list_tokens,
    save_token,
)


def test_save_and_get_token(mock_token_file):
    """Test saving and retrieving a token."""
    host_url = "https://api.anymoment.sineways.tech"
    # Use a valid JWT token format for testing
    import jwt
    token = jwt.encode({"sub": "test@example.com"}, "secret", algorithm="HS256")
    
    save_token(host_url, token)
    retrieved = get_token(host_url)
    
    assert retrieved == token


def test_token_encryption(mock_token_file):
    """Test that tokens are encrypted in storage."""
    host_url = "https://api.anymoment.sineways.tech"
    # Use a valid JWT token format for testing
    import jwt
    token = jwt.encode({"sub": "test@example.com"}, "secret", algorithm="HS256")
    
    save_token(host_url, token)
    
    # Read the file directly and verify it's encrypted
    with open(mock_token_file, "r") as f:
        data = json.load(f)
    
    assert host_url in data
    assert data[host_url]["token"] != token  # Should be encrypted
    assert isinstance(data[host_url]["token"], str)


def test_multiple_hosts(mock_token_file):
    """Test storing tokens for multiple hosts."""
    import jwt
    host1 = "https://api.anymoment.sineways.tech"
    host2 = "https://dev.api.anymoment.sineways.tech"
    token1 = jwt.encode({"sub": "test1@example.com"}, "secret", algorithm="HS256")
    token2 = jwt.encode({"sub": "test2@example.com"}, "secret", algorithm="HS256")
    
    save_token(host1, token1)
    save_token(host2, token2)
    
    assert get_token(host1) == token1
    assert get_token(host2) == token2


def test_delete_token(mock_token_file):
    """Test deleting a token."""
    import jwt
    host_url = "https://api.anymoment.sineways.tech"
    token = jwt.encode({"sub": "test@example.com"}, "secret", algorithm="HS256")
    
    save_token(host_url, token)
    assert get_token(host_url) == token
    
    delete_token(host_url)
    assert get_token(host_url) is None


def test_clear_all_tokens(mock_token_file):
    """Test clearing all tokens."""
    host1 = "https://api.anymoment.sineways.tech"
    host2 = "https://dev.api.anymoment.sineways.tech"
    
    save_token(host1, "token-1")
    save_token(host2, "token-2")
    
    clear_all_tokens()
    
    assert get_token(host1) is None
    assert get_token(host2) is None


def test_expired_token(mock_token_file):
    """Test that expired tokens are not returned."""
    host_url = "https://api.anymoment.sineways.tech"
    
    # Create an expired token
    exp = datetime.now(timezone.utc) - timedelta(hours=1)
    expired_token = jwt.encode(
        {"sub": "test@example.com", "exp": exp.timestamp()},
        "secret",
        algorithm="HS256",
    )
    
    save_token(host_url, expired_token)
    retrieved = get_token(host_url)
    
    assert retrieved is None


def test_valid_token(mock_token_file):
    """Test that valid tokens are returned."""
    host_url = "https://api.anymoment.sineways.tech"
    
    # Create a valid token (expires in 1 hour)
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    valid_token = jwt.encode(
        {"sub": "test@example.com", "exp": exp.timestamp()},
        "secret",
        algorithm="HS256",
    )
    
    save_token(host_url, valid_token)
    retrieved = get_token(host_url)
    
    assert retrieved == valid_token


def test_permanent_token(mock_token_file):
    """Test that permanent tokens (no exp) are returned."""
    host_url = "https://api.anymoment.sineways.tech"
    
    # Create a token without expiration
    permanent_token = jwt.encode(
        {"sub": "test@example.com"},
        "secret",
        algorithm="HS256",
    )
    
    save_token(host_url, permanent_token)
    retrieved = get_token(host_url)
    
    assert retrieved == permanent_token


def test_list_tokens(mock_token_file):
    """Test listing all tokens with their status."""
    host1 = "https://api.anymoment.sineways.tech"
    host2 = "https://dev.api.anymoment.sineways.tech"
    
    # Create valid and expired tokens
    exp_valid = datetime.now(timezone.utc) + timedelta(hours=1)
    exp_expired = datetime.now(timezone.utc) - timedelta(hours=1)
    
    valid_token = jwt.encode(
        {"sub": "test@example.com", "exp": exp_valid.timestamp()},
        "secret",
        algorithm="HS256",
    )
    expired_token = jwt.encode(
        {"sub": "test@example.com", "exp": exp_expired.timestamp()},
        "secret",
        algorithm="HS256",
    )
    
    save_token(host1, valid_token)
    save_token(host2, expired_token)
    
    tokens = list_tokens()
    
    assert host1 in tokens
    assert host2 in tokens
    assert tokens[host1]["expired"] is False
    assert tokens[host2]["expired"] is True
