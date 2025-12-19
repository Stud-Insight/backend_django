"""
Permission classes for API controllers.
"""

from typing import Any

from django.http import HttpRequest
from ninja_extra import permissions


class IsAuthenticated(permissions.BasePermission):
    """
    Permission class that requires authentication.

    Checks if the user is authenticated before allowing access.
    """

    message = "Authentification requise."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if the user is authenticated."""
        return bool(request.user and request.user.is_authenticated)


class IsStaff(permissions.BasePermission):
    """
    Permission class that requires staff status.

    Checks if the user is authenticated and has staff privileges.
    """

    message = "Accès réservé au personnel."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if the user is staff."""
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )


class IsSuperuser(permissions.BasePermission):
    """
    Permission class that requires superuser status.

    Checks if the user is authenticated and is a superuser.
    """

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if the user is a superuser."""
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class AllowAny(permissions.BasePermission):
    """
    Permission class that allows any access.

    Used for public endpoints that don't require authentication.
    """

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Always return True."""
        return True
