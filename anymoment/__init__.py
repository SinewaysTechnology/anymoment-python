"""AnyMoment Python SDK - API client and CLI for AnyMoment calendar service."""

import sys

if sys.version_info < (3, 10):
    from anymoment_entry import python_too_old_message

    raise ImportError(python_too_old_message())

from anymoment.client import Client
from anymoment.business import preview_occurrences
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
    SubscriptionRequiredError,
    UnprocessableError,
    ValidationError,
)
from anymoment.signatures import verify_signature, verify_webhook, webhook_signature
from anymoment.webhooks import (
    CHANGE_TYPES,
    OCCURRENCE_DUE,
    build_webhook_payload,
    canonical_webhook_body,
    parse_webhook_payload,
)

__version__ = "2.3.0"
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
    "SubscriptionRequiredError",
    "UnprocessableError",
    "ValidationError",
    "CHANGE_TYPES",
    "OCCURRENCE_DUE",
    "build_webhook_payload",
    "canonical_webhook_body",
    "parse_webhook_payload",
    "preview_occurrences",
    "verify_signature",
    "verify_webhook",
    "webhook_signature",
]
