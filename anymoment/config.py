"""Configuration management for AnyMoment SDK."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from anymoment.exceptions import ConfigError

DEFAULT_API_URL = "https://api.anymoment.sineways.tech"
CONFIG_DIR = Path.home() / ".anymoment"
CONFIG_FILE = CONFIG_DIR / "config.json"


def ensure_config_dir() -> None:
    """Ensure the config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def active_config_file() -> Path:
    """Config file for the current profile, or the default file."""
    profile = os.getenv("ANYMOMENT_PROFILE")
    if profile:
        safe = "".join(ch for ch in profile if ch.isalnum() or ch in {"-", "_"})
        return CONFIG_DIR / f"config.{safe or 'default'}.json"
    return CONFIG_FILE


def load_config() -> dict[str, Any]:
    """Load configuration from file."""
    ensure_config_dir()
    config_file = active_config_file()

    if not config_file.exists():
        return {
            "default_api_url": DEFAULT_API_URL,
            "default_timezone": "UTC",
            "default_calendar_id": None,
        }
    
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
            # Ensure default_api_url is set
            if "default_api_url" not in config:
                config["default_api_url"] = DEFAULT_API_URL
            return config
    except (json.JSONDecodeError, IOError) as e:
        raise ConfigError(f"Failed to load configuration: {e}")


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    ensure_config_dir()

    try:
        with open(active_config_file(), "w") as f:
            json.dump(config, f, indent=2)
    except IOError as e:
        raise ConfigError(f"Failed to save configuration: {e}")


def get_config(key: str, default: Any = None) -> Any:
    """Get a configuration value."""
    config = load_config()
    return config.get(key, default)


def set_config(key: str, value: Any) -> None:
    """Set a configuration value."""
    config = load_config()
    config[key] = value
    save_config(config)


def get_api_url() -> str:
    """Get the default API URL from config or environment."""
    # Check environment variable first
    env_url = os.getenv("ANYMOMENT_BASE_URL")
    if env_url:
        return env_url
    
    # Then check config file
    return get_config("default_api_url", DEFAULT_API_URL)


def get_default_timezone() -> str:
    """Get the default timezone from config or environment."""
    # Check environment variable first
    env_tz = os.getenv("ANYMOMENT_DEFAULT_TIMEZONE")
    if env_tz:
        return env_tz
    
    # Then check config file
    return get_config("default_timezone", "UTC")


def get_default_calendar_id() -> Optional[str]:
    """Get the default calendar ID from config or environment."""
    # Check environment variable first
    env_cal = os.getenv("ANYMOMENT_DEFAULT_CALENDAR")
    if env_cal:
        return env_cal
    
    # Then check config file
    return get_config("default_calendar_id", None)
