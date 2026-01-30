"""Custom exception classes for AnyMoment SDK."""

from typing import Optional


class AnyMomentException(Exception):
    """Base exception for all AnyMoment-related errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(AnyMomentException):
    """Raised when authentication fails (401)."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[dict] = None):
        super().__init__(message, status_code=401, details=details)


class NotFoundError(AnyMomentException):
    """Raised when a resource is not found (404)."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None):
        super().__init__(message, status_code=404, details=details)


class ValidationError(AnyMomentException):
    """Raised when request validation fails (400)."""
    
    def __init__(self, message: str = "Validation error", details: Optional[dict] = None):
        super().__init__(message, status_code=400, details=details)


class ServerError(AnyMomentException):
    """Raised when server returns an error (500+)."""
    
    def __init__(self, message: str = "Server error", status_code: int = 500, details: Optional[dict] = None):
        super().__init__(message, status_code=status_code, details=details)


class TokenError(AnyMomentException):
    """Raised when token operations fail."""
    
    def __init__(self, message: str = "Token error", details: Optional[dict] = None):
        super().__init__(message, details=details)


class ConfigError(AnyMomentException):
    """Raised when configuration operations fail."""
    
    def __init__(self, message: str = "Configuration error", details: Optional[dict] = None):
        super().__init__(message, details=details)
