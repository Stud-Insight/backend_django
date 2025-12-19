"""
Authentication schemas for login, signup, password reset, etc.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from ninja import Schema
from pydantic import EmailStr
from pydantic import field_validator

if TYPE_CHECKING:
    from backend_django.users.models import User


class LoginSchema(Schema):
    """Login request schema."""

    email: EmailStr
    password: str


class SignupSchema(Schema):
    """Signup request schema."""

    email: EmailStr
    first_name: str
    last_name: str = ""
    password: str
    password_confirm: str

    @field_validator("first_name")
    @classmethod
    def first_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            msg = "Le prénom est requis."
            raise ValueError(msg)
        return v.strip()

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            msg = "Les mots de passe ne correspondent pas."
            raise ValueError(msg)
        return v


class EmailVerifySchema(Schema):
    """Email verification schema."""

    key: str


class PasswordResetRequestSchema(Schema):
    """Password reset request schema."""

    email: EmailStr


class PasswordResetConfirmSchema(Schema):
    """Password reset confirmation schema."""

    uid: str
    token: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            msg = "Les mots de passe ne correspondent pas."
            raise ValueError(msg)
        return v


class ResendActivationSchema(Schema):
    """Resend activation email schema."""

    email: EmailStr


class GroupSchema(Schema):
    """Group with permissions schema."""

    name: str
    permissions: list[str]


class UserSchema(Schema):
    """User response schema - matches frontend interface."""

    id: UUID
    first_name: str
    last_name: str
    email: str
    groups: list[GroupSchema]
    is_staff: bool
    is_superuser: bool

    @staticmethod
    def from_user(user: "User") -> "UserSchema":
        """Create schema from User model."""
        groups_with_perms = []
        for group in user.groups.prefetch_related("permissions").all():
            groups_with_perms.append(
                GroupSchema(
                    name=group.name,
                    permissions=[p.codename for p in group.permissions.all()],
                )
            )
        return UserSchema(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            groups=groups_with_perms,
            is_staff=user.is_staff,
            is_superuser=user.is_superuser,
        )


class LoginResponseSchema(Schema):
    """Login response schema."""

    success: bool
    user: UserSchema | None = None
    csrf_token: str | None = None


class SignupResponseSchema(Schema):
    """Signup response schema."""

    success: bool
    message: str
    requires_email_verification: bool = True


class MessageSchema(Schema):
    """Simple message response."""

    success: bool
    message: str | None = None


class CSRFTokenSchema(Schema):
    """CSRF token response."""

    csrf_token: str


class PasswordChangeSchema(Schema):
    """Password change schema for authenticated users."""

    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            msg = "Les mots de passe ne correspondent pas."
            raise ValueError(msg)
        return v


class ActivateCheckSchema(Schema):
    """Response for activation token check."""

    valid: bool
    email: str | None = None


class ActivateWithPasswordSchema(Schema):
    """Schema for activating account with password."""

    password: str
    password_confirm: str

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "password" in info.data and v != info.data["password"]:
            msg = "Les mots de passe ne correspondent pas."
            raise ValueError(msg)
        return v
