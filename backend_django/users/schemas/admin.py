"""
Admin user management schemas.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from ninja import Schema

if TYPE_CHECKING:
    from backend_django.users.models import User


class UserCreateSchema(Schema):
    """Schema for admin creating a user."""

    email: str
    first_name: str
    last_name: str = ""
    company_name: str = ""  # For Externe users
    groups: list[str] = []  # Group names (roles)


class UserUpdateSchema(Schema):
    """Schema for updating a user."""

    first_name: str | None = None
    last_name: str | None = None
    is_active: bool | None = None
    company_name: str | None = None  # For Externe users
    groups: list[str] | None = None  # Group names (roles)


class SetUserRoleSchema(Schema):
    """Schema for setting a user's role(s)."""

    roles: list[str]  # Role names to assign


class RoleSchema(Schema):
    """Schema for role information."""

    name: str
    description: str


class RoleListSchema(Schema):
    """Schema for listing available roles."""

    roles: list[RoleSchema]


class GroupDetailSchema(Schema):
    """Group detail with permissions."""

    name: str
    permissions: list[str]


class UserListSchema(Schema):
    """Schema for user list response."""

    id: UUID
    email: str
    first_name: str
    last_name: str
    company_name: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    groups: list[GroupDetailSchema]
    date_joined: datetime
    last_login: datetime | None

    @staticmethod
    def from_user(user: "User") -> "UserListSchema":
        """Create schema from User model."""
        groups_with_perms = []
        for group in user.groups.prefetch_related("permissions").all():
            groups_with_perms.append(
                GroupDetailSchema(
                    name=group.name,
                    permissions=[p.codename for p in group.permissions.all()],
                )
            )
        return UserListSchema(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            company_name=user.company_name,
            is_active=user.is_active,
            is_staff=user.is_staff,
            is_superuser=user.is_superuser,
            groups=groups_with_perms,
            date_joined=user.date_joined,
            last_login=user.last_login,
        )


class UserDetailSchema(UserListSchema):
    """Detailed user schema."""

    pass


class CSVImportErrorSchema(Schema):
    """Schema for a single CSV import error."""

    line: int
    email: str | None = None
    error: str


class CSVImportResultSchema(Schema):
    """Schema for CSV import result."""

    success: bool
    created_count: int
    skipped_count: int
    error_count: int
    errors: list[CSVImportErrorSchema]
    created_users: list[UserListSchema]
