"""
Permission classes for API controllers.

Includes both standard permissions (IsAuthenticated, IsStaff) and
role-based permissions for Stud'Insight's 6 roles.
"""

from typing import Any

from django.http import HttpRequest
from ninja_extra import permissions

from backend_django.core.roles import Role
from backend_django.core.roles import user_has_any_role
from backend_django.core.roles import user_has_role


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


# =============================================================================
# Role-based permission classes for Stud'Insight
# =============================================================================


class IsEtudiant(permissions.BasePermission):
    """Permission class that requires Étudiant role."""

    message = "Accès réservé aux étudiants."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Étudiant role."""
        return user_has_role(request.user, Role.ETUDIANT)


class IsRespoTER(permissions.BasePermission):
    """Permission class that requires Respo TER role."""

    message = "Accès réservé aux responsables TER."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Respo TER role."""
        return user_has_role(request.user, Role.RESPO_TER)


class IsRespoStage(permissions.BasePermission):
    """Permission class that requires Respo Stage role."""

    message = "Accès réservé aux responsables Stage."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Respo Stage role."""
        return user_has_role(request.user, Role.RESPO_STAGE)


class IsEncadrant(permissions.BasePermission):
    """Permission class that requires Encadrant role."""

    message = "Accès réservé aux encadrants."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Encadrant role."""
        return user_has_role(request.user, Role.ENCADRANT)


class IsExterne(permissions.BasePermission):
    """Permission class that requires Externe role."""

    message = "Accès réservé aux superviseurs externes."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Externe role."""
        return user_has_role(request.user, Role.EXTERNE)


class IsAdmin(permissions.BasePermission):
    """Permission class that requires Admin role (via group, not is_superuser)."""

    message = "Accès réservé aux administrateurs."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has Admin role or is superuser."""
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or user_has_role(request.user, Role.ADMIN)


class IsRespo(permissions.BasePermission):
    """Permission class that requires either Respo TER or Respo Stage role."""

    message = "Accès réservé aux responsables (TER ou Stage)."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has either Respo role."""
        return user_has_any_role(request.user, [Role.RESPO_TER, Role.RESPO_STAGE])


class IsAcademic(permissions.BasePermission):
    """
    Permission for academic staff (Encadrant, Respo TER, Respo Stage).

    Useful for endpoints accessible to any internal academic user.
    """

    message = "Accès réservé au personnel académique."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user has an academic role."""
        return user_has_any_role(
            request.user, [Role.ENCADRANT, Role.RESPO_TER, Role.RESPO_STAGE]
        )


class IsStaffOrRespo(permissions.BasePermission):
    """
    Permission for staff or responsables.

    Useful for admin-like endpoints that Respo should also access.
    """

    message = "Accès réservé au personnel ou responsables."

    def has_permission(self, request: HttpRequest, controller: Any) -> bool:
        """Check if user is staff or has a Respo role."""
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return user_has_any_role(request.user, [Role.RESPO_TER, Role.RESPO_STAGE])
