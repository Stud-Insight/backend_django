"""
Admin API controller for user management.
"""

import csv
import io
import logging
import secrets
import string
from uuid import UUID

from allauth.account.internal.flows.email_verification import send_verification_email_for_user
from allauth.account.models import EmailAddress
from django.contrib.auth.models import Group
from django.http import HttpRequest
from ninja import File, UploadedFile
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
from backend_django.users.schemas import CSVImportErrorSchema
from backend_django.users.schemas import CSVImportResultSchema
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
            company_name=data.company_name,
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

    @http_post(
        "/import-csv",
        response={200: CSVImportResultSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="users_import_csv",
    )
    def import_users_csv(self, request: HttpRequest, file: UploadedFile = File(...)):
        """
        Import users from a CSV file.

        CSV format: email,first_name,last_name (header row required)
        - email: Required, must be valid email format
        - first_name: Required
        - last_name: Optional

        Users are created with:
        - is_active=False (requires email verification)
        - Role "Etudiant" assigned by default
        - Activation email sent automatically

        Returns a summary with created users, skipped (duplicates), and errors.
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        # Read and decode file
        try:
            content = file.read().decode("utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            try:
                file.seek(0)
                content = file.read().decode("latin-1")
            except Exception:
                return 400, ErrorSchema(
                    code="INVALID_ENCODING",
                    message="Encodage du fichier invalide. Utilisez UTF-8 ou Latin-1.",
                )

        # Parse CSV
        errors: list[CSVImportErrorSchema] = []
        created_users: list[User] = []
        skipped_count = 0

        try:
            reader = csv.DictReader(io.StringIO(content), delimiter=",")

            # Validate header
            if not reader.fieldnames:
                return 400, ErrorSchema(
                    code="INVALID_CSV",
                    message="Fichier CSV vide ou invalide.",
                )

            # Normalize field names (lowercase, strip)
            fieldnames = [f.lower().strip() for f in reader.fieldnames]

            if "email" not in fieldnames:
                return 400, ErrorSchema(
                    code="MISSING_COLUMN",
                    message="Colonne 'email' manquante dans le CSV.",
                )

            if "first_name" not in fieldnames and "prenom" not in fieldnames and "prénom" not in fieldnames:
                return 400, ErrorSchema(
                    code="MISSING_COLUMN",
                    message="Colonne 'first_name' ou 'prenom' manquante dans le CSV.",
                )

        except csv.Error as e:
            return 400, ErrorSchema(
                code="INVALID_CSV",
                message=f"Erreur de parsing CSV: {e!s}",
            )

        # Re-read with normalized fieldnames
        reader = csv.DictReader(io.StringIO(content), delimiter=",")

        # Get Etudiant group for default assignment
        etudiant_group = None
        try:
            etudiant_group = Group.objects.get(name=Role.ETUDIANT.value)
        except Group.DoesNotExist:
            logger.warning("Etudiant group not found, users will be created without role")

        for line_num, row in enumerate(reader, start=2):  # Start at 2 (header is line 1)
            # Normalize row keys
            row = {k.lower().strip(): v.strip() if v else "" for k, v in row.items()}

            # Extract fields with fallbacks for French column names
            email = row.get("email", "").lower()
            first_name = row.get("first_name") or row.get("prenom") or row.get("prénom", "")
            last_name = row.get("last_name") or row.get("nom", "")

            # Validate email
            if not email:
                errors.append(CSVImportErrorSchema(
                    line=line_num,
                    email=None,
                    error="Email manquant.",
                ))
                continue

            if "@" not in email or "." not in email:
                errors.append(CSVImportErrorSchema(
                    line=line_num,
                    email=email,
                    error="Format d'email invalide.",
                ))
                continue

            # Validate first_name
            if not first_name:
                errors.append(CSVImportErrorSchema(
                    line=line_num,
                    email=email,
                    error="Prénom manquant.",
                ))
                continue

            # Check if user already exists
            if User.objects.filter(email__iexact=email).exists():
                skipped_count += 1
                continue

            # Create user
            try:
                temp_password = generate_temp_password()

                user = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=False,
                )

                # Assign Etudiant role
                if etudiant_group:
                    user.groups.add(etudiant_group)

                # Create EmailAddress for allauth
                EmailAddress.objects.create(
                    user=user,
                    email=user.email,
                    primary=True,
                    verified=False,
                )

                # Send activation email
                try:
                    send_verification_email_for_user(request, user)
                except Exception:
                    logger.exception(f"Failed to send activation email for {email}")

                created_users.append(user)

            except Exception as e:
                logger.exception(f"Failed to create user {email}")
                errors.append(CSVImportErrorSchema(
                    line=line_num,
                    email=email,
                    error=f"Erreur de création: {e!s}",
                ))

        return 200, CSVImportResultSchema(
            success=len(errors) == 0,
            created_count=len(created_users),
            skipped_count=skipped_count,
            error_count=len(errors),
            errors=errors,
            created_users=[UserListSchema.from_user(u) for u in created_users],
        )

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
        if data.company_name is not None:
            user.company_name = data.company_name
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
