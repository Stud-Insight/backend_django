"""
Attachments and academic projects API controller.
"""

from uuid import UUID

import boto3
from botocore.config import Config
from django.conf import settings
from django.db.models import Q
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
from backend_django.projects.models import AcademicProject
from backend_django.projects.models import Attachment
from backend_django.projects.schemas import AcademicProjectCreateSchema
from backend_django.projects.schemas import AcademicProjectSchema
from backend_django.projects.schemas import AttachmentSchema
from backend_django.projects.schemas import AttachmentUploadResponse


@api_controller("/attachments", tags=["Attachments & Projects"], permissions=[IsAuthenticated])
class AttachmentsController(BaseAPI):
    """API endpoints for attachments and academic projects."""

    @http_get(
        "/projects",
        response={200: list[AcademicProjectSchema], 401: ErrorSchema},
        url_name="projects_list",
    )
    def list_projects(self, request: HttpRequest):
        """List academic projects for the current user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        projects = AcademicProject.objects.filter(
            Q(student=request.user) | Q(referent=request.user) | Q(supervisor=request.user)
        ).prefetch_related("files")

        return 200, [
            AcademicProjectSchema(
                id=p.id,
                student_id=p.student_id,
                referent_id=p.referent_id,
                supervisor_id=p.supervisor_id,
                subject=p.subject,
                project_type=p.project_type,
                start_date=p.start_date,
                end_date=p.end_date,
                created=p.created,
                modified=p.modified,
                files=[
                    AttachmentSchema(
                        id=f.id,
                        original_filename=f.original_filename,
                        content_type=f.content_type,
                        size=f.size,
                        created=f.created,
                    )
                    for f in p.files.all()
                ],
            )
            for p in projects
        ]

    @http_post(
        "/projects",
        response={201: AcademicProjectSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="projects_create",
    )
    def create_project(self, request: HttpRequest, data: AcademicProjectCreateSchema):
        """Create a new academic project. Requires staff permissions."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        project = AcademicProject.objects.create(
            student_id=data.student_id,
            referent_id=data.referent_id,
            supervisor_id=data.supervisor_id,
            subject=data.subject,
            project_type=data.project_type,
            start_date=data.start_date,
            end_date=data.end_date,
        )

        return 201, AcademicProjectSchema(
            id=project.id,
            student_id=project.student_id,
            referent_id=project.referent_id,
            supervisor_id=project.supervisor_id,
            subject=project.subject,
            project_type=project.project_type,
            start_date=project.start_date,
            end_date=project.end_date,
            created=project.created,
            modified=project.modified,
            files=[],
        )

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

        if attachment.owner_id != request.user.id and not request.user.is_staff:
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

    @http_post(
        "/projects/{project_id}/attach/{attachment_id}",
        response={200: dict, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="projects_attach_file",
    )
    def attach_file_to_project(self, request: HttpRequest, project_id: UUID, attachment_id: UUID):
        """Attach a file to an academic project."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)
        attachment = get_object_or_404(Attachment, id=attachment_id)

        # Check if user has access to the project
        if not (
            project.student_id == request.user.id
            or project.referent_id == request.user.id
            or project.supervisor_id == request.user.id
            or request.user.is_staff
        ):
            return PermissionDeniedError().to_response()

        # Check if user owns the attachment
        if attachment.owner_id != request.user.id and not request.user.is_staff:
            return NotOwnerError("Vous n'êtes pas le propriétaire de ce fichier.").to_response()

        project.files.add(attachment)

        return {"success": True, "message": "Fichier associé au projet avec succès."}
