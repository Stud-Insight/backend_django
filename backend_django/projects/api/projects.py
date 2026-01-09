"""
Academic projects API controller.
"""

from uuid import UUID

from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import File
from ninja import UploadedFile
from ninja_extra import api_controller
from ninja_extra import http_delete
from ninja_extra import http_get
from ninja_extra import http_post
from ninja_extra import http_put

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import NotFoundError
from backend_django.core.exceptions import NotOwnerError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.projects.models import AcademicProject
from backend_django.projects.models import AcademicProjectStatus
from backend_django.projects.models import Attachment
from backend_django.projects.models import get_current_academic_year
from backend_django.projects.schemas import AcademicProjectCreateSchema
from backend_django.projects.schemas import AcademicProjectDetailSchema
from backend_django.projects.schemas import AcademicProjectListSchema
from backend_django.projects.schemas import AcademicProjectUpdateSchema
from backend_django.projects.schemas import AttachmentMinimalSchema
from backend_django.projects.schemas import MessageSchema
from backend_django.projects.schemas import ProjectStatusUpdateSchema
from backend_django.projects.schemas import UserMinimalSchema
from backend_django.users.models import User


def project_to_list_schema(project: AcademicProject) -> AcademicProjectListSchema:
    """Convert AcademicProject to list schema."""
    return AcademicProjectListSchema(
        id=project.id,
        subject=project.subject,
        project_type=project.project_type,
        status=project.status,
        student=UserMinimalSchema.from_user(project.student),
        referent=UserMinimalSchema.from_user(project.referent) if project.referent else None,
        supervisor=UserMinimalSchema.from_user(project.supervisor) if project.supervisor else None,
        start_date=project.start_date,
        end_date=project.end_date,
        academic_year=project.academic_year,
        admin_validated=project.admin_validated,
        created=project.created,
        modified=project.modified,
    )


def project_to_detail_schema(project: AcademicProject) -> AcademicProjectDetailSchema:
    """Convert AcademicProject to detail schema."""
    return AcademicProjectDetailSchema(
        id=project.id,
        subject=project.subject,
        project_type=project.project_type,
        status=project.status,
        student=UserMinimalSchema.from_user(project.student),
        referent=UserMinimalSchema.from_user(project.referent) if project.referent else None,
        supervisor=UserMinimalSchema.from_user(project.supervisor) if project.supervisor else None,
        start_date=project.start_date,
        end_date=project.end_date,
        academic_year=project.academic_year,
        admin_validated=project.admin_validated,
        created=project.created,
        modified=project.modified,
        description=project.description,
        files=[
            AttachmentMinimalSchema(
                id=f.id,
                original_filename=f.original_filename,
                content_type=f.content_type,
                size=f.size,
                created=f.created,
            )
            for f in project.files.all()
        ],
        company_name=project.company_name,
        company_address=project.company_address,
        company_tutor_name=project.company_tutor_name,
        company_tutor_email=project.company_tutor_email,
        company_tutor_phone=project.company_tutor_phone,
        admin_validated_at=project.admin_validated_at,
        admin_validated_by=UserMinimalSchema.from_user(project.admin_validated_by) if project.admin_validated_by else None,
    )


@api_controller("/projects", tags=["Academic Projects"], permissions=[IsAuthenticated])
class AcademicProjectController(BaseAPI):
    """CRUD operations for academic projects."""

    @http_get(
        "/",
        response={200: list[AcademicProjectListSchema], 401: ErrorSchema},
        url_name="academic_projects_list",
    )
    def list_projects(
        self,
        request: HttpRequest,
        project_type: str | None = None,
        status: str | None = None,
        academic_year: str | None = None,
    ):
        """
        List projects with optional filtering.
        Staff sees all projects, others see only projects they're involved in.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if request.user.is_staff:
            projects = AcademicProject.objects.all()
        else:
            projects = AcademicProject.objects.filter(
                Q(student=request.user) | Q(referent=request.user) | Q(supervisor=request.user)
            )

        # Apply filters
        if project_type:
            projects = projects.filter(project_type=project_type)
        if status:
            projects = projects.filter(status=status)
        if academic_year:
            projects = projects.filter(academic_year=academic_year)

        projects = projects.select_related("student", "referent", "supervisor").order_by("-created")

        return 200, [project_to_list_schema(p) for p in projects]

    @http_get(
        "/my",
        response={200: list[AcademicProjectListSchema], 401: ErrorSchema},
        url_name="academic_projects_my",
    )
    def my_projects(self, request: HttpRequest, project_type: str | None = None):
        """Get all projects where current user is involved."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        projects = AcademicProject.objects.filter(
            Q(student=request.user) | Q(referent=request.user) | Q(supervisor=request.user)
        )

        if project_type:
            projects = projects.filter(project_type=project_type)

        projects = projects.select_related("student", "referent", "supervisor").order_by("-created")

        return 200, [project_to_list_schema(p) for p in projects]

    @http_get(
        "/ongoing",
        response={200: list[AcademicProjectListSchema], 401: ErrorSchema},
        url_name="academic_projects_ongoing",
    )
    def ongoing_projects(self, request: HttpRequest, project_type: str | None = None):
        """Get projects with status IN_PROGRESS."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if request.user.is_staff:
            projects = AcademicProject.objects.filter(status=AcademicProjectStatus.IN_PROGRESS)
        else:
            projects = AcademicProject.objects.filter(
                Q(student=request.user) | Q(referent=request.user) | Q(supervisor=request.user),
                status=AcademicProjectStatus.IN_PROGRESS,
            )

        if project_type:
            projects = projects.filter(project_type=project_type)

        projects = projects.select_related("student", "referent", "supervisor").order_by("-created")

        return 200, [project_to_list_schema(p) for p in projects]

    @http_get(
        "/pending-validation",
        response={200: list[AcademicProjectListSchema], 401: ErrorSchema, 403: ErrorSchema},
        url_name="academic_projects_pending_validation",
    )
    def pending_validation_projects(self, request: HttpRequest, project_type: str | None = None):
        """Get projects pending admin validation. Staff only."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        projects = AcademicProject.objects.filter(
            status=AcademicProjectStatus.PENDING,
            admin_validated=False,
        )

        if project_type:
            projects = projects.filter(project_type=project_type)

        projects = projects.select_related("student", "referent", "supervisor").order_by("-created")

        return 200, [project_to_list_schema(p) for p in projects]

    @http_get(
        "/archived",
        response={200: list[AcademicProjectListSchema], 401: ErrorSchema},
        url_name="academic_projects_archived",
    )
    def archived_projects(self, request: HttpRequest, project_type: str | None = None):
        """Get archived projects."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if request.user.is_staff:
            projects = AcademicProject.objects.filter(status=AcademicProjectStatus.ARCHIVED)
        else:
            projects = AcademicProject.objects.filter(
                Q(student=request.user) | Q(referent=request.user) | Q(supervisor=request.user),
                status=AcademicProjectStatus.ARCHIVED,
            )

        if project_type:
            projects = projects.filter(project_type=project_type)

        projects = projects.select_related("student", "referent", "supervisor").order_by("-created")

        return 200, [project_to_list_schema(p) for p in projects]

    @http_get(
        "/{project_id}",
        response={200: AcademicProjectDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_detail",
    )
    def get_project(self, request: HttpRequest, project_id: UUID):
        """Get project details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(
            AcademicProject.objects.select_related("student", "referent", "supervisor", "admin_validated_by").prefetch_related("files"),
            id=project_id,
        )

        if not project.is_user_involved(request.user):
            return PermissionDeniedError("Vous n'avez pas accès à ce projet.").to_response()

        return 200, project_to_detail_schema(project)

    @http_post(
        "/",
        response={201: AcademicProjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="academic_projects_create",
    )
    def create_project(self, request: HttpRequest, data: AcademicProjectCreateSchema):
        """
        Create a new project.
        Students create their own projects, staff can create for any student.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Determine the student
        if data.student_id:
            if not request.user.is_staff:
                return PermissionDeniedError("Seul le staff peut créer un projet pour un autre utilisateur.").to_response()
            student = User.objects.filter(id=data.student_id).first()
            if not student:
                return BadRequestError("Étudiant introuvable.").to_response()
        else:
            student = request.user

        # Get referent and supervisor
        referent = None
        supervisor = None
        if data.referent_id:
            referent = User.objects.filter(id=data.referent_id).first()
        if data.supervisor_id:
            supervisor = User.objects.filter(id=data.supervisor_id).first()

        project = AcademicProject.objects.create(
            student=student,
            referent=referent,
            supervisor=supervisor,
            subject=data.subject,
            project_type=data.project_type,
            description=data.description,
            start_date=data.start_date,
            end_date=data.end_date,
            academic_year=data.academic_year or get_current_academic_year(),
            company_name=data.company_name,
            company_address=data.company_address,
            company_tutor_name=data.company_tutor_name,
            company_tutor_email=data.company_tutor_email,
            company_tutor_phone=data.company_tutor_phone,
        )

        return 201, project_to_detail_schema(project)

    @http_put(
        "/{project_id}",
        response={200: AcademicProjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_update",
    )
    def update_project(self, request: HttpRequest, project_id: UUID, data: AcademicProjectUpdateSchema):
        """
        Update project. Only owner (if pending) or staff can update.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)

        # Check permissions
        is_owner = project.student_id == request.user.id
        if not request.user.is_staff:
            if not is_owner:
                return PermissionDeniedError("Vous n'êtes pas le propriétaire de ce projet.").to_response()
            if project.status != AcademicProjectStatus.PENDING:
                return PermissionDeniedError("Vous ne pouvez modifier que les projets en attente.").to_response()

        # Update fields
        if data.subject is not None:
            project.subject = data.subject
        if data.description is not None:
            project.description = data.description
        if data.start_date is not None:
            project.start_date = data.start_date
        if data.end_date is not None:
            project.end_date = data.end_date
        if data.referent_id is not None:
            project.referent = User.objects.filter(id=data.referent_id).first()
        if data.supervisor_id is not None:
            project.supervisor = User.objects.filter(id=data.supervisor_id).first()
        if data.company_name is not None:
            project.company_name = data.company_name
        if data.company_address is not None:
            project.company_address = data.company_address
        if data.company_tutor_name is not None:
            project.company_tutor_name = data.company_tutor_name
        if data.company_tutor_email is not None:
            project.company_tutor_email = data.company_tutor_email
        if data.company_tutor_phone is not None:
            project.company_tutor_phone = data.company_tutor_phone

        project.save()

        # Reload with relations
        project = AcademicProject.objects.select_related(
            "student", "referent", "supervisor", "admin_validated_by"
        ).prefetch_related("files").get(id=project_id)

        return 200, project_to_detail_schema(project)

    @http_delete(
        "/{project_id}",
        response={200: MessageSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_delete",
    )
    def delete_project(self, request: HttpRequest, project_id: UUID):
        """Delete project. Only owner (if pending) or staff."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)

        is_owner = project.student_id == request.user.id
        if not request.user.is_staff:
            if not is_owner:
                return PermissionDeniedError("Vous n'êtes pas le propriétaire de ce projet.").to_response()
            if project.status != AcademicProjectStatus.PENDING:
                return PermissionDeniedError("Vous ne pouvez supprimer que les projets en attente.").to_response()

        project.delete()

        return 200, MessageSchema(success=True, message="Projet supprimé avec succès.")

    @http_post(
        "/{project_id}/status",
        response={200: AcademicProjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_status",
    )
    def update_status(self, request: HttpRequest, project_id: UUID, data: ProjectStatusUpdateSchema):
        """
        Update project status.
        - PENDING -> VALIDATED: supervisor or staff
        - VALIDATED -> IN_PROGRESS: staff
        - IN_PROGRESS -> COMPLETED: student, supervisor, or staff
        - Any -> ARCHIVED: staff only
        - Any -> REJECTED: supervisor or staff (requires reason)
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)
        new_status = data.status

        # Permission checks based on transition
        is_supervisor = project.supervisor_id == request.user.id
        is_student = project.student_id == request.user.id

        if new_status == AcademicProjectStatus.VALIDATED:
            if not (is_supervisor or request.user.is_staff):
                return PermissionDeniedError("Seul l'encadrant ou le staff peut valider.").to_response()
        elif new_status == AcademicProjectStatus.IN_PROGRESS:
            if not request.user.is_staff:
                return PermissionDeniedError("Seul le staff peut passer un projet en cours.").to_response()
        elif new_status == AcademicProjectStatus.COMPLETED:
            if not (is_student or is_supervisor or request.user.is_staff):
                return PermissionDeniedError("Seul l'étudiant, l'encadrant ou le staff peut terminer.").to_response()
        elif new_status == AcademicProjectStatus.ARCHIVED:
            if not request.user.is_staff:
                return PermissionDeniedError("Seul le staff peut archiver.").to_response()
        elif new_status == AcademicProjectStatus.REJECTED:
            if not (is_supervisor or request.user.is_staff):
                return PermissionDeniedError("Seul l'encadrant ou le staff peut refuser.").to_response()
            if not data.reason:
                return BadRequestError("Une raison est requise pour le refus.").to_response()

        project.status = new_status
        project.save()

        project = AcademicProject.objects.select_related(
            "student", "referent", "supervisor", "admin_validated_by"
        ).prefetch_related("files").get(id=project_id)

        return 200, project_to_detail_schema(project)

    @http_post(
        "/{project_id}/validate",
        response={200: AcademicProjectDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_admin_validate",
    )
    def admin_validate(self, request: HttpRequest, project_id: UUID):
        """Administrative validation for projects. Staff only."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError("Permission staff requise.").to_response()

        project = get_object_or_404(AcademicProject, id=project_id)

        project.admin_validated = True
        project.admin_validated_at = timezone.now()
        project.admin_validated_by = request.user
        project.save()

        project = AcademicProject.objects.select_related(
            "student", "referent", "supervisor", "admin_validated_by"
        ).prefetch_related("files").get(id=project_id)

        return 200, project_to_detail_schema(project)

    @http_post(
        "/{project_id}/files",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_upload_file",
    )
    def upload_file(self, request: HttpRequest, project_id: UUID, file: UploadedFile = File(...)):
        """Upload a file to a project."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)

        if not project.is_user_involved(request.user):
            return PermissionDeniedError("Vous n'avez pas accès à ce projet.").to_response()

        if not file:
            return BadRequestError("Aucun fichier fourni.").to_response()

        attachment = Attachment.objects.create(
            file=file,
            original_filename=file.name,
            content_type=file.content_type or "application/octet-stream",
            size=file.size,
            owner=request.user,
        )

        project.files.add(attachment)

        return 200, MessageSchema(success=True, message=f"Fichier {file.name} ajouté au projet.")

    @http_delete(
        "/{project_id}/files/{file_id}",
        response={200: MessageSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="academic_projects_delete_file",
    )
    def delete_file(self, request: HttpRequest, project_id: UUID, file_id: UUID):
        """Remove a file from project."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        project = get_object_or_404(AcademicProject, id=project_id)
        attachment = get_object_or_404(Attachment, id=file_id)

        # Check permissions
        is_owner = attachment.owner_id == request.user.id
        if not (is_owner or request.user.is_staff):
            return NotOwnerError("Vous n'êtes pas le propriétaire de ce fichier.").to_response()

        # Remove from project and delete file
        project.files.remove(attachment)
        attachment.file.delete(save=False)
        attachment.delete()

        return 200, MessageSchema(success=True, message="Fichier supprimé avec succès.")
