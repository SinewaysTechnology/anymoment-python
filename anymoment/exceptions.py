"""Custom exception classes for AnyMoment SDK."""

from typing import Any, Mapping, Optional


class AnyMomentException(Exception):
    """Base exception for all AnyMoment-related errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        user_message: Optional[str] = None,
        next_step: Optional[str] = None,
        retry_after: Optional[int] = None,
        details: Optional[dict] = None,
        raw: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.user_message = message if user_message is None else user_message
        self.next_step = next_step
        self.retry_after = retry_after
        self.details = details or {}
        self.raw = self.details if raw is None else raw


class AuthenticationError(AnyMomentException):
    """Raised when authentication fails (401)."""

    def __init__(
        self,
        message: str = "Authentication failed",
        status_code: Optional[int] = 401,
        **kwargs: Any,
    ):
        if isinstance(status_code, dict) and "details" not in kwargs:
            kwargs["details"] = status_code
            status_code = 401
        super().__init__(message, status_code=status_code, **kwargs)


class EmailNotVerifiedError(AuthenticationError):
    """Raised when sign-in is rejected because the email is not verified."""

    def __init__(
        self,
        message: str = "Email address is not verified",
        status_code: Optional[int] = 401,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class PermissionDeniedError(AnyMomentException):
    """Raised when the caller is not allowed to perform the action (403)."""

    def __init__(
        self,
        message: str = "Permission denied",
        status_code: Optional[int] = 403,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class NotFoundError(AnyMomentException):
    """Raised when a resource is not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        status_code: Optional[int] = 404,
        **kwargs: Any,
    ):
        if isinstance(status_code, dict) and "details" not in kwargs:
            kwargs["details"] = status_code
            status_code = 404
        super().__init__(message, status_code=status_code, **kwargs)


class ConflictError(AnyMomentException):
    """Raised when the request conflicts with current state (409)."""

    def __init__(
        self,
        message: str = "Conflict",
        status_code: Optional[int] = 409,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class ValidationError(AnyMomentException):
    """Raised when request validation fails (400)."""

    def __init__(
        self,
        message: str = "Validation error",
        status_code: Optional[int] = 400,
        **kwargs: Any,
    ):
        if isinstance(status_code, dict) and "details" not in kwargs:
            kwargs["details"] = status_code
            status_code = 400
        super().__init__(message, status_code=status_code, **kwargs)


class UnprocessableError(AnyMomentException):
    """Raised when the server cannot process the entity (422)."""

    def __init__(
        self,
        message: str = "Unprocessable entity",
        status_code: Optional[int] = 422,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class RateLimitError(AnyMomentException):
    """Raised when the server rate-limits the caller (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        status_code: Optional[int] = 429,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class ServerError(AnyMomentException):
    """Raised when the server returns an error (500+), including 502."""

    def __init__(
        self,
        message: str = "Server error",
        status_code: int = 500,
        **kwargs: Any,
    ):
        super().__init__(message, status_code=status_code, **kwargs)


class TokenError(AnyMomentException):
    """Raised when token operations fail."""

    def __init__(self, message: str = "Token error", **kwargs: Any):
        super().__init__(message, **kwargs)


class ConfigError(AnyMomentException):
    """Raised when configuration operations fail."""

    def __init__(self, message: str = "Configuration error", **kwargs: Any):
        super().__init__(message, **kwargs)


class ParsedError:
    """Fields extracted from an error response body."""

    def __init__(
        self,
        message: str,
        code: Optional[str],
        user_message: Optional[str],
        next_step: Optional[str],
        retry_after: Optional[int],
        details: dict,
        raw: Any,
        plain: bool,
    ):
        self.message = message
        self.code = code
        self.user_message = user_message
        self.next_step = next_step
        self.retry_after = retry_after
        self.details = details
        self.raw = raw
        self.plain = plain


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _message_from_detail_list(detail: list) -> str:
    parts = []
    for item in detail:
        if isinstance(item, dict):
            msg = item.get("msg") or item.get("message")
            loc = item.get("loc")
            if loc and msg:
                if isinstance(loc, (list, tuple)):
                    loc_text = ".".join(str(part) for part in loc)
                else:
                    loc_text = str(loc)
                parts.append(f"{loc_text}: {msg}")
            elif msg:
                parts.append(str(msg))
        else:
            parts.append(str(item))
    return "; ".join(parts) if parts else "Validation error"


def parse_error_payload(
    payload: Any,
    text: str = "",
    status_code: int = 0,
    headers: Optional[Mapping[str, str]] = None,
) -> ParsedError:
    """Read detail, top-level user_message/next_step, or a CalDAV detail object."""
    code = None
    user_message = None
    next_step = None
    retry_after = None
    details: dict = {}
    raw: Any = text
    plain = False

    if isinstance(payload, dict):
        raw = payload
        details = payload
        detail = payload.get("detail")
        if isinstance(detail, str):
            user_message = _as_str(detail)
        elif isinstance(detail, dict):
            code = _as_str(detail.get("code"))
            user_message = _as_str(detail.get("user_message")) or _as_str(detail.get("message"))
            next_step = _as_str(detail.get("next_step"))
            retry_after = _as_int(detail.get("retry_after_seconds"))
            if retry_after is None:
                retry_after = _as_int(detail.get("retry_after"))
        elif isinstance(detail, list):
            user_message = _message_from_detail_list(detail)
        if _as_str(payload.get("user_message")):
            user_message = _as_str(payload.get("user_message"))
        if _as_str(payload.get("next_step")):
            next_step = _as_str(payload.get("next_step"))
        if _as_str(payload.get("code")):
            code = _as_str(payload.get("code"))
        top_retry = _as_int(payload.get("retry_after_seconds"))
        if top_retry is None:
            top_retry = _as_int(payload.get("retry_after"))
        if top_retry is not None:
            retry_after = top_retry
    elif isinstance(payload, str):
        plain = True
        user_message = _as_str(payload)
        raw = payload
    else:
        plain = True
        user_message = _as_str(text) or f"HTTP {status_code}"
        raw = text

    if retry_after is None and headers is not None:
        retry_after = _as_int(headers.get("Retry-After"))

    message = user_message or f"HTTP {status_code}"
    return ParsedError(
        message=message,
        code=code,
        user_message=user_message or message,
        next_step=next_step,
        retry_after=retry_after,
        details=details,
        raw=raw,
        plain=plain,
    )


def exception_for_status(status_code: int, parsed: ParsedError) -> AnyMomentException:
    """Map an HTTP status and a parsed body onto a typed error."""
    kwargs = {
        "code": parsed.code,
        "user_message": parsed.user_message,
        "next_step": parsed.next_step,
        "retry_after": parsed.retry_after,
        "details": parsed.details,
        "raw": parsed.raw,
    }
    message = parsed.message
    if (
        status_code == 401
        and parsed.plain
        and parsed.user_message
        and "verify" in parsed.user_message.lower()
    ):
        return EmailNotVerifiedError(message, **kwargs)
    if status_code == 401:
        return AuthenticationError(message, **kwargs)
    if status_code == 403:
        return PermissionDeniedError(message, **kwargs)
    if status_code == 404:
        return NotFoundError(message, **kwargs)
    if status_code == 409:
        return ConflictError(message, **kwargs)
    if status_code == 422:
        return UnprocessableError(message, **kwargs)
    if status_code == 400:
        return ValidationError(message, **kwargs)
    if status_code == 429:
        return RateLimitError(message, **kwargs)
    if status_code >= 500:
        return ServerError(message, status_code=status_code, **kwargs)
    return AnyMomentException(message, status_code=status_code, **kwargs)
