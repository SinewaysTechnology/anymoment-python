"""AnyMoment Python SDK - API client and CLI for AnyMoment calendar service."""

from anymoment.client import Client
from anymoment.exceptions import (
    AnyMomentException,
    AuthenticationError,
    ConflictError,
    EmailNotVerifiedError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnprocessableError,
    ValidationError,
)

__version__ = "2.0.1"
__all__ = [
    "Client",
    "AnyMomentException",
    "AuthenticationError",
    "ConflictError",
    "EmailNotVerifiedError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "UnprocessableError",
    "ValidationError",
]
