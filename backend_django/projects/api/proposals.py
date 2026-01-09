"""
Proposals API controller.
"""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Count
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller
from ninja_extra import http_delete
from ninja_extra import http_get
from ninja_extra import http_post
from ninja_extra import http_put

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.exceptions import AlreadyExistsError
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.projects.models import AcademicProject
from backend_django.projects.models import AcademicProjectStatus
from backend_django.projects.models import ApplicationStatus
from backend_django.projects.models import Proposal
from backend_django.projects.models import ProposalApplication
from backend_django.projects.models import ProposalStatus
from backend_django.projects.models import get_current_academic_year
from backend_django.projects.schemas import ApplicationCreateSchema
from backend_django.projects.schemas import ApplicationSchema
from backend_django.projects.schemas import MessageSchema
from backend_django.projects.schemas import ProposalCreateSchema
from backend_django.projects.schemas import ProposalDetailSchema
from backend_django.projects.schemas import ProposalListSchema
from backend_django.projects.schemas import ProposalUpdateSchema
from backend_django.projects.schemas import UserMinimalSchema
from backend_django.users.models import User


def application_to_schema(app: ProposalApplication) -> ApplicationSchema:
    """Convert ProposalApplication to schema."""
    return ApplicationSchema(
        id=app.id,
        applicant=UserMinimalSchema.from_user(app.applicant),
        motivation=app.motivation,
        status=app.status,
        created=app.created,
    )


def proposal_to_list_schema(proposal: Proposal, applications_count: int = 0) -> ProposalListSchema:
    """Convert Proposal to list schema."""
    return ProposalListSchema(
        id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        project_type=proposal.project_type,
        status=proposal.status,
        created_by=UserMinimalSchema.from_user(proposal.created_by),
        supervisor=UserMinimalSchema.from_user(proposal.supervisor) if proposal.supervisor else None,
        academic_year=proposal.academic_year,
        is_professor_proposal=proposal.is_professor_proposal,
        applications_count=applications_count,
        created=proposal.created,
        modified=proposal.modified,
    )


def proposal_to_detail_schema(proposal: Proposal) -> ProposalDetailSchema:
    """Convert Proposal to detail schema."""
    applications = [application_to_schema(app) for app in proposal.applications.select_related("applicant").all()]
    return ProposalDetailSchema(
        id=proposal.id,
        title=proposal.title,
        description=proposal.description,
        project_type=proposal.project_type,
        status=proposal.status,
        created_by=UserMinimalSchema.from_user(proposal.created_by),
        supervisor=UserMinimalSchema.from_user(proposal.supervisor) if proposal.supervisor else None,
        academic_year=proposal.academic_year,
        is_professor_proposal=proposal.is_professor_proposal,
        applications_count=len(applications),
        created=proposal.created,
        modified=proposal.modified,
        applications=applications,
        resulting_project_id=proposal.resulting_project_id,
    )


@api_controller("/proposals", tags=["Proposals"], permissions=[IsAuthenticated])
class ProposalController(BaseAPI):
    """CRUD operations for project proposals."""

    @http_get(
        "/",
        response={200: list[ProposalListSchema], 401: ErrorSchema},
        url_name="proposals_list",
    )
    def list_proposals(
        self,
        request: HttpRequest,
        project_type: str | None = None,
        status: str | None = None,
        is_professor_proposal: bool | None = None,
        academic_year: str | None = None,
    ):
        """List proposals with filtering."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposals = Proposal.objects.annotate(
            apps_count=Count("applications")
        ).select_related("created_by", "supervisor")

        if project_type:
            proposals = proposals.filter(project_type=project_type)
        if status:
            proposals = proposals.filter(status=status)
        if is_professor_proposal is not None:
            proposals = proposals.filter(is_professor_proposal=is_professor_proposal)
        if academic_year:
            proposals = proposals.filter(academic_year=academic_year)

        proposals = proposals.order_by("-created")

        return 200, [proposal_to_list_schema(p, p.apps_count) for p in proposals]

    @http_get(
        "/incoming",
        response={200: list[ProposalListSchema], 401: ErrorSchema},
        url_name="proposals_incoming",
    )
    def incoming_proposals(self, request: HttpRequest, project_type: str | None = None):
        """Get open professor proposals (subjects waiting for students)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposals = Proposal.objects.filter(
            is_professor_proposal=True,
            status=ProposalStatus.OPEN,
        ).annotate(
            apps_count=Count("applications")
        ).select_related("created_by", "supervisor")

        if project_type:
            proposals = proposals.filter(project_type=project_type)

        proposals = proposals.order_by("-created")

        return 200, [proposal_to_list_schema(p, p.apps_count) for p in proposals]

    @http_get(
        "/in-development",
        response={200: list[ProposalListSchema], 401: ErrorSchema},
        url_name="proposals_in_development",
    )
    def in_development_proposals(self, request: HttpRequest, project_type: str | None = None):
        """Get proposals in development (student working on defining subject)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposals = Proposal.objects.filter(
            is_professor_proposal=False,
            status=ProposalStatus.IN_DEVELOPMENT,
        ).annotate(
            apps_count=Count("applications")
        ).select_related("created_by", "supervisor")

        if project_type:
            proposals = proposals.filter(project_type=project_type)

        proposals = proposals.order_by("-created")

        return 200, [proposal_to_list_schema(p, p.apps_count) for p in proposals]

    @http_get(
        "/my",
        response={200: list[ProposalListSchema], 401: ErrorSchema},
        url_name="proposals_my",
    )
    def my_proposals(self, request: HttpRequest):
        """Get proposals created by or supervised by current user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposals = Proposal.objects.filter(
            created_by=request.user
        ).annotate(
            apps_count=Count("applications")
        ).select_related("created_by", "supervisor").order_by("-created")

        return 200, [proposal_to_list_schema(p, p.apps_count) for p in proposals]

    @http_get(
        "/{proposal_id}",
        response={200: ProposalDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_detail",
    )
    def get_proposal(self, request: HttpRequest, proposal_id: UUID):
        """Get proposal details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(
            Proposal.objects.select_related("created_by", "supervisor").prefetch_related("applications__applicant"),
            id=proposal_id,
        )

        return 200, proposal_to_detail_schema(proposal)

    @http_post(
        "/",
        response={201: ProposalDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="proposals_create",
    )
    def create_proposal(self, request: HttpRequest, data: ProposalCreateSchema):
        """
        Create a new proposal.
        - Staff/professors create professor proposals (is_professor_proposal=True)
        - Students create in-development proposals (is_professor_proposal=False)
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Determine proposal type based on user role
        if data.is_professor_proposal:
            if not request.user.is_staff:
                return PermissionDeniedError("Seul le staff peut créer une proposition de professeur.").to_response()
            initial_status = ProposalStatus.OPEN
        else:
            # Student creating their own proposal
            initial_status = ProposalStatus.IN_DEVELOPMENT

        # Get supervisor if specified
        supervisor = None
        if data.supervisor_id:
            supervisor = User.objects.filter(id=data.supervisor_id).first()

        proposal = Proposal.objects.create(
            title=data.title,
            description=data.description,
            project_type=data.project_type,
            status=initial_status,
            created_by=request.user,
            supervisor=supervisor,
            academic_year=data.academic_year or get_current_academic_year(),
            is_professor_proposal=data.is_professor_proposal,
        )

        return 201, proposal_to_detail_schema(proposal)

    @http_put(
        "/{proposal_id}",
        response={200: ProposalDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_update",
    )
    def update_proposal(self, request: HttpRequest, proposal_id: UUID, data: ProposalUpdateSchema):
        """Update proposal. Only creator or staff."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous ne pouvez pas modifier cette proposition.").to_response()

        if data.title is not None:
            proposal.title = data.title
        if data.description is not None:
            proposal.description = data.description
        if data.supervisor_id is not None:
            proposal.supervisor = User.objects.filter(id=data.supervisor_id).first()

        proposal.save()

        proposal = Proposal.objects.select_related("created_by", "supervisor").prefetch_related("applications__applicant").get(id=proposal_id)

        return 200, proposal_to_detail_schema(proposal)

    @http_delete(
        "/{proposal_id}",
        response={200: MessageSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_delete",
    )
    def delete_proposal(self, request: HttpRequest, proposal_id: UUID):
        """Delete proposal. Only creator or staff, and only if not assigned."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous ne pouvez pas supprimer cette proposition.").to_response()

        if proposal.status == ProposalStatus.ASSIGNED:
            return BadRequestError("Impossible de supprimer une proposition déjà attribuée.").to_response()

        proposal.delete()

        return 200, MessageSchema(success=True, message="Proposition supprimée avec succès.")

    @http_post(
        "/{proposal_id}/apply",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_apply",
    )
    def apply_to_proposal(self, request: HttpRequest, proposal_id: UUID, data: ApplicationCreateSchema):
        """Student applies to an open proposal."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)

        if proposal.status != ProposalStatus.OPEN:
            return BadRequestError("Cette proposition n'est plus ouverte aux candidatures.").to_response()

        if not proposal.is_professor_proposal:
            return BadRequestError("Vous ne pouvez candidater qu'aux propositions de professeurs.").to_response()

        try:
            ProposalApplication.objects.create(
                proposal=proposal,
                applicant=request.user,
                motivation=data.motivation,
            )
        except IntegrityError:
            return AlreadyExistsError("Vous avez déjà candidaté à cette proposition.").to_response()

        return 200, MessageSchema(success=True, message="Candidature envoyée avec succès.")

    @http_get(
        "/{proposal_id}/applications",
        response={200: list[ApplicationSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_applications_list",
    )
    def list_applications(self, request: HttpRequest, proposal_id: UUID):
        """List applications for a proposal. Only creator/supervisor/staff."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous n'avez pas accès aux candidatures.").to_response()

        applications = proposal.applications.select_related("applicant").order_by("-created")

        return 200, [application_to_schema(app) for app in applications]

    @http_post(
        "/{proposal_id}/applications/{application_id}/accept",
        response={200: ProposalDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_applications_accept",
    )
    def accept_application(self, request: HttpRequest, proposal_id: UUID, application_id: UUID):
        """Accept an application. Updates proposal status to ASSIGNED."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)
        application = get_object_or_404(ProposalApplication, id=application_id, proposal=proposal)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous ne pouvez pas gérer les candidatures.").to_response()

        if proposal.status != ProposalStatus.OPEN:
            return BadRequestError("Cette proposition n'est plus ouverte.").to_response()

        # Accept the application
        application.status = ApplicationStatus.ACCEPTED
        application.save()

        # Reject all other applications
        proposal.applications.exclude(id=application_id).update(status=ApplicationStatus.REJECTED)

        # Update proposal status
        proposal.status = ProposalStatus.ASSIGNED
        proposal.save()

        proposal = Proposal.objects.select_related("created_by", "supervisor").prefetch_related("applications__applicant").get(id=proposal_id)

        return 200, proposal_to_detail_schema(proposal)

    @http_post(
        "/{proposal_id}/applications/{application_id}/reject",
        response={200: ApplicationSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_applications_reject",
    )
    def reject_application(self, request: HttpRequest, proposal_id: UUID, application_id: UUID):
        """Reject an application."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)
        application = get_object_or_404(ProposalApplication, id=application_id, proposal=proposal)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous ne pouvez pas gérer les candidatures.").to_response()

        application.status = ApplicationStatus.REJECTED
        application.save()

        return 200, application_to_schema(application)

    @http_post(
        "/{proposal_id}/convert",
        response={201: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="proposals_convert",
    )
    def convert_to_project(self, request: HttpRequest, proposal_id: UUID):
        """
        Convert proposal to an active project.
        For professor proposals: must be assigned (have an accepted application).
        For student proposals: creates project with the student as owner.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        proposal = get_object_or_404(Proposal, id=proposal_id)

        if not proposal.can_be_managed_by(request.user):
            return PermissionDeniedError("Vous ne pouvez pas convertir cette proposition.").to_response()

        if proposal.resulting_project:
            return BadRequestError("Cette proposition a déjà été convertie en projet.").to_response()

        # Determine the student
        if proposal.is_professor_proposal:
            # Must have an accepted application
            accepted_app = proposal.applications.filter(status=ApplicationStatus.ACCEPTED).first()
            if not accepted_app:
                return BadRequestError("Aucune candidature acceptée. Acceptez une candidature avant de convertir.").to_response()
            student = accepted_app.applicant
        else:
            # Student's own proposal
            student = proposal.created_by

        # Create the project
        project = AcademicProject.objects.create(
            student=student,
            supervisor=proposal.supervisor,
            subject=proposal.title,
            description=proposal.description,
            project_type=proposal.project_type,
            academic_year=proposal.academic_year,
            status=AcademicProjectStatus.PENDING,
            start_date=proposal.created.date(),
            end_date=proposal.created.date(),  # Will need to be updated
        )

        # Link proposal to project
        proposal.resulting_project = project
        proposal.status = ProposalStatus.CLOSED
        proposal.save()

        return 201, MessageSchema(
            success=True,
            message=f"Projet créé avec succès (ID: {project.id}).",
        )
