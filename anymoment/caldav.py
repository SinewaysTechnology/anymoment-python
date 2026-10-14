"""Experimental CalDAV client.

Remote credential failures use the CalDAV error shape and must not refresh
the AnyMoment session token. This namespace calls the same _request path
as the rest of the SDK, which already skips refresh for /caldav.
"""

from typing import Any, Optional


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _credentials(
    address: str,
    username: str,
    password: str,
    display_label: Optional[str] = None,
    provider_kind: Optional[str] = None,
    tls_pin_sha256: Optional[str] = None,
) -> dict[str, Any]:
    return _omit_none(
        {
            "address": address,
            "username": username,
            "password": password,
            "display_label": display_label,
            "provider_kind": provider_kind,
            "tls_pin_sha256": tls_pin_sha256,
        }
    )


class CalDavClient:
    """Experimental CalDAV API, exposed as client.caldav."""

    def __init__(self, client: Any):
        self._client = client

    def capabilities(self) -> Any:
        return self._client._request("GET", "/caldav/capabilities")

    def discover(
        self,
        address: str,
        username: str,
        password: str,
        display_label: Optional[str] = None,
        provider_kind: Optional[str] = None,
        tls_pin_sha256: Optional[str] = None,
    ) -> Any:
        return self._client._request(
            "POST",
            "/caldav/discover",
            json_data=_credentials(
                address, username, password, display_label, provider_kind, tls_pin_sha256
            ),
        )

    def test_connection(
        self,
        address: str,
        username: str,
        password: str,
        display_label: Optional[str] = None,
        provider_kind: Optional[str] = None,
        tls_pin_sha256: Optional[str] = None,
    ) -> Any:
        return self._client._request(
            "POST",
            "/caldav/accounts/test",
            json_data=_credentials(
                address, username, password, display_label, provider_kind, tls_pin_sha256
            ),
        )

    def list_accounts(self) -> Any:
        return self._client._request("GET", "/caldav/accounts")

    def create_account(
        self,
        address: str,
        username: str,
        password: str,
        display_label: Optional[str] = None,
        provider_kind: Optional[str] = None,
        tls_pin_sha256: Optional[str] = None,
    ) -> Any:
        return self._client._request(
            "POST",
            "/caldav/accounts",
            json_data=_credentials(
                address, username, password, display_label, provider_kind, tls_pin_sha256
            ),
        )

    def get_account(self, account_id: str) -> Any:
        return self._client._request("GET", f"/caldav/accounts/{account_id}")

    def update_account(
        self,
        account_id: str,
        display_label: Optional[str] = None,
        tls_pin_sha256: Optional[str] = None,
    ) -> Any:
        data = _omit_none({"display_label": display_label, "tls_pin_sha256": tls_pin_sha256})
        return self._client._request("PATCH", f"/caldav/accounts/{account_id}", json_data=data)

    def refresh_calendars(self, account_id: str) -> Any:
        return self._client._request("POST", f"/caldav/accounts/{account_id}/calendars/refresh")

    def start_login_flow(self, server_url: str) -> Any:
        return self._client._request(
            "POST",
            "/caldav/login-flow/start",
            json_data={"server_url": server_url},
        )

    def poll_login_flow(
        self,
        poll_endpoint: str,
        poll_token: str,
        login_url: Optional[str] = None,
    ) -> Any:
        data = _omit_none(
            {
                "poll_endpoint": poll_endpoint,
                "poll_token": poll_token,
                "login_url": login_url,
            }
        )
        return self._client._request("POST", "/caldav/login-flow/poll", json_data=data)

    def list_links(self, account_id: str) -> Any:
        return self._client._request("GET", f"/caldav/accounts/{account_id}/links")

    def create_links(self, account_id: str, calendars: list) -> Any:
        return self._client._request(
            "POST",
            f"/caldav/accounts/{account_id}/links",
            json_data={"calendars": calendars},
        )

    def create_destination(
        self,
        account_id: str,
        local_calendar_id: str,
        display_name: Optional[str] = None,
        remote_href: Optional[str] = None,
    ) -> Any:
        data = _omit_none(
            {
                "local_calendar_id": local_calendar_id,
                "display_name": display_name,
                "remote_href": remote_href,
            }
        )
        return self._client._request(
            "POST",
            f"/caldav/accounts/{account_id}/destinations",
            json_data=data,
        )

    def refresh(self) -> Any:
        return self._client._request("POST", "/caldav/refresh")

    def mark_remote_deleted(self, link_id: str, action: str) -> Any:
        return self._client._request(
            "POST",
            f"/caldav/links/{link_id}/remote-deleted",
            json_data={"action": action},
        )

    def sync_health(self) -> Any:
        return self._client._request("GET", "/caldav/sync-health")

    def quarantine(self, status: Optional[str] = None) -> Any:
        params = _omit_none({"status": status})
        return self._client._request("GET", "/caldav/quarantine", params=params or None)

    def resolve_quarantine(self, quarantine_id: str, resolution: str) -> Any:
        return self._client._request(
            "POST",
            f"/caldav/quarantine/{quarantine_id}/resolve",
            params={"resolution": resolution},
        )

    def enable_push(self, account_id: str) -> Any:
        return self._client._request("POST", f"/caldav/accounts/{account_id}/push")

    def fetch_certificate(self, address: str) -> Any:
        return self._client._request(
            "POST",
            "/caldav/certificate",
            json_data={"address": address},
        )

    def disconnect_preview(self, account_id: str) -> Any:
        return self._client._request("GET", f"/caldav/accounts/{account_id}/disconnect-preview")

    def reconnect(self, account_id: str, password: str) -> Any:
        return self._client._request(
            "POST",
            f"/caldav/accounts/{account_id}/reconnect",
            json_data={"password": password},
        )

    def disconnect(
        self,
        account_id: str,
        remove_imported: Optional[bool] = None,
        remove_remote_managed: Optional[bool] = None,
    ) -> Any:
        data = _omit_none(
            {"remove_imported": remove_imported, "remove_remote_managed": remove_remote_managed}
        )
        return self._client._request(
            "POST",
            f"/caldav/accounts/{account_id}/disconnect",
            json_data=data,
        )
