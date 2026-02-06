"""
TER Deliverables API controller.

Handles file uploads and downloads for TER group deliverables.
Supports async uploads for large files via Celery.
"""

from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect, FileResponse
from django.shortcuts import get_object_or_404
from ninja import File, UploadedFile
from ninja_extra import api_controller, http_delete, http_get, http_post, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    MAX_DELIVERABLE_SIZE_BYTES,
    DeliverableType,
    TERDeliverable,
    TERPeriod,
    UploadStatus,
)
from backend_django.ter.schemas.deliverables import (
    FILE_SIZE_LIMIT_MB,
    TERDeliverableListSchema,
    TERDeliverableSchema,
    TERDeliverableUpdateSchema,
    TERDeliverableUploadResponse,
    TERDeliverableUploadSchema,
    UploadStatusResponse,
)


def validate_file_size(file: UploadedFile) -> str | None:
    """
    Validate file size against limit.
    Returns error message if invalid, None if valid.
    """
    if file.size > MAX_DELIVERABLE_SIZE_BYTES:
        return f"Fichier trop volumineux - max {FILE_SIZE_LIMIT_MB}MB (taille: {file.size / (1024*1024):.1f}MB)"
    return None


def get_user_group_for_period(user, ter_period: TERPeriod) -> Group | None:
    """Get the user's group for a specific TER period."""
    return Group.objects.filter(
        ter_period=ter_period,
        members=user,
        status__in=[GroupStatus.FORME, GroupStatus.CLOTURE],
    ).first()


@api_controller("/ter/deliverables", tags=["TER Deliverables"], permissions=[IsAuthenticated])
class TERDeliverablesController(BaseAPI):
    """API endpoints for TER deliverables (upload, download, delete)."""

    @http_post(
        "/upload/{group_id}",
        response={
            201: TERDeliverableUploadResponse,
            400: ErrorSchema,
            401: ErrorSchema,
            403: ErrorSchema,
            404: ErrorSchema,
        },
        url_name="ter_deliverables_upload",
    )
    def upload_deliverable(
        self,
        request: HttpRequest,
        group_id: UUID,
        file: UploadedFile = File(...),
        deliverable_type: str = "other",
        description: str = "",
        is_confidential: bool = False,
    ):
        """
        Upload a deliverable for a group.

        Only group members can upload deliverables.
        Max file size: 50MB.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Get and validate group
        group = get_object_or_404(Group, id=group_id)

        # Check user is member of the group
        if not group.members.filter(id=request.user.id).exists():
            if not is_ter_admin(request.user):
                return PermissionDeniedError(
                    "Vous devez etre membre du groupe pour soumettre un livrable."
                ).to_response()

        # Check group has a TER period
        if not group.ter_period:
            return BadRequestError(
                "Ce groupe n'est pas associe a une periode TER."
            ).to_response()

        # Validate file
        if not file:
            return BadRequestError("Aucun fichier fourni.").to_response()

        # Validate file size
        size_error = validate_file_size(file)
        if size_error:
            return BadRequestError(size_error).to_response()

        # Validate deliverable type
        valid_types = [t.value for t in DeliverableType]
        if deliverable_type not in valid_types:
            return BadRequestError(
                f"Type de livrable invalide. Valeurs acceptees: {', '.join(valid_types)}"
            ).to_response()

        # Create deliverable (sync upload for files under threshold)
        deliverable = TERDeliverable.objects.create(
            ter_period=group.ter_period,
            group=group,
            uploaded_by=request.user,
            file=file,
            original_filename=file.name,
            content_type=file.content_type or "application/octet-stream",
            size=file.size,
            deliverable_type=deliverable_type,
            description=description,
            is_confidential=is_confidential,
            upload_status=UploadStatus.COMPLETED,
        )

        return 201, TERDeliverableUploadResponse(
            success=True,
            message=f"Fichier '{file.name}' televerse avec succes.",
            deliverable_id=deliverable.id,
            upload_status=UploadStatus.COMPLETED,
            is_async=False,
        )

    @http_get(
        "/group/{group_id}",
        response={200: list[TERDeliverableListSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_list",
    )
    def list_group_deliverables(self, request: HttpRequest, group_id: UUID):
        """List all deliverables for a group."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission to view group deliverables
        is_member = group.members.filter(id=request.user.id).exists()
        is_admin = is_ter_admin(request.user)

        if not is_member and not is_admin:
            # Check if user is encadrant for this group's subject
            is_encadrant = False
            if hasattr(group, "assigned_subject") and group.assigned_subject:
                subject = group.assigned_subject
                is_encadrant = (
                    subject.professor_id == request.user.id
                    or subject.supervisor_id == request.user.id
                )

            if not is_encadrant:
                return PermissionDeniedError(
                    "Vous n'avez pas acces aux livrables de ce groupe."
                ).to_response()

        deliverables = TERDeliverable.objects.filter(group=group).order_by("-created")

        # Filter confidential if not member/admin/encadrant
        if not is_member and not is_admin:
            deliverables = deliverables.filter(is_confidential=False)

        return 200, [
            TERDeliverableListSchema(
                id=d.id,
                original_filename=d.original_filename,
                content_type=d.content_type,
                size=d.size,
                deliverable_type=d.deliverable_type,
                is_confidential=d.is_confidential,
                upload_status=d.upload_status,
                created=d.created,
            )
            for d in deliverables
        ]

    @http_get(
        "/{deliverable_id}",
        response={200: TERDeliverableSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_detail",
    )
    def get_deliverable(self, request: HttpRequest, deliverable_id: UUID):
        """Get deliverable metadata."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        deliverable = get_object_or_404(TERDeliverable, id=deliverable_id)

        if not deliverable.can_be_viewed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas acces a ce livrable."
            ).to_response()

        return 200, TERDeliverableSchema(
            id=deliverable.id,
            ter_period_id=deliverable.ter_period_id,
            group_id=deliverable.group_id,
            uploaded_by_id=deliverable.uploaded_by_id,
            original_filename=deliverable.original_filename,
            content_type=deliverable.content_type,
            size=deliverable.size,
            deliverable_type=deliverable.deliverable_type,
            description=deliverable.description,
            is_confidential=deliverable.is_confidential,
            upload_status=deliverable.upload_status,
            upload_error=deliverable.upload_error,
            created=deliverable.created,
            modified=deliverable.modified,
        )

    @http_get(
        "/{deliverable_id}/download",
        response={400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_download",
    )
    def download_deliverable(self, request: HttpRequest, deliverable_id: UUID):
        """Download a deliverable file."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        deliverable = get_object_or_404(TERDeliverable, id=deliverable_id)

        if not deliverable.can_be_viewed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas acces a ce livrable."
            ).to_response()

        # Check upload is complete
        if deliverable.upload_status != UploadStatus.COMPLETED:
            return BadRequestError(
                f"Le fichier n'est pas encore disponible (statut: {deliverable.upload_status})."
            ).to_response()

        # If using S3/MinIO, generate presigned URL
        if getattr(settings, "USE_S3_STORAGE", False):
            import boto3
            from botocore.config import Config

            public_url = getattr(settings, "AWS_S3_PUBLIC_URL", None)
            if public_url:
                s3_client = boto3.client(
                    "s3",
                    endpoint_url=public_url,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
                    config=Config(signature_version="s3v4"),
                )

                signed_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                        "Key": deliverable.file.name,
                        "ResponseContentDisposition": f'attachment; filename="{deliverable.original_filename}"',
                    },
                    ExpiresIn=3600,
                )
                return HttpResponseRedirect(signed_url)

        # Fallback: stream file directly
        return FileResponse(
            deliverable.file.open("rb"),
            as_attachment=True,
            filename=deliverable.original_filename,
            content_type=deliverable.content_type,
        )

    @http_get(
        "/{deliverable_id}/status",
        response={200: UploadStatusResponse, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_status",
    )
    def get_upload_status(self, request: HttpRequest, deliverable_id: UUID):
        """Check the upload status of a deliverable."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        deliverable = get_object_or_404(TERDeliverable, id=deliverable_id)

        # Only uploader, group members, or admin can check status
        if deliverable.uploaded_by_id != request.user.id:
            if not deliverable.group.members.filter(id=request.user.id).exists():
                if not is_ter_admin(request.user):
                    return PermissionDeniedError(
                        "Vous n'avez pas acces a ce livrable."
                    ).to_response()

        return 200, UploadStatusResponse(
            deliverable_id=deliverable.id,
            upload_status=deliverable.upload_status,
            upload_error=deliverable.upload_error,
            original_filename=deliverable.original_filename,
            size=deliverable.size,
            is_complete=deliverable.upload_status == UploadStatus.COMPLETED,
        )

    @http_put(
        "/{deliverable_id}",
        response={200: TERDeliverableSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_update",
    )
    def update_deliverable(
        self, request: HttpRequest, deliverable_id: UUID, data: TERDeliverableUpdateSchema
    ):
        """Update deliverable metadata (type, description, confidentiality)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        deliverable = get_object_or_404(TERDeliverable, id=deliverable_id)

        if not deliverable.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour modifier ce livrable."
            ).to_response()

        if data.deliverable_type is not None:
            valid_types = [t.value for t in DeliverableType]
            if data.deliverable_type not in valid_types:
                return BadRequestError(
                    f"Type invalide. Valeurs acceptees: {', '.join(valid_types)}"
                ).to_response()
            deliverable.deliverable_type = data.deliverable_type

        if data.description is not None:
            deliverable.description = data.description

        if data.is_confidential is not None:
            deliverable.is_confidential = data.is_confidential

        deliverable.save()

        return 200, TERDeliverableSchema(
            id=deliverable.id,
            ter_period_id=deliverable.ter_period_id,
            group_id=deliverable.group_id,
            uploaded_by_id=deliverable.uploaded_by_id,
            original_filename=deliverable.original_filename,
            content_type=deliverable.content_type,
            size=deliverable.size,
            deliverable_type=deliverable.deliverable_type,
            description=deliverable.description,
            is_confidential=deliverable.is_confidential,
            upload_status=deliverable.upload_status,
            upload_error=deliverable.upload_error,
            created=deliverable.created,
            modified=deliverable.modified,
        )

    @http_delete(
        "/{deliverable_id}",
        response={200: dict, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_deliverables_delete",
    )
    def delete_deliverable(self, request: HttpRequest, deliverable_id: UUID):
        """Delete a deliverable."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        deliverable = get_object_or_404(TERDeliverable, id=deliverable_id)

        if not deliverable.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour supprimer ce livrable."
            ).to_response()

        filename = deliverable.original_filename

        # Delete file from storage
        if deliverable.file:
            deliverable.file.delete(save=False)

        deliverable.delete()

        return 200, {"success": True, "message": f"Livrable '{filename}' supprime."}
