"""Token management with encrypted storage for AnyMoment SDK."""

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from anymoment.exceptions import TokenError

TOKEN_DIR = Path.home() / ".anymoment"
TOKEN_FILE = TOKEN_DIR / "tokens.json"


def _get_fernet() -> Fernet:
    """Get Fernet instance with machine-specific key."""
    import base64
    import hashlib
    
    # Derive a stable key from machine-specific information
    machine_id = platform.node()
    user_home = str(Path.home())
    key_material = f"{machine_id}:{user_home}:anymoment-token-key".encode()
    
    # Use PBKDF2 to derive a 32-byte key
    salt = hashlib.sha256(key_material).digest()[:16]  # 16-byte salt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    key = kdf.derive(key_material)
    
    # Fernet requires a URL-safe base64-encoded 32-byte key
    key_b64 = base64.urlsafe_b64encode(key)
    
    return Fernet(key_b64)


def _ensure_token_dir() -> None:
    """Ensure the token directory exists."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)


def _load_tokens() -> Dict[str, Any]:
    """Load encrypted tokens from file."""
    _ensure_token_dir()
    
    if not TOKEN_FILE.exists():
        return {}
    
    try:
        with open(TOKEN_FILE, "r") as f:
            encrypted_data = json.load(f)
        
        # Decrypt tokens
        fernet = _get_fernet()
        decrypted_data = {}
        
        for host_url, token_data in encrypted_data.items():
            try:
                decrypted_token = fernet.decrypt(token_data["token"].encode()).decode()
                decrypted_data[host_url] = {
                    "token": decrypted_token,
                    "expires_at": token_data.get("expires_at"),
                }
            except Exception as e:
                # Skip invalid tokens
                continue
        
        return decrypted_data
    except (json.JSONDecodeError, IOError) as e:
        raise TokenError(f"Failed to load tokens: {e}")


def _save_tokens(tokens: dict[str, Any]) -> None:
    """Save encrypted tokens to file."""
    _ensure_token_dir()
    
    try:
        fernet = _get_fernet()
        encrypted_data = {}
        
        for host_url, token_data in tokens.items():
            encrypted_token = fernet.encrypt(token_data["token"].encode()).decode()
            encrypted_data[host_url] = {
                "token": encrypted_token,
                "expires_at": token_data.get("expires_at"),
            }
        
        with open(TOKEN_FILE, "w") as f:
            json.dump(encrypted_data, f, indent=2)
    except IOError as e:
        raise TokenError(f"Failed to save tokens: {e}")


def _is_token_expired(token: str) -> bool:
    """Check if a JWT token is expired.
    
    Returns True if token is expired or invalid (can't be decoded).
    Returns False if token is valid and not expired (or has no expiration).
    """
    if not token:
        return True
    
    # Basic JWT format check - should have 3 parts separated by dots
    if not isinstance(token, str) or token.count('.') < 2:
        # Not a valid JWT format - treat as expired/invalid
        return True
    
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if exp is None:
            # No expiration means permanent token - never expired
            return False
        
        now = datetime.now(timezone.utc).timestamp()
        return now >= exp
    except jwt.DecodeError:
        # Invalid JWT format - can't determine expiration, assume expired for safety
        return True
    except Exception:
        # Other errors (e.g., invalid token structure) - assume expired for safety
        return True


def get_token(host_url: str) -> Optional[str]:
    """Get stored token for a host URL."""
    tokens = _load_tokens()
    token_data = tokens.get(host_url)
    
    if not token_data:
        return None
    
    token = token_data["token"]
    
    # Check if expired
    if _is_token_expired(token):
        return None
    
    return token


def save_token(host_url: str, token: str) -> None:
    """Save token for a host URL."""
    tokens = _load_tokens()
    
    # Decode token to get expiration
    expires_at = None
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if exp:
            expires_at = exp
    except Exception:
        pass
    
    tokens[host_url] = {
        "token": token,
        "expires_at": expires_at,
    }
    
    _save_tokens(tokens)


def delete_token(host_url: str) -> None:
    """Delete token for a host URL."""
    tokens = _load_tokens()
    if host_url in tokens:
        del tokens[host_url]
        _save_tokens(tokens)


def clear_all_tokens() -> None:
    """Clear all stored tokens."""
    _save_tokens({})


def list_tokens() -> Dict[str, Any]:
    """List all stored tokens with their status."""
    tokens = _load_tokens()
    result = {}
    
    for host_url, token_data in tokens.items():
        token = token_data.get("token")
        if not token:
            continue
            
        is_expired = _is_token_expired(token)
        
        # Check if token is invalid (not a proper JWT)
        is_invalid = False
        if token and isinstance(token, str) and token.count('.') < 2:
            is_invalid = True
        
        expires_at = token_data.get("expires_at")
        expires_str = None
        if expires_at:
            try:
                expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                expires_str = expires_dt.isoformat()
            except (ValueError, OSError):
                # Invalid timestamp, treat as never expires
                expires_str = None
        
        result[host_url] = {
            "expired": is_expired,
            "invalid": is_invalid,
            "expires_at": expires_str,
        }
    
    return result
