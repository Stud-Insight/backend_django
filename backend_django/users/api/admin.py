"""
Admin API controller for user management.
"""

import logging
import secrets
import string
from uuid import UUID

from allauth.account.internal.flows.email_verification import send_verification_email_for_user
from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group
from django.http import HttpRequest
from ninja_extra import api_controller
from ninja_extra import http_delete
from ninja_extra import http_get
from ninja_extra import http_post
from ninja_extra import http_put

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsStaff
from backend_django.core.exceptions import AlreadyExistsError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotFoundError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.core.exceptions import ValidationError
from backend_django.core.roles import Role
from backend_django.core.roles import ROLE_DESCRIPTIONS
from backend_django.users.models import User
from backend_django.users.schemas import MessageSchema
from backend_django.users.schemas import RoleListSchema
from backend_django.users.schemas import RoleSchema
from backend_django.users.schemas import SetUserRoleSchema
from backend_django.users.schemas import UserCreateSchema
from backend_django.users.schemas import UserDetailSchema
from backend_django.users.schemas import UserListSchema
from backend_django.users.schemas import UserUpdateSchema

logger = logging.getLogger(__name__)


def generate_temp_password(length: int = 16) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@api_controller("/users", tags=["Users (Admin)"], permissions=[IsStaff])
class UserAdminController(BaseAPI):
    """Admin endpoints for user management. Requires staff permissions."""

    @http_get(
        "/",
        response={200: list[UserListSchema], 401: ErrorSchema, 403: ErrorSchema},
        url_name="users_list",
    )
    def list_users(self, request: HttpRequest):
        """List all users. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        users = User.objects.prefetch_related("groups__permissions").all()
        return 200, [UserListSchema.from_user(user) for user in users]

    @http_get(
        "/roles",
        response={200: RoleListSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="users_roles_list",
    )
    def list_roles(self, request: HttpRequest):
        """List all available roles. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        roles = [
            RoleSchema(name=role.value, description=ROLE_DESCRIPTIONS[role])
            for role in Role
        ]
        return 200, RoleListSchema(roles=roles)

    @http_post(
        "/create",
        response={201: UserDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 409: ErrorSchema},
        url_name="users_create",
    )
    def create_user(self, request: HttpRequest, data: UserCreateSchema):
        """Create a new user account (admin function)."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        if User.objects.filter(email__iexact=data.email).exists():
            return AlreadyExistsError("Un compte avec cet email existe déjà.").to_response()

        temp_password = generate_temp_password()

        user = User.objects.create_user(
            email=data.email,
            password=temp_password,
            first_name=data.first_name,
            last_name=data.last_name,
            is_active=False,
        )

        if data.groups:
            for group_name in data.groups:
                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass

        try:
            EmailAddress.objects.create(
                user=user,
                email=user.email,
                primary=True,
                verified=False,
            )

            send_verification_email_for_user(request, user)
        except Exception:
            logger.exception("Failed to send activation email for new user")

        return 201, UserListSchema.from_user(user)

    @http_get(
        "/{user_id}",
        response={200: UserDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_detail",
    )
    def get_user(self, request: HttpRequest, user_id: UUID):
        """Get user details by ID. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.prefetch_related("groups__permissions").get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        return 200, UserListSchema.from_user(user)

    @http_put(
        "/{user_id}",
        response={200: UserDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_update",
    )
    def update_user(self, request: HttpRequest, user_id: UUID, data: UserUpdateSchema):
        """Update user details. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        if data.first_name is not None:
            user.first_name = data.first_name
        if data.last_name is not None:
            user.last_name = data.last_name
        if data.is_active is not None:
            user.is_active = data.is_active

        user.save()

        if data.groups is not None:
            user.groups.clear()
            for group_name in data.groups:
                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass

        return 200, UserListSchema.from_user(user)

    @http_delete(
        "/{user_id}",
        response={200: MessageSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_delete",
    )
    def delete_user(self, request: HttpRequest, user_id: UUID):
        """Delete a user. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        if user.id == request.user.id:
            return 403, ErrorSchema(
                code="CANNOT_DELETE_SELF",
                message="Vous ne pouvez pas supprimer votre propre compte.",
            )

        if user.is_superuser and not request.user.is_superuser:
            return 403, ErrorSchema(
                code="CANNOT_DELETE_SUPERUSER",
                message="Seul un superutilisateur peut supprimer un autre superutilisateur.",
            )

        user.delete()
        return 200, MessageSchema(success=True, message="Utilisateur supprimé.")

    @http_post(
        "/{user_id}/resend-activation",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_resend_activation",
    )
    def resend_activation(self, request: HttpRequest, user_id: UUID):
        """Resend activation email to a user. Requires staff permissions."""
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        if user.is_active:
            return 400, ErrorSchema(
                code="ALREADY_ACTIVE",
                message="Ce compte est déjà activé.",
            )

        try:
            send_verification_email_for_user(request, user)
        except Exception as e:
            return 500, ErrorSchema(
                code="EMAIL_ERROR",
                message=f"Erreur lors de l'envoi de l'email: {e!s}",
            )

        return 200, MessageSchema(success=True, message="Email d'activation envoyé.")

    @http_put(
        "/{user_id}/roles",
        response={200: UserDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_set_roles",
    )
    def set_user_roles(self, request: HttpRequest, user_id: UUID, data: SetUserRoleSchema):
        """
        Set a user's roles. Replaces all existing roles.

        Requires staff permissions. Only superusers can assign Admin role.
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        # Validate role names
        valid_roles = Role.values()
        invalid_roles = [r for r in data.roles if r not in valid_roles]
        if invalid_roles:
            return ValidationError(
                message=f"Rôles invalides: {', '.join(invalid_roles)}",
                details={"invalid_roles": invalid_roles, "valid_roles": valid_roles},
            ).to_response()

        # Only superusers can assign Admin role
        if Role.ADMIN.value in data.roles and not request.user.is_superuser:
            return 403, ErrorSchema(
                code="CANNOT_ASSIGN_ADMIN",
                message="Seul un superutilisateur peut assigner le rôle Admin.",
            )

        # Clear existing role groups and assign new ones
        role_groups = Group.objects.filter(name__in=valid_roles)
        user.groups.remove(*role_groups)

        for role_name in data.roles:
            try:
                group = Group.objects.get(name=role_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                logger.warning(f"Role group not found: {role_name}")

        return 200, UserListSchema.from_user(user)

    @http_post(
        "/{user_id}/roles/add",
        response={200: UserDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_add_role",
    )
    def add_user_role(self, request: HttpRequest, user_id: UUID, data: SetUserRoleSchema):
        """
        Add role(s) to a user without removing existing roles.

        Requires staff permissions. Only superusers can assign Admin role.
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        # Validate role names
        valid_roles = Role.values()
        invalid_roles = [r for r in data.roles if r not in valid_roles]
        if invalid_roles:
            return ValidationError(
                message=f"Rôles invalides: {', '.join(invalid_roles)}",
                details={"invalid_roles": invalid_roles, "valid_roles": valid_roles},
            ).to_response()

        # Only superusers can assign Admin role
        if Role.ADMIN.value in data.roles and not request.user.is_superuser:
            return 403, ErrorSchema(
                code="CANNOT_ASSIGN_ADMIN",
                message="Seul un superutilisateur peut assigner le rôle Admin.",
            )

        for role_name in data.roles:
            try:
                group = Group.objects.get(name=role_name)
                user.groups.add(group)
            except Group.DoesNotExist:
                logger.warning(f"Role group not found: {role_name}")

        return 200, UserListSchema.from_user(user)

    @http_post(
        "/{user_id}/roles/remove",
        response={200: UserDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="users_remove_role",
    )
    def remove_user_role(self, request: HttpRequest, user_id: UUID, data: SetUserRoleSchema):
        """
        Remove role(s) from a user.

        Requires staff permissions.
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        # Validate role names
        valid_roles = Role.values()
        invalid_roles = [r for r in data.roles if r not in valid_roles]
        if invalid_roles:
            return ValidationError(
                message=f"Rôles invalides: {', '.join(invalid_roles)}",
                details={"invalid_roles": invalid_roles, "valid_roles": valid_roles},
            ).to_response()

        for role_name in data.roles:
            try:
                group = Group.objects.get(name=role_name)
                user.groups.remove(group)
            except Group.DoesNotExist:
                pass

        return 200, UserListSchema.from_user(user)
