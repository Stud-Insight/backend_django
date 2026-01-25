"""
User schemas for API requests and responses.
"""

from backend_django.users.schemas.admin import RoleListSchema
from backend_django.users.schemas.admin import RoleSchema
from backend_django.users.schemas.admin import SetUserRoleSchema
from backend_django.users.schemas.admin import UserCreateSchema
from backend_django.users.schemas.admin import UserDetailSchema
from backend_django.users.schemas.admin import UserListSchema
from backend_django.users.schemas.admin import UserUpdateSchema
from backend_django.users.schemas.auth import ActivateCheckSchema
from backend_django.users.schemas.auth import ActivateWithPasswordSchema
from backend_django.users.schemas.auth import CSRFTokenSchema
from backend_django.users.schemas.auth import EmailVerifySchema
from backend_django.users.schemas.auth import GroupSchema
from backend_django.users.schemas.auth import LoginResponseSchema
from backend_django.users.schemas.auth import LoginSchema
from backend_django.users.schemas.auth import MessageSchema
from backend_django.users.schemas.auth import PasswordChangeSchema
from backend_django.users.schemas.auth import PasswordResetConfirmSchema
from backend_django.users.schemas.auth import PasswordResetRequestSchema
from backend_django.users.schemas.auth import ResendActivationSchema
from backend_django.users.schemas.auth import SignupResponseSchema
from backend_django.users.schemas.auth import SignupSchema
from backend_django.users.schemas.auth import UserSchema

__all__ = [
    # Auth schemas
    "LoginSchema",
    "SignupSchema",
    "EmailVerifySchema",
    "PasswordResetRequestSchema",
    "PasswordResetConfirmSchema",
    "ResendActivationSchema",
    "GroupSchema",
    "UserSchema",
    "LoginResponseSchema",
    "SignupResponseSchema",
    "MessageSchema",
    "CSRFTokenSchema",
    "PasswordChangeSchema",
    "ActivateCheckSchema",
    "ActivateWithPasswordSchema",
    # Admin schemas
    "UserCreateSchema",
    "UserUpdateSchema",
    "UserListSchema",
    "UserDetailSchema",
    # Role schemas
    "RoleSchema",
    "RoleListSchema",
    "SetUserRoleSchema",
]
