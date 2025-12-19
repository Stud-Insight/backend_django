"""
Attachments and academic projects API controller.
"""

from uuid import UUID

from django.db.models import Q
from django.http import HttpRequest
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
