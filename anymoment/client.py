"""API client for AnyMoment SDK."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import requests

from anymoment.config import get_api_url
from anymoment.exceptions import (
    AnyMomentException,
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from anymoment.token_manager import get_token, save_token


class Client:
    """Client for interacting with the AnyMoment API."""
    
    DEFAULT_API_URL = "https://api.anymoment.sineways.tech"
    
    def __init__(self, api_url: Optional[str] = None, token: Optional[str] = None):
        """
        Initialize the API client.
        
        Args:
            api_url: API base URL. Defaults to config/env or https://api.anymoment.sineways.tech
            token: Optional JWT token. If not provided, will try to load from token manager.
        """
        self.api_url = api_url or get_api_url() or self.DEFAULT_API_URL
        self.api_url = self.api_url.rstrip("/")
        self._token = token
        self._session = requests.Session()
    
    def _get_token(self) -> Optional[str]:
        """Get authentication token."""
        if self._token:
            return self._token
        return get_token(self.api_url)
    
    def _set_token(self, token: str) -> None:
        """Set and save authentication token."""
        self._token = token
        save_token(self.api_url, token)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        token = self._get_token()
        if token:
            headers["x-auth-token"] = token
        return headers
    
    def _handle_response(self, response: requests.Response) -> Any:
        """Handle API response and raise appropriate exceptions."""
        if response.status_code == 200 or response.status_code == 201:
            # Try to parse JSON, return text if not JSON
            try:
                return response.json()
            except ValueError:
                return response.text
        
        # Handle errors
        error_detail = "Unknown error"
        try:
            error_data = response.json()
            if isinstance(error_data, dict):
                error_detail = error_data.get("detail", str(error_data))
            else:
                error_detail = str(error_data)
        except ValueError:
            error_detail = response.text or f"HTTP {response.status_code}"
        
        if response.status_code == 401:
            raise AuthenticationError(error_detail)
        elif response.status_code == 404:
            raise NotFoundError(error_detail)
        elif response.status_code == 400:
            raise ValidationError(error_detail)
        elif response.status_code >= 500:
            raise ServerError(error_detail, status_code=response.status_code)
        else:
            raise AnyMomentException(
                error_detail,
                status_code=response.status_code,
            )
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
        retry_on_auth_error: bool = True,
    ) -> Any:
        """Make an HTTP request to the API."""
        url = f"{self.api_url}{path}"
        headers = self._get_headers()
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30,
            )
            
            # Handle 401 with token refresh
            if response.status_code == 401 and retry_on_auth_error:
                # Try to refresh token
                try:
                    self.refresh_token()
                    # Retry once with new token
                    headers = self._get_headers()
                    response = self._session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                        timeout=30,
                    )
                except Exception:
                    # Refresh failed, raise auth error
                    pass
            
            return self._handle_response(response)
        except (AuthenticationError, NotFoundError, ValidationError, ServerError, AnyMomentException):
            raise
        except requests.exceptions.RequestException as e:
            raise AnyMomentException(f"Request failed: {e}")
    
    def login(self, email: str, password: str) -> str:
        """
        Authenticate and get a token.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            JWT token string
        """
        response = self._session.post(
            f"{self.api_url}/auth/token",
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        
        if response.status_code == 200:
            token = response.text.strip().strip('"')  # Token is returned as plain text
            self._set_token(token)
            return token
        else:
            self._handle_response(response)
            return ""  # Should not reach here
    
    def refresh_token(self) -> str:
        """
        Refresh the current authentication token.
        
        Returns:
            New JWT token string
        """
        token = self._get_token()
        if not token:
            raise AuthenticationError("No token available to refresh")
        
        response = self._session.get(
            f"{self.api_url}/auth/token/extend",
            headers={"x-auth-token": token},
            timeout=30,
        )
        
        if response.status_code == 200:
            new_token = response.text.strip().strip('"')
            self._set_token(new_token)
            return new_token
        else:
            self._handle_response(response)
            return ""  # Should not reach here
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get current user information."""
        return self._request("GET", "/auth/me")

    @staticmethod
    def _datetime_to_iso(value: Union[str, datetime]) -> str:
        """Serialize start/end for agenda/search: datetime (naive=UTC) or str to ISO."""
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        raise TypeError("start/end must be str (ISO 8601) or datetime")

    # Agenda methods

    def get_agenda(
        self,
        start: Union[str, datetime],
        end: Union[str, datetime],
        calendar_ids: Optional[List[str]] = None,
        use_cache: bool = True,
        include_webhooks: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get events and their instances within a time window (agenda).

        Args:
            start: Start of window (ISO 8601 string or datetime; naive datetime = UTC).
            end: End of window (ISO 8601 string or datetime; naive datetime = UTC).
            calendar_ids: Optional list of calendar UUIDs to restrict to.
            use_cache: Use instance cache when available (default True).
            include_webhooks: Include webhooks in each event payload (default False).

        Returns:
            List of dicts with keys 'event' and 'instances'.
        """
        params = {
            "start": self._datetime_to_iso(start),
            "end": self._datetime_to_iso(end),
            "use_cache": use_cache,
            "include_webhooks": include_webhooks,
        }
        if calendar_ids is not None:
            params["calendar_ids"] = calendar_ids
        return self._request("GET", "/agenda", params=params)

    def search_events(
        self,
        q: str,
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None,
        calendar_ids: Optional[List[str]] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        include_instances: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search over events (by name). Optional time window and filters.

        Args:
            q: Search query (min length 1).
            start: Only events with at least one instance on or after this time (ISO or datetime; naive = UTC).
            end: Only events with at least one instance on or before this time (ISO or datetime; naive = UTC).
            calendar_ids: Optional list of calendar UUIDs to restrict to.
            is_active: Filter by active status.
            limit: Max results (1-100, default 50).
            offset: Skip this many results (default 0).
            include_instances: If start/end provided, include instances in response (default True).

        Returns:
            List of dicts with keys 'event', optional 'score', optional 'instances'.
        """
        params = {"q": q.strip(), "limit": limit, "offset": offset, "include_instances": include_instances}
        if start is not None:
            params["start"] = self._datetime_to_iso(start)
        if end is not None:
            params["end"] = self._datetime_to_iso(end)
        if calendar_ids is not None:
            params["calendar_ids"] = calendar_ids
        if is_active is not None:
            params["is_active"] = is_active
        return self._request("GET", "/agenda/search", params=params)

    # Calendar methods
    
    def list_calendars(
        self,
        is_active: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List all calendars for the authenticated user."""
        params = {}
        if is_active is not None:
            params["is_active"] = is_active
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self._request("GET", "/calendars", params=params)
    
    def get_calendar(self, calendar_id: str) -> Dict[str, Any]:
        """Get a specific calendar by ID."""
        return self._request("GET", f"/calendars/{calendar_id}")
    
    def create_calendar(
        self,
        name: str,
        description: Optional[str] = None,
        timezone: str = "UTC",
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new calendar."""
        data = {
            "name": name,
            "timezone": timezone,
        }
        if description is not None:
            data["description"] = description
        if color is not None:
            data["color"] = color
        return self._request("POST", "/calendars", json_data=data)
    
    def update_calendar(
        self,
        calendar_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timezone: Optional[str] = None,
        color: Optional[str] = None,
        is_active: bool | None = None,
    ) -> Dict[str, Any]:
        """Update a calendar."""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if timezone is not None:
            data["timezone"] = timezone
        if color is not None:
            data["color"] = color
        if is_active is not None:
            data["is_active"] = is_active
        return self._request("PUT", f"/calendars/{calendar_id}", json_data=data)
    
    def delete_calendar(self, calendar_id: str) -> None:
        """Delete a calendar."""
        self._request("DELETE", f"/calendars/{calendar_id}")
    
    def share_calendar(
        self,
        calendar_id: str,
        user_id: str,
        role: str = "viewer",
    ) -> Dict[str, Any]:
        """Share a calendar with another user."""
        data = {
            "user_id": user_id,
            "role": role,
        }
        return self._request("POST", f"/calendars/{calendar_id}/share", json_data=data)
    
    def get_calendar_webhook_url(self, calendar_id: str) -> dict[str, Any]:
        """Get webhook URL for a calendar."""
        return self._request("GET", f"/calendars/{calendar_id}/webhook-url")
    
    # Event methods
    
    def list_events(
        self,
        calendar_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        minimal: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all events for the authenticated user."""
        params = {}
        if calendar_id is not None:
            params["calendar_id"] = calendar_id
        if is_active is not None:
            params["is_active"] = is_active
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if minimal:
            params["minimal"] = True
        return self._request("GET", "/events", params=params)
    
    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get a specific event by ID."""
        return self._request("GET", f"/events/{event_id}")
    
    def create_event_from_text(
        self,
        recurrence_text: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        timezone: str = "UTC",
        calendar_id: Optional[str] = None,
        model: str = "high",
    ) -> Dict[str, Any]:
        """Create an event from natural language text."""
        data = {
            "recurrence_text": recurrence_text,
            "timezone": timezone,
            "model": model,
        }
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if calendar_id is not None:
            data["calendar_id"] = calendar_id
        return self._request("POST", "/events/from-text", json_data=data)
    
    def update_event(
        self,
        event_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an event."""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        return self._request("PUT", f"/events/{event_id}", json_data=data)
    
    def delete_event(self, event_id: str) -> None:
        """Delete an event."""
        self._request("DELETE", f"/events/{event_id}")
    
    def toggle_event(self, event_id: str) -> dict[str, Any]:
        """Toggle event active status."""
        return self._request("PATCH", f"/events/{event_id}/toggle")
    
    def get_event_instances(
        self,
        event_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        optimized: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get event instances for a date range."""
        params = {}
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        if optimized:
            params["optimized"] = True
        return self._request("GET", f"/events/{event_id}/instances", params=params)
    
    def get_next_event_instance(self, event_id: str) -> Dict[str, Any]:
        """Get the next instance of an event."""
        return self._request("GET", f"/events/{event_id}/next-instance")
    
    # Calendar-Event Link methods
    
    def link_event_to_calendar(
        self,
        calendar_id: str,
        event_id: str,
        display_order: Optional[int] = None,
        color_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Link an event to a calendar."""
        data = {}
        if display_order is not None:
            data["display_order"] = display_order
        if color_override is not None:
            data["color_override"] = color_override
        return self._request(
            "POST",
            f"/calendars/{calendar_id}/events/{event_id}",
            json_data=data,
        )
    
    def unlink_event_from_calendar(
        self,
        calendar_id: str,
        event_id: str,
    ) -> None:
        """Unlink an event from a calendar."""
        self._request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")
