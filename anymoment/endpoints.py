"""User-facing routes that sit next to the original client methods."""

from typing import Any, Optional

from anymoment.models import mutation_result


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


class EndpointsMixin:
    """Methods implemented by Client. _request is provided by the client."""

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        retry_on_auth_error: bool = True,
    ) -> Any:
        raise NotImplementedError

    def _datetime_to_iso(self, value: Any) -> str:
        raise NotImplementedError

    def resend_verification(self) -> Any:
        """POST /auth/resend-verification. One send per minute. No body."""
        return self._request("POST", "/auth/resend-verification")

    def signup(
        self,
        email: str,
        password: str,
        display_name: Optional[str] = None,
        preferred_timezone: Optional[str] = None,
        birthday: Optional[str] = None,
    ) -> Any:
        """Create an account. POST /auth/users."""
        data = _omit_none(
            {
                "email": email,
                "password": password,
                "display_name": display_name,
                "preferred_timezone": preferred_timezone,
                "birthday": birthday,
            }
        )
        return self._request("POST", "/auth/users", json_data=data)

    def change_password(self, new_password: str, old_password: Optional[str] = None) -> Any:
        """Change the signed-in user's password."""
        data = _omit_none({"new_password": new_password, "old_password": old_password})
        return self._request("POST", "/auth/users/change-password", json_data=data)

    def reset_password(self, user: Any, new_password: str) -> Any:
        """Reset a password. `user` is an email or a UserBase object."""
        if isinstance(user, str):
            user = {"email": user}
        return self._request(
            "POST",
            "/auth/users/reset-password",
            json_data={"user": user, "new_password": new_password},
        )

    def create_permanent_token(
        self,
        email: str,
        display_name: Optional[str] = None,
        preferred_timezone: Optional[str] = None,
        birthday: Optional[str] = None,
    ) -> Any:
        """Create a permanent token for the given user email."""
        data = _omit_none(
            {
                "email": email,
                "display_name": display_name,
                "preferred_timezone": preferred_timezone,
                "birthday": birthday,
            }
        )
        return self._request("POST", "/auth/permanent-token", json_data=data)

    def list_permanent_tokens(self) -> Any:
        """List permanent tokens."""
        return self._request("GET", "/auth/permanent-token")

    def delete_permanent_token(self, token: str) -> Any:
        """Revoke one permanent token."""
        return self._request("DELETE", "/auth/permanent-token", json_data={"token": token})

    def create_feedback(
        self,
        message: str,
        rating: Optional[int] = None,
        title: Optional[str] = None,
    ) -> Any:
        """Send product feedback."""
        data = _omit_none({"message": message, "rating": rating, "title": title})
        return self._request("POST", "/auth/feedback", json_data=data)

    def create_event(
        self,
        name: str,
        components: list,
        description: Optional[str] = None,
    ) -> Any:
        """Create an event from structured recurrence components."""
        data = _omit_none({"name": name, "components": components, "description": description})
        return mutation_result(self._request("POST", "/events", json_data=data))

    def get_events_batch(
        self,
        event_ids: list[str],
        is_active: Optional[bool] = None,
        minimal: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Any:
        """Fetch many events by id. POST /events/batch."""
        params = _omit_none(
            {
                "is_active": is_active,
                "minimal": True if minimal else None,
                "limit": limit,
                "offset": offset,
            }
        )
        return self._request(
            "POST",
            "/events/batch",
            params=params or None,
            json_data={"event_ids": event_ids},
        )

    def preview_event_from_text(
        self,
        name: str,
        recurrence_text: str,
        start: Any,
        end: Any,
        description: Optional[str] = None,
        timezone: str = "UTC",
        model: str = "high",
    ) -> Any:
        """Preview a natural-language event without saving it."""
        data = _omit_none(
            {
                "name": name,
                "recurrence_text": recurrence_text,
                "start": self._datetime_to_iso(start),
                "end": self._datetime_to_iso(end),
                "description": description,
                "timezone": timezone,
                "model": model,
            }
        )
        return self._request("POST", "/events/from-recurrence-text/preview", json_data=data)

    def create_event_from_ics(
        self,
        ics_content: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Any:
        """Create an event from an ICS document."""
        data = _omit_none(
            {
                "ics_content": ics_content,
                "name": name,
                "description": description,
                "timezone": timezone,
            }
        )
        return mutation_result(self._request("POST", "/events/from-ics", json_data=data))

    def list_event_feedback(
        self,
        value: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Any:
        """List event feedback the user has submitted."""
        params = _omit_none({"value": value, "limit": limit, "offset": offset})
        return self._request("GET", "/events/feedback", params=params or None)

    def create_event_feedback(self, value: int, event_data: dict, message: Optional[str] = None) -> Any:
        """Submit thumbs-up or thumbs-down feedback for an event."""
        data = _omit_none({"value": value, "event_data": event_data, "message": message})
        return self._request("POST", "/events/feedback", json_data=data)

    def list_guests(self, event_id: str) -> Any:
        return self._request("GET", f"/events/{event_id}/guests")

    def add_guest(self, event_id: str, **fields: Any) -> Any:
        """Add a guest. Fields match EventGuestCreate and empty ones are omitted."""
        return self._request(
            "POST",
            f"/events/{event_id}/guests",
            json_data=_omit_none(fields),
        )

    def update_guest(self, event_id: str, guest_id: str, **fields: Any) -> Any:
        return self._request(
            "PATCH",
            f"/events/{event_id}/guests/{guest_id}",
            json_data=_omit_none(fields),
        )

    def delete_guest(self, event_id: str, guest_id: str) -> Any:
        return self._request("DELETE", f"/events/{event_id}/guests/{guest_id}")

    def list_webhooks(self, event_id: str, is_active: Optional[bool] = None) -> Any:
        params = _omit_none({"is_active": is_active})
        return self._request("GET", f"/events/{event_id}/webhooks", params=params or None)

    def create_webhook(
        self,
        event_id: str,
        url: str,
        method: str,
        headers: Optional[dict] = None,
        include_event_data: Optional[bool] = None,
        is_active: Optional[bool] = None,
        offset: Optional[int] = None,
        offset_unit: Optional[str] = None,
    ) -> Any:
        data = _omit_none(
            {
                "url": url,
                "method": method,
                "headers": headers,
                "include_event_data": include_event_data,
                "is_active": is_active,
                "offset": offset,
                "offset_unit": offset_unit,
            }
        )
        return self._request("POST", f"/events/{event_id}/webhooks", json_data=data)

    def get_webhook(self, event_id: str, webhook_id: str) -> Any:
        return self._request("GET", f"/events/{event_id}/webhooks/{webhook_id}")

    def update_webhook(self, event_id: str, webhook_id: str, url: str, method: str, **fields: Any) -> Any:
        data = _omit_none({"url": url, "method": method, **fields})
        return self._request("PUT", f"/events/{event_id}/webhooks/{webhook_id}", json_data=data)

    def delete_webhook(self, event_id: str, webhook_id: str) -> Any:
        return self._request("DELETE", f"/events/{event_id}/webhooks/{webhook_id}")

    def list_webhook_runs(self, event_id: str, webhook_id: str) -> Any:
        return self._request("GET", f"/events/{event_id}/webhooks/{webhook_id}/runs")

    def get_calendar_instances(
        self,
        calendar_id: str,
        start: Any,
        end: Any,
        include_webhooks: bool = False,
        optimized: bool = False,
    ) -> Any:
        params = {
            "start": self._datetime_to_iso(start),
            "end": self._datetime_to_iso(end),
            "include_webhooks": include_webhooks,
            "optimized": optimized,
        }
        return self._request("GET", f"/calendars/{calendar_id}/instances", params=params)

    def get_loose_event_instances(
        self,
        start: Any,
        end: Any,
        include_webhooks: bool = False,
        optimized: bool = False,
    ) -> Any:
        params = {
            "start": self._datetime_to_iso(start),
            "end": self._datetime_to_iso(end),
            "include_webhooks": include_webhooks,
            "optimized": optimized,
        }
        return self._request("GET", "/calendars/loose-events/instances", params=params)

    def export_calendar(self, calendar_id: str, start: Any, end: Any) -> Any:
        """Download a calendar window as ICS text."""
        params = {"start": self._datetime_to_iso(start), "end": self._datetime_to_iso(end)}
        return self._request("GET", f"/calendars/{calendar_id}/export", params=params)

    def get_changes(self, since: str) -> Any:
        """Poll changes across calendars since a cursor."""
        return self._request("GET", "/refresh/changes", params={"since": since})

    def get_calendar_changes(self, calendar_id: str, since: str) -> Any:
        """Poll changes for one calendar since a cursor."""
        return self._request(
            "GET",
            f"/refresh/calendars/{calendar_id}/changes",
            params={"since": since},
        )

    def list_subscriptions(self, calendar_id: str) -> Any:
        """List outgoing webhook subscriptions. The secret is not included."""
        return self._request("GET", f"/calendars/{calendar_id}/subscriptions")

    def create_subscription(
        self,
        calendar_id: str,
        url: str,
        event_types: list[str],
        secret: Optional[str] = None,
        occurrence_offset_seconds: Optional[int] = None,
    ) -> Any:
        """Create a subscription. A generated secret is returned once."""
        data = _omit_none(
            {
                "url": url,
                "secret": secret,
                "event_types": event_types,
                "occurrence_offset_seconds": occurrence_offset_seconds,
            }
        )
        return self._request(
            "POST",
            f"/calendars/{calendar_id}/subscriptions",
            json_data=data,
        )

    def get_subscription(self, calendar_id: str, subscription_id: str) -> Any:
        """Get one subscription. The secret is not included."""
        return self._request(
            "GET",
            f"/calendars/{calendar_id}/subscriptions/{subscription_id}",
        )

    def update_subscription(
        self,
        calendar_id: str,
        subscription_id: str,
        url: Optional[str] = None,
        secret: Optional[str] = None,
        event_types: Optional[list[str]] = None,
        occurrence_offset_seconds: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Any:
        """Update a subscription. A replacement secret is stored and not returned."""
        data = _omit_none(
            {
                "url": url,
                "secret": secret,
                "event_types": event_types,
                "occurrence_offset_seconds": occurrence_offset_seconds,
                "is_active": is_active,
            }
        )
        return self._request(
            "PATCH",
            f"/calendars/{calendar_id}/subscriptions/{subscription_id}",
            json_data=data,
        )

    def delete_subscription(self, calendar_id: str, subscription_id: str) -> Any:
        """Delete a subscription."""
        return self._request(
            "DELETE",
            f"/calendars/{calendar_id}/subscriptions/{subscription_id}",
        )

    def list_subscription_deliveries(
        self,
        calendar_id: str,
        subscription_id: str,
        limit: Optional[int] = None,
    ) -> Any:
        """Delivery log for one subscription, newest first."""
        params = _omit_none({"limit": limit})
        return self._request(
            "GET",
            f"/calendars/{calendar_id}/subscriptions/{subscription_id}/deliveries",
            params=params or None,
        )

    def replay_subscription_delivery(
        self,
        calendar_id: str,
        subscription_id: str,
        delivery_id: str,
    ) -> Any:
        """Queue a new delivery with the same payload. The original row is unchanged."""
        return self._request(
            "POST",
            f"/calendars/{calendar_id}/subscriptions/{subscription_id}/deliveries/{delivery_id}/replay",
        )
