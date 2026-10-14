"""Result objects returned by the AnyMoment client.

These are attribute objects, not dicts. Nested API documents stay dicts
so callers can still index fields such as external_origin["read_only"].
"""

from typing import Any


class AgendaResult:
    """Agenda window: expanded events plus per-event failures."""

    def __init__(self, events: list | None = None, failures: list | None = None):
        self.events = list(events or [])
        self.failures = list(failures or [])


class MutationResult:
    """Successful mutation body, including warnings the API attached."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __contains__(self, name: object) -> bool:
        return name in self._data

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def agenda_result(data: Any) -> AgendaResult:
    """Normalize a list (legacy) or {events, failures} body."""
    if isinstance(data, dict) and "events" in data:
        events = data.get("events") or []
        failures = data.get("failures") or []
        return AgendaResult(events, failures)
    if isinstance(data, list):
        return AgendaResult(data, [])
    return AgendaResult([], [])


def mutation_result(data: Any) -> Any:
    """Wrap a JSON object. Leave non-objects unchanged."""
    if isinstance(data, dict):
        return MutationResult(data)
    return data
