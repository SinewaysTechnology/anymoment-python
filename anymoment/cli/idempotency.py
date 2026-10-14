"""Local idempotency cache.

The AnyMoment API does not accept an idempotency header. The CLI stores the
first successful stdout for a key under the config directory and replays it
when the same key is used again. This does not protect two machines.
"""

import json
from typing import Optional

_FILE_NAME = "idempotency.json"


def _path():
    from anymoment.config import CONFIG_DIR

    return CONFIG_DIR / _FILE_NAME


def _ensure():
    from anymoment.config import ensure_config_dir

    ensure_config_dir()


def _load() -> dict:
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def lookup(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    value = _load().get(key)
    return value if isinstance(value, str) else None


def store(key: Optional[str], output: str) -> None:
    if not key:
        return
    _ensure()
    data = _load()
    data[key] = output
    _path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
