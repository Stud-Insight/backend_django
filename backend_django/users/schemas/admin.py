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
    groups: list[str] = []  # Group names


class UserUpdateSchema(Schema):
    """Schema for updating a user."""

    first_name: str | None = None
    last_name: str | None = None
    is_active: bool | None = None
    groups: list[str] | None = None


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
