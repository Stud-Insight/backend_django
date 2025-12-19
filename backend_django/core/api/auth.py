"""
Authentication classes for the API.
"""

from typing import Any

from django.http import HttpRequest
from ninja.security import SessionAuth as NinjaSessionAuth


class SessionAuth(NinjaSessionAuth):
    """
    Session-based authentication.

    Uses Django's session framework for authentication.
    Returns the authenticated user if the session is valid.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> Any | None:
        """
        Authenticate the request using session.

        Args:
            request: The HTTP request object
            key: The session key (not used, but required by interface)

        Returns:
            The authenticated user or None
        """
        if request.user.is_authenticated:
            return request.user
        return None


class OptionalSessionAuth(NinjaSessionAuth):
    """
    Optional session-based authentication.

    Same as SessionAuth but doesn't require authentication.
    Returns the user if authenticated, None otherwise.
    """

    def authenticate(self, request: HttpRequest, key: str | None) -> Any | None:
        """Authenticate the request, returning None if not authenticated."""
        if request.user.is_authenticated:
            return request.user
        return None
