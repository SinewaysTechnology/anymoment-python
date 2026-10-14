"""AnyMoment Python SDK - API client and CLI for AnyMoment calendar service."""

from anymoment.client import Client
from anymoment.exceptions import (
    AnyMomentException,
    ApiKeyExpiredError,
    ApiKeyNotPermittedError,
    ApiKeyRevokedError,
    AuthenticationError,
    CalendarNotAllowedError,
    ConflictError,
    EmailNotVerifiedError,
    InvalidApiKeyError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableError,
    ValidationError,
)
from anymoment.signatures import verify_signature, verify_webhook, webhook_signature

__version__ = "2.1.0"
__all__ = [
    "Client",
    "AnyMomentException",
    "ApiKeyExpiredError",
    "ApiKeyNotPermittedError",
    "ApiKeyRevokedError",
    "AuthenticationError",
    "CalendarNotAllowedError",
    "ConflictError",
    "EmailNotVerifiedError",
    "InvalidApiKeyError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "UnprocessableError",
    "ValidationError",
    "verify_signature",
    "verify_webhook",
    "webhook_signature",
]
