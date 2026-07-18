"""
Purpose of this file.
Custom application exceptions.
Responsibility of this file.
Defining standard exceptions for domain-specific errors.
"""

class TokenExpiredError(Exception):
    """Raised when an access token is expired and cannot be refreshed."""

class TokenRefreshError(Exception):
    """Raised when refreshing a token fails."""

class GraphApiError(Exception):
    """Raised when Microsoft Graph API returns an error."""

class TenantNotFoundError(Exception):
    """Raised when an organization is not found or inactive."""

class EmailSendError(Exception):
    """Raised when sending an email fails."""
