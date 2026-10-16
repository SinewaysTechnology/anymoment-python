"""API client for AnyMoment SDK."""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import requests

from anymoment.config import get_api_url
from anymoment.exceptions import (
    AnyMomentException,
    ApiKeyExpiredError,
    AuthenticationError,
    CALENDAR_LIMITED_EVENTS_NEXT_STEP,
    PermissionDeniedError,
    ServerError,
    ValidationError,
    exception_for_status,
    parse_error_payload,
)

_API_KEY_FAILURES = {"invalid_api_key", "api_key_revoked", "api_key_expired", "auth_failed"}
from anymoment.caldav import CalDavClient
from anymoment.endpoints import EndpointsMixin
from anymoment.google import GoogleAPI
from anymoment.models import AgendaResult, agenda_result, mutation_result
from anymoment.schedule import ScheduleError, build_scheduled_event, record_to_kwargs
from anymoment.token_manager import get_token, save_token, token_expiry_state


class Client(EndpointsMixin):
    """Client for interacting with the AnyMoment API."""
    
    DEFAULT_API_URL = "https://api.anymoment.sineways.tech"
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        token: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the API client.

        An API key is sent as ``Authorization: Bearer``. When ``api_key`` or
        ``ANYMOMENT_API_KEY`` is set, it is used instead of a saved login.

        Args:
            api_url: API base URL. Defaults to config/env or https://api.anymoment.sineways.tech
            token: Optional JWT token. If not provided, will try to load from token manager.
            api_key: Optional API key (``am_live_<8 hex>_<secret>``). Falls back to ANYMOMENT_API_KEY.
        """
        self.api_url = api_url or get_api_url() or self.DEFAULT_API_URL
        self.api_url = self.api_url.rstrip("/")
        self._token = token
        self._api_key = _clean_secret(api_key)
        if self._api_key is None:
            self._api_key = _clean_secret(os.getenv("ANYMOMENT_API_KEY"))
        self._session = requests.Session()

    @property
    def api_key(self) -> Optional[str]:
        """The API key in use, or None when the client is using a session token."""
        return self._api_key

    @property
    def google(self) -> GoogleAPI:
        """Google account, sync health, quarantine, and sync status calls."""
        return GoogleAPI(self)

    @property
    def caldav(self) -> CalDavClient:
        """Experimental CalDAV API. Remote auth failures do not refresh the session token."""
        return CalDavClient(self)
    
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
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
            return headers
        token = self._get_token()
        if token:
            headers["x-auth-token"] = token
        return headers
    
    def _read_payload(self, response: requests.Response) -> Any:
        """Return parsed JSON, or None when the body is not JSON."""
        try:
            return response.json()
        except ValueError:
            return None

    def _parsed_error(self, response: requests.Response):
        return parse_error_payload(
            self._read_payload(response),
            response.text or "",
            response.status_code,
            response.headers,
        )

    def _should_refresh(self, path: str, response: requests.Response) -> bool:
        """Refresh only a real AnyMoment session 401.

        CalDAV auth_failed, any /caldav 401, and token login/extend 401s
        are credential failures. Refreshing the session token cannot fix them.
        """
        if self._api_key:
            return False
        normalized = path.split("?", 1)[0]
        if normalized.startswith("/caldav") or normalized.startswith("/auth/token"):
            return False
        parsed = self._parsed_error(response)
        if parsed.code in _API_KEY_FAILURES:
            return False
        return True

    def _handle_response(self, response: requests.Response) -> Any:
        """Handle API response and raise appropriate exceptions."""
        if 200 <= response.status_code < 300:
            try:
                return response.json()
            except ValueError:
                return response.text

        raise exception_for_status(response.status_code, self._parsed_error(response))
    
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
            
            if (
                response.status_code == 401
                and retry_on_auth_error
                and self._should_refresh(path, response)
            ):
                try:
                    self.refresh_token()
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
                    pass

            return self._handle_response(response)
        except AnyMomentException:
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
        
        if response.status_code != 200:
            self._handle_response(response)
            return ""
        token = response.text.strip().strip('"')
        if not token:
            raise AuthenticationError(
                "Login did not return a token.",
                user_message="Login failed. The server did not return a token.",
                next_step="Check the email and password, then try again.",
            )
        return self.adopt_token(token)

    def adopt_token(self, token: str) -> str:
        """Check a token with the server, then save it. A rejected token is not saved."""
        self._token = token
        status = self.check_credentials()
        if status != "valid":
            self._token = None
            if status == "expired":
                message = "Login failed. The token is expired."
                step = "Sign in again with `am auth login`."
            elif status == "unknown":
                message = "Login failed. The token could not be verified."
                step = "Check the network and the API host, then try again."
            else:
                message = "Login failed. The server rejected the token."
                step = "Check the email and password, or set a current ANYMOMENT_TOKEN."
            raise AuthenticationError(message, user_message=message, next_step=step)
        save_token(self.api_url, token)
        return token

    def check_credentials(self) -> str:
        """Ask the server whether the current credential works.

        Returns ``valid``, ``expired``, ``invalid``, or ``unknown``.
        Does not refresh or save a token.
        """
        path = "/calendars" if self._api_key else "/auth/me"
        params = {"limit": 1} if self._api_key else None
        try:
            self._request("GET", path, params=params, retry_on_auth_error=False)
        except ApiKeyExpiredError:
            return "expired"
        except AuthenticationError as exc:
            text = f"{exc.code or ''} {exc.user_message or ''}".lower()
            if "expir" in text:
                return "expired"
            if self._token and not self._api_key and token_expiry_state(self._token) == "expired":
                return "expired"
            return "invalid"
        except PermissionDeniedError:
            return "valid"
        except AnyMomentException:
            return "unknown"
        return "valid"
    
    def refresh_token(self) -> str:
        """
        Refresh the current authentication token.
        
        Returns:
            New JWT token string
        """
        if self._api_key:
            raise AuthenticationError(
                "API keys cannot be refreshed.",
                user_message="API keys cannot be refreshed.",
                next_step=(
                    "Create a new key in AnyMoment settings if this one was revoked or expired."
                ),
            )
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
    ) -> AgendaResult:
        """
        Get events and their instances within a time window (agenda).

        Args:
            start: Start of window (ISO 8601 string or datetime; naive datetime = UTC).
            end: End of window (ISO 8601 string or datetime; naive datetime = UTC).
            calendar_ids: Optional list of calendar UUIDs to restrict to.
            use_cache: Use instance cache when available (default True).
            include_webhooks: Include webhooks in each event payload (default False).

        Returns:
            AgendaResult with .events and .failures. A legacy list body is
            exposed as events with an empty failures list.
        """
        params = {
            "start": self._datetime_to_iso(start),
            "end": self._datetime_to_iso(end),
            "use_cache": use_cache,
            "include_webhooks": include_webhooks,
        }
        if calendar_ids is not None:
            params["calendar_ids"] = calendar_ids
        return agenda_result(self._request("GET", "/agenda", params=params))

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

    def update_calendar_share_role(
        self,
        calendar_id: str,
        user_id: str,
        role: str,
    ) -> Dict[str, Any]:
        """Update a shared user's role for a calendar (owner, editor, viewer)."""
        data = {"role": role}
        return self._request("PUT", f"/calendars/{calendar_id}/share/{user_id}", json_data=data)

    def unshare_calendar(self, calendar_id: str, user_id: str) -> Dict[str, Any]:
        """Remove an AnyMoment share for a calendar (user loses access unless linked via Google)."""
        return self._request("DELETE", f"/calendars/{calendar_id}/share/{user_id}")

    def get_calendar_webhook_url(self, calendar_id: str) -> dict[str, Any]:
        """Get webhook URL for a calendar."""
        return self._request("GET", f"/calendars/{calendar_id}/webhook-url")
    
    # Event methods
    
    def list_calendar_events(
        self,
        calendar_id: str,
        is_active: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List events on one calendar.

        ``GET /calendars/{calendar_id}/events``. Each item is ``{"event", "link"}``.
        ``is_active`` filters that page. The route has no minimal flag.
        """
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        events = self._request("GET", f"/calendars/{calendar_id}/events", params=params or None)
        if is_active is None or not isinstance(events, list):
            return events
        return [item for item in events if _event_is_active(item) is is_active]

    def list_events(
        self,
        calendar_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        minimal: bool = False,
    ) -> List[Dict[str, Any]]:
        """List events for the authenticated user.

        A session token uses ``GET /events``. An API key with ``calendar_id``
        uses ``GET /calendars/{calendar_id}/events``, which is required for a
        calendar-limited key. ``GET /events`` is not available to those keys.
        """
        if self._api_key and calendar_id:
            if minimal:
                raise ValidationError(
                    "minimal is only supported on GET /events.",
                    user_message="This key lists events on one calendar at a time.",
                    next_step=(
                        "Omit minimal and pass calendar_id. "
                        "The client calls GET /calendars/{calendar_id}/events."
                    ),
                )
            return self.list_calendar_events(
                calendar_id,
                is_active=is_active,
                limit=limit,
                offset=offset,
            )
        params: Dict[str, Any] = {}
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
        try:
            return self._request("GET", "/events", params=params or None)
        except PermissionDeniedError as exc:
            if self._api_key and not calendar_id and exc.code != "api_key_not_permitted":
                exc.next_step = CALENDAR_LIMITED_EVENTS_NEXT_STEP
            raise
    
    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get a specific event by ID."""
        return self._request("GET", f"/events/{event_id}")
    
    def extract_and_create_events(
        self,
        text: str,
        context: Optional[str] = None,
        timezone: str = "UTC",
        model: str = "high",
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract events from free-form text and create them (POST /events/extract)."""
        data: Dict[str, Any] = {
            "text": text,
            "timezone": timezone,
            "model": model,
        }
        if context is not None:
            data["context"] = context
        if calendar_id is not None:
            data["calendar_id"] = calendar_id
        return self._request("POST", "/events/extract", json_data=data)
    
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
        return self._request("POST", "/events/from-recurrence-text", json_data=data)

    def create_scheduled_event(
        self,
        title: str,
        start: str,
        end: Optional[str] = None,
        all_day: bool = False,
        rrule: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        timezone: str = "UTC",
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create one event from exact fields via POST /events, then link a calendar.

        This does not call the natural-language extractor. ``location`` is stored
        in the description because the create body has no location field.
        """
        body = build_scheduled_event(
            title=title,
            start=start,
            end=end,
            all_day=all_day,
            rrule=rrule,
            description=description,
            location=location,
            timezone=timezone,
        )
        created = self.create_event(
            body["name"],
            body["components"],
            description=body.get("description"),
        )
        event = created.as_dict() if hasattr(created, "as_dict") else dict(created)
        result: Dict[str, Any] = {"event": event, "link": None, "warnings": []}
        warnings = getattr(created, "sync_warnings", None) or []
        if isinstance(warnings, list):
            result["warnings"].extend(warnings)
        if not calendar_id:
            return result
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ScheduleError("The server created an event without an id.")
        try:
            linked = self.link_event_to_calendar(calendar_id, event_id)
        except AnyMomentException as exc:
            note = f"The event was created ({event_id}) but it is not on the calendar."
            if exc.next_step:
                exc.next_step = f"{note} {exc.next_step}"
            else:
                exc.next_step = note + " Link it with `am calendars add-event`."
            raise
        link_body = linked.as_dict() if hasattr(linked, "as_dict") else linked
        if isinstance(link_body, dict):
            result["link"] = link_body.get("link", link_body)
            extra = link_body.get("google_export_warnings") or []
            if isinstance(extra, list):
                result["warnings"].extend(extra)
        return result

    def create_scheduled_events(
        self,
        records: List[Any],
        default_timezone: str = "UTC",
        default_calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create many exact-field events. Local problems are rejected before any request."""
        prepared = []
        for index, record in enumerate(records):
            try:
                prepared.append(
                    (index, record_to_kwargs(record, default_timezone, default_calendar_id))
                )
            except ScheduleError as exc:
                raise ScheduleError(f"Event {index + 1}: {exc.user_message}") from exc
        results = []
        for index, fields in prepared:
            try:
                created = self.create_scheduled_event(**fields)
            except AuthenticationError:
                raise
            except AnyMomentException as exc:
                results.append(
                    {
                        "ok": False,
                        "index": index,
                        "title": fields.get("title"),
                        "error": {
                            "code": exc.code,
                            "status": exc.status_code,
                            "user_message": exc.user_message,
                            "next_step": exc.next_step,
                        },
                    }
                )
                continue
            results.append({"ok": True, "index": index, **created})
        return {"results": results}
    
    def update_event(
        self,
        event_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an event (name/description only)."""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        return mutation_result(self._request("PUT", f"/events/{event_id}", json_data=data))
    
    def update_event_from_text(
        self,
        event_id: str,
        recurrence_text: str,
        name: str,
        description: Optional[str] = None,
        timezone: str = "UTC",
        model: str = "high",
    ) -> Dict[str, Any]:
        """Update an event from natural language recurrence (PUT /events/{id}/from-recurrence-text)."""
        data: Dict[str, Any] = {
            "recurrence_text": recurrence_text,
            "name": name,
            "timezone": timezone,
            "model": model,
        }
        if description is not None:
            data["description"] = description
        return mutation_result(
            self._request(
                "PUT", f"/events/{event_id}/from-recurrence-text", json_data=data
            )
        )
    
    def delete_event(self, event_id: str) -> Any:
        """Delete an event. Returns message and sync_warnings when the API sends them."""
        return mutation_result(self._request("DELETE", f"/events/{event_id}"))
    
    def toggle_event(self, event_id: str) -> Any:
        """Toggle event active status."""
        return mutation_result(self._request("PATCH", f"/events/{event_id}/toggle"))
    
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

    def batch_add_events_to_calendar(
        self,
        calendar_id: str,
        event_ids: List[str],
        display_order: Optional[int] = None,
        color_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add multiple events to a calendar in one request.

        Returns ``{results, warnings}``. Each result is one event: ``ok``,
        ``event_id``, ``link``, ``warnings``, and ``error``.
        """
        data: Dict[str, Any] = {"event_ids": event_ids}
        if display_order is not None:
            data["display_order"] = display_order
        if color_override is not None:
            data["color_override"] = color_override
        payload = self._request("POST", f"/calendars/{calendar_id}/events", json_data=data)
        return normalize_batch_add(payload)

    def batch_remove_events_from_calendar(
        self,
        calendar_id: str,
        event_ids: List[str],
    ) -> Dict[str, Any]:
        """Remove multiple events from a calendar (unlink only; events are not deleted)."""
        return mutation_result(
            self._request(
                "POST",
                f"/calendars/{calendar_id}/events/batch-unlink",
                json_data={"event_ids": event_ids},
            )
        )

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
        return mutation_result(
            self._request(
                "POST",
                f"/calendars/{calendar_id}/events/{event_id}",
                json_data=data,
            )
        )

    def unlink_event_from_calendar(
        self,
        calendar_id: str,
        event_id: str,
    ) -> Any:
        """Unlink an event from a calendar. Returns sync_warnings when the API sends them."""
        return mutation_result(
            self._request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")
        )


def _clean_secret(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    return text or None


def api_key_prefix(api_key: str) -> Optional[str]:
    """Public prefix ``am_live_<8 hex>``. The secret after the underscore is dropped."""
    text = api_key.strip()
    parts = text.split("_", 3)
    if len(parts) != 4:
        return None
    kind, mode, prefix, secret = parts
    if kind != "am" or mode != "live" or len(prefix) != 8 or not secret:
        return None
    if any(char not in "0123456789abcdefABCDEF" for char in prefix):
        return None
    return f"am_live_{prefix}"


def _warning_list(row: Any) -> List[Any]:
    if not isinstance(row, dict):
        return []
    for key in ("google_export_warnings", "sync_warnings", "warnings"):
        value = row.get(key)
        if isinstance(value, list):
            return value
    return []


def _one_batch_link(row: Any) -> Dict[str, Any]:
    """One batch-add item, whether the API sent a link or a link plus warnings."""
    error = None
    ok = True
    link: Any = None
    warnings: List[Any] = []
    if isinstance(row, dict) and isinstance(row.get("link"), dict):
        link = row["link"]
        warnings = _warning_list(row)
        error = row.get("error")
        ok = row.get("ok", error is None)
    elif isinstance(row, dict) and (row.get("error") or row.get("ok") is False):
        link = row.get("link")
        warnings = _warning_list(row)
        error = row.get("error") or row.get("user_message")
        ok = False
    elif isinstance(row, dict):
        link = row
    else:
        ok = False
        error = "Unexpected item in the batch-add response."
    event_id = link.get("event_id") if isinstance(link, dict) else None
    if event_id is None and isinstance(row, dict):
        event_id = row.get("event_id")
    return {
        "ok": bool(ok) and error is None,
        "event_id": event_id,
        "link": link,
        "warnings": warnings,
        "error": error,
    }


def normalize_batch_add(payload: Any) -> Dict[str, Any]:
    """Per-item links and warnings from POST /calendars/{id}/events.

    A bare link list and a list of ``{link, google_export_warnings}`` both work.
    A non-document body becomes a server error instead of a traceback.
    """
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        rows = payload["results"]
    elif isinstance(payload, dict) and isinstance(payload.get("links"), list):
        rows = payload["links"]
    elif isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ServerError(
            "The server returned an unexpected batch-add response.",
            user_message="The server returned an unexpected batch-add response.",
            next_step=(
                "Retry `am calendars batch-add-events`. "
                "If it keeps failing, the calendar service still needs a fix."
            ),
        )
    results = [_one_batch_link(row) for row in rows]
    warnings: List[Any] = []
    for item in results:
        warnings.extend(item["warnings"])
    return {"results": results, "warnings": warnings}


def _event_is_active(item: Any) -> Optional[bool]:
    if not isinstance(item, dict):
        return None
    event = item.get("event")
    if isinstance(event, dict) and "is_active" in event:
        value = event.get("is_active")
    else:
        value = item.get("is_active")
    if isinstance(value, bool):
        return value
    return None
