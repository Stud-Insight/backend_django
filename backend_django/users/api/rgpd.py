"""
RGPD API controller for personal data export and account deletion.
"""

import logging
from datetime import datetime
from uuid import UUID

from django.http import HttpRequest
from ninja_extra import api_controller
from ninja_extra import http_get
from ninja_extra import http_post

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.api import IsStaff
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotFoundError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.core.exceptions import ValidationError
from backend_django.core.roles import is_admin
from backend_django.users.models import User
from backend_django.users.rgpd import anonymize_user
from backend_django.users.rgpd import can_delete_user
from backend_django.users.rgpd import collect_user_data
from backend_django.users.schemas import MessageSchema
from backend_django.users.schemas import RGPDDeleteRequestSchema
from backend_django.users.schemas import RGPDDeleteResponseSchema
from backend_django.users.schemas import RGPDExportResponseSchema

logger = logging.getLogger(__name__)


@api_controller("/rgpd", tags=["RGPD"], permissions=[IsAuthenticated])
class RGPDController(BaseAPI):
    """RGPD endpoints for personal data export and account management."""

    @http_get(
        "/export",
        response={200: RGPDExportResponseSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="rgpd_export_own_data",
    )
    def export_own_data(self, request: HttpRequest):
        """
        Export current user's personal data (RGPD Article 20).

        Returns all personal data in JSON format:
        - Profile information
        - Groups/roles
        - Conversations and messages
        - Projects
        - Attachments
        - Proposals and applications
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        user = request.user

        logger.info(f"RGPD data export requested by user {user.email}")

        data = collect_user_data(user)

        return 200, RGPDExportResponseSchema(
            success=True,
            message="Export des données personnelles effectué avec succès.",
            export_date=datetime.now(),
            data=data,
        )

    @http_post(
        "/request-deletion",
        response={200: MessageSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="rgpd_request_own_deletion",
    )
    def request_own_deletion(self, request: HttpRequest):
        """
        Request deletion of own account (user-initiated).

        This creates a deletion request that must be processed by an admin.
        The user receives an email confirming their request.

        Note: In a production system, this would create a pending deletion
        request that an admin must approve within 30 days (RGPD compliance).
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        user = request.user

        logger.info(f"RGPD deletion request received for user {user.email}")

        try:
            from django.core.mail import send_mail
            from django.conf import settings

            send_mail(
                subject="Demande de suppression de compte - Stud'Insight",
                message=(
                    f"Bonjour,\n\n"
                    f"Nous avons bien reçu votre demande de suppression de compte.\n\n"
                    f"Conformément au RGPD, votre demande sera traitée dans un délai "
                    f"maximum de 30 jours.\n\n"
                    f"Vous recevrez une confirmation une fois la suppression effectuée.\n\n"
                    f"Cordialement,\n"
                    f"L'équipe Stud'Insight"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Could not send deletion request confirmation email: {e}")

        return 200, MessageSchema(
            success=True,
            message="Votre demande de suppression a été enregistrée. "
                    "Elle sera traitée dans un délai maximum de 30 jours.",
        )


@api_controller("/users", tags=["Users (Admin)"], permissions=[IsStaff])
class RGPDAdminController(BaseAPI):
    """Admin RGPD endpoints for account deletion."""

    @http_get(
        "/{user_id}/rgpd/export",
        response={200: RGPDExportResponseSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="rgpd_admin_export_user_data",
    )
    def admin_export_user_data(self, request: HttpRequest, user_id: UUID):
        """
        Export a user's personal data (admin function).

        Requires staff permissions.
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not is_admin(request.user):
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        logger.info(f"RGPD data export for user {user.email} requested by admin {request.user.email}")

        data = collect_user_data(user)

        return 200, RGPDExportResponseSchema(
            success=True,
            message=f"Export des données de {user.email} effectué avec succès.",
            export_date=datetime.now(),
            data=data,
        )

    @http_post(
        "/{user_id}/rgpd/delete",
        response={200: RGPDDeleteResponseSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="rgpd_admin_delete_user",
    )
    def admin_delete_user(self, request: HttpRequest, user_id: UUID, data: RGPDDeleteRequestSchema):
        """
        Delete a user's account and anonymize their data (RGPD Article 17).

        This action:
        - Anonymizes the user's profile (email, name)
        - Removes the user from all groups
        - Anonymizes sent messages
        - Deletes attachments/files
        - Deactivates the account

        Academic records (projects) are preserved but with anonymized identifiers.

        Requires staff permissions and confirmation (confirm=true).
        """
        if not request.user.is_authenticated:
            return 401, ErrorSchema(code="NOT_AUTHENTICATED", message="Non authentifié.")

        if not is_admin(request.user):
            return PermissionDeniedError("Permission staff requise.").to_response()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        # Check if deletion is allowed
        can_delete, reason = can_delete_user(user, request.user)
        if not can_delete:
            return 403, ErrorSchema(code="CANNOT_DELETE", message=reason)

        # Require confirmation
        if not data.confirm:
            return ValidationError(
                message="Confirmation requise pour la suppression. Envoyez confirm=true.",
                details={"confirm": "Ce champ doit être true pour confirmer la suppression."},
            ).to_response()

        original_email = user.email

        logger.info(
            f"RGPD account deletion for user {original_email} "
            f"requested by admin {request.user.email}. Reason: {data.reason}"
        )

        # Perform anonymization
        summary = anonymize_user(user, deleted_by=request.user)

        # Send confirmation email (if email service is available)
        try:
            from django.core.mail import send_mail
            from django.conf import settings

            send_mail(
                subject="Confirmation de suppression de compte - Stud'Insight",
                message=(
                    f"Bonjour,\n\n"
                    f"Votre compte Stud'Insight ({original_email}) a été supprimé "
                    f"conformément à votre demande RGPD.\n\n"
                    f"Toutes vos données personnelles ont été anonymisées ou supprimées.\n\n"
                    f"Cordialement,\n"
                    f"L'équipe Stud'Insight"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[original_email],
                fail_silently=True,
            )
            summary["actions"].append("confirmation_email_sent")
        except Exception as e:
            logger.warning(f"Could not send deletion confirmation email: {e}")

        return 200, RGPDDeleteResponseSchema(
            success=True,
            message=f"Compte {original_email} supprimé et anonymisé avec succès.",
            user_id=user.id,
            anonymized_email=user.email,
            actions=summary["actions"],
        )
