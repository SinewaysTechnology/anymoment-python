"""Google Calendar account and sync calls for the signed-in user."""

from typing import Any, Optional


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


class GoogleAPI:
    """Namespace at client.google. Does not call Google admin routes."""

    def __init__(self, client: Any):
        self._client = client

    def accounts(self) -> Any:
        """List connected Google accounts."""
        return self._client._request("GET", "/google/accounts")

    def delete_account(self, account_id: str) -> Any:
        """Disconnect one Google account."""
        return self._client._request("DELETE", f"/google/accounts/{account_id}")

    def sync_health(self, export_id: Optional[str] = None) -> Any:
        params = _omit_none({"export_id": export_id})
        return self._client._request("GET", "/google/sync-health", params=params or None)

    def quarantine(
        self,
        export_id: Optional[str] = None,
        status: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Any:
        params = _omit_none(
            {"export_id": export_id, "status": status, "provider": provider}
        )
        return self._client._request("GET", "/google/quarantine", params=params or None)

    def resolve_quarantine(self, quarantine_id: str, resolution: str) -> Any:
        return self._client._request(
            "POST",
            f"/google/quarantine/{quarantine_id}/resolve",
            params={"resolution": resolution},
        )

    def sync_status(self, job_id: str) -> Any:
        return self._client._request("GET", "/google/sync-status", params={"job_id": job_id})
