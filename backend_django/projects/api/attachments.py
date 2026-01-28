"""
Attachments API controller.

Handles file uploads and downloads to MinIO/S3 storage.
"""

from uuid import UUID

import boto3
from botocore.config import Config
from django.conf import settings
from django.http import FileResponse
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from ninja import File
from ninja import UploadedFile
from ninja_extra import api_controller
from ninja_extra import http_delete
from ninja_extra import http_get
from ninja_extra import http_post

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import NotOwnerError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.core.roles import is_admin_or_respo
from backend_django.projects.models import Attachment
from backend_django.projects.schemas import AttachmentSchema
from backend_django.projects.schemas import AttachmentUploadResponse


@api_controller("/attachments", tags=["Attachments"], permissions=[IsAuthenticated])
class AttachmentsController(BaseAPI):
    """API endpoints for file attachments (upload, download, delete)."""

    @http_post(
        "/upload",
        response={200: AttachmentUploadResponse, 400: ErrorSchema, 401: ErrorSchema},
        url_name="attachments_upload",
    )
    def upload_file(self, request: HttpRequest, file: UploadedFile = File(...)):
        """Upload a file to MinIO/S3."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not file:
            return BadRequestError("Aucun fichier fourni.").to_response()

        attachment = Attachment.objects.create(
            file=file,
            original_filename=file.name,
            content_type=file.content_type or "application/octet-stream",
            size=file.size,
            owner=request.user,
        )

        return AttachmentUploadResponse(
            success=True,
            message=f"Fichier {file.name} téléversé avec succès.",
            file_id=attachment.id,
        )

    @http_get(
        "/{attachment_id}",
        response={200: AttachmentSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="attachments_detail",
    )
    def get_attachment(self, request: HttpRequest, attachment_id: UUID):
        """Get attachment metadata."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        attachment = get_object_or_404(Attachment, id=attachment_id)

        if not attachment.can_be_viewed_by(request.user):
            return PermissionDeniedError().to_response()

        return AttachmentSchema(
            id=attachment.id,
            original_filename=attachment.original_filename,
            content_type=attachment.content_type,
            size=attachment.size,
            created=attachment.created,
        )

    @http_get(
        "/{attachment_id}/download",
        response={401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="attachments_download",
    )
    def download_attachment(self, request: HttpRequest, attachment_id: UUID):
        """Download an attachment file."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        attachment = get_object_or_404(Attachment, id=attachment_id)

        if not attachment.can_be_viewed_by(request.user):
            return PermissionDeniedError().to_response()

        # If S3/MinIO with public URL configured, redirect to signed URL
        public_url = getattr(settings, "AWS_S3_PUBLIC_URL", None)
        if getattr(settings, "USE_S3_STORAGE", False) and public_url:
            # Create S3 client with public endpoint for URL generation
            s3_client = boto3.client(
                "s3",
                endpoint_url=public_url,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=getattr(settings, "AWS_S3_REGION_NAME", "us-east-1"),
                config=Config(signature_version="s3v4"),
            )

            # Generate presigned URL
            signed_url = s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": attachment.file.name,
                    "ResponseContentDisposition": f'attachment; filename="{attachment.original_filename}"',
                },
                ExpiresIn=3600,  # 1 hour
            )
            return HttpResponseRedirect(signed_url)

        # Fallback: stream the file directly
        return FileResponse(
            attachment.file.open("rb"),
            as_attachment=True,
            filename=attachment.original_filename,
            content_type=attachment.content_type,
        )

    @http_delete(
        "/{attachment_id}",
        response={200: dict, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="attachments_delete",
    )
    def delete_attachment(self, request: HttpRequest, attachment_id: UUID):
        """Delete an attachment. Only the owner can delete their files."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        attachment = get_object_or_404(Attachment, id=attachment_id)

        if attachment.owner_id != request.user.id and not is_admin_or_respo(request.user):
            return NotOwnerError().to_response()

        attachment.file.delete(save=False)
        attachment.delete()

        return {"success": True, "message": "Fichier supprimé avec succès."}

    @http_get(
        "/",
        response={200: list[AttachmentSchema], 401: ErrorSchema},
        url_name="attachments_list",
    )
    def list_attachments(self, request: HttpRequest):
        """List all attachments owned by the current user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        attachments = Attachment.objects.filter(owner=request.user).order_by("-created")

        return 200, [
            AttachmentSchema(
                id=a.id,
                original_filename=a.original_filename,
                content_type=a.content_type,
                size=a.size,
                created=a.created,
            )
            for a in attachments
        ]
