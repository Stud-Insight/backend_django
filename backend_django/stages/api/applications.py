"""
Stage Applications API controller.

Handles student applications to stage offers:
- Apply to offer (5.5)
- Multiple applications (5.6)
- View applications as externe/supervisor (5.7)
- Accept/reject applications (5.8)
- Confirm assignment (5.9)
- Auto-withdraw pending applications after confirmation
"""

from datetime import date
from uuid import UUID

from django.db import models, transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja_extra import api_controller, http_delete, http_get, http_post

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_stage_admin, user_has_role, Role
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    PeriodStatus,
    StageApplication,
    StageOffer,
)
from backend_django.stages.schemas.applications import (
    ApplicationCountSchema,
    StageApplicationConfirmSchema,
    StageApplicationCreateSchema,
    StageApplicationDetailSchema,
    StageApplicationListSchema,
    StageApplicationRejectSchema,
    SuccessSchema,
)
from backend_django.users.models import User


# ==================== Helper Functions ====================


def user_to_minimal_schema(user: User | None) -> dict | None:
    """Convert User to minimal schema dict."""
    if not user:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
    }


def application_to_list_schema(app: StageApplication) -> StageApplicationListSchema:
    """Convert StageApplication to list schema."""
    return StageApplicationListSchema(
        id=app.id,
        student=user_to_minimal_schema(app.student),
        offer_id=app.offer_id,
        offer_title=app.offer.title,
        company_name=app.offer.company_name,
        status=app.status,
        created=str(app.created),
    )


def application_to_detail_schema(app: StageApplication) -> StageApplicationDetailSchema:
    """Convert StageApplication to detailed schema."""
    return StageApplicationDetailSchema(
        id=app.id,
        student=user_to_minimal_schema(app.student),
        offer_id=app.offer_id,
        offer_title=app.offer.title,
        company_name=app.offer.company_name,
        status=app.status,
        motivation=app.motivation,
        cv_url=app.cv_url,
        decision_date=app.decision_date,
        decision_by=user_to_minimal_schema(app.decision_by),
        rejection_reason=app.rejection_reason,
        confirmed_at=app.confirmed_at,
        academic_supervisor=user_to_minimal_schema(app.academic_supervisor),
        created=str(app.created),
        modified=str(app.modified),
    )


def is_within_application_period(offer: StageOffer) -> bool:
    """Check if current date is within application period."""
    today = date.today()
    period = offer.stage_period
    return period.application_start <= today <= period.application_end


# ==================== Applications Controller ====================


@api_controller("/stages/applications", tags=["Stage Applications"], permissions=[IsAuthenticated])
class StageApplicationController(BaseAPI):
    """API for Stage applications."""

    @http_get(
        "/my-applications",
        response={200: list[StageApplicationListSchema], 401: ErrorSchema},
        url_name="stage_my_applications",
    )
    def list_my_applications(
        self,
        request: HttpRequest,
        stage_period_id: UUID | None = None,
        status: str | None = None,
    ):
        """
        List current user's applications.

        Optional filters:
        - stage_period_id: Filter by stage period
        - status: Filter by status (pending, accepted, rejected, withdrawn, confirmed)
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        applications = StageApplication.objects.filter(
            student=request.user
        ).select_related("offer", "offer__stage_period")

        if stage_period_id:
            applications = applications.filter(offer__stage_period_id=stage_period_id)

        if status:
            applications = applications.filter(status=status)

        applications = applications.order_by("-created")

        return 200, [application_to_list_schema(a) for a in applications]

    @http_get(
        "/{application_id}",
        response={200: StageApplicationDetailSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_application_detail",
    )
    def get_application(self, request: HttpRequest, application_id: UUID):
        """
        Get application details.

        Accessible by: applicant, offer supervisor, or staff.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related(
                "student", "offer", "decision_by", "academic_supervisor"
            ),
            id=application_id,
        )

        # Check access
        is_applicant = application.student_id == request.user.id
        is_supervisor = application.offer.supervisor_id == request.user.id
        is_admin = is_stage_admin(request.user)

        if not (is_applicant or is_supervisor or is_admin):
            return PermissionDeniedError(
                "Vous n'avez pas acces a cette candidature."
            ).to_response()

        return 200, application_to_detail_schema(application)

    @http_post(
        "/{application_id}/withdraw",
        response={200: SuccessSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_application_withdraw",
    )
    def withdraw_application(self, request: HttpRequest, application_id: UUID):
        """
        Withdraw an application.

        Only the applicant can withdraw, and only while pending.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(StageApplication, id=application_id)

        if not application.can_be_withdrawn_by(request.user):
            if application.student_id != request.user.id:
                return PermissionDeniedError(
                    "Vous ne pouvez pas retirer cette candidature."
                ).to_response()
            return BadRequestError(
                "Seules les candidatures en attente peuvent etre retirees."
            ).to_response()

        application.status = ApplicationStatus.WITHDRAWN
        application.save()

        return 200, SuccessSchema(
            success=True,
            message="Candidature retiree avec succes.",
        )


# ==================== Offer Applications Controller ====================


@api_controller("/stages/offers", tags=["Stage Applications"], permissions=[IsAuthenticated])
class StageOfferApplicationController(BaseAPI):
    """API for applications on specific offers."""

    @http_post(
        "/{offer_id}/apply",
        response={201: StageApplicationDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema, 409: ErrorSchema},
        url_name="stage_offer_apply",
    )
    def apply_to_offer(
        self, request: HttpRequest, offer_id: UUID, data: StageApplicationCreateSchema
    ):
        """
        Apply to a stage offer (5.5).

        Students can apply to validated offers during the application period.
        Students can apply to multiple offers (5.6).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Only students can apply
        if not user_has_role(request.user, Role.ETUDIANT):
            return PermissionDeniedError(
                "Seuls les etudiants peuvent postuler aux offres de stage."
            ).to_response()

        offer = get_object_or_404(
            StageOffer.objects.select_related("stage_period"),
            id=offer_id,
        )

        # Check offer is validated
        if offer.status != OfferStatus.VALIDATED:
            return BadRequestError(
                "Cette offre n'est pas disponible pour les candidatures."
            ).to_response()

        # Check period is open
        if offer.stage_period.status != PeriodStatus.OPEN:
            return BadRequestError(
                "La periode de stage n'est pas ouverte."
            ).to_response()

        # Check within application period (unless admin)
        if not is_stage_admin(request.user) and not is_within_application_period(offer):
            return BadRequestError(
                "La periode de candidature est terminee."
            ).to_response()

        # Check user hasn't already applied
        if StageApplication.objects.filter(student=request.user, offer=offer).exists():
            return 409, ErrorSchema(
                code="ALREADY_APPLIED",
                message="Vous avez deja postule a cette offre.",
            )

        # Check user doesn't have a confirmed application in this period
        if StageApplication.objects.filter(
            student=request.user,
            offer__stage_period=offer.stage_period,
            status=ApplicationStatus.CONFIRMED,
        ).exists():
            return BadRequestError(
                "Vous avez deja confirme un stage pour cette periode."
            ).to_response()

        # Create application
        application = StageApplication.objects.create(
            student=request.user,
            offer=offer,
            motivation=data.motivation,
            cv_url=data.cv_url,
            status=ApplicationStatus.PENDING,
        )

        return 201, application_to_detail_schema(application)

    @http_get(
        "/{offer_id}/applications",
        response={200: list[StageApplicationListSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offer_applications",
    )
    def list_offer_applications(
        self,
        request: HttpRequest,
        offer_id: UUID,
        status: str | None = None,
    ):
        """
        List applications for an offer (5.7).

        Only accessible by offer supervisor or staff.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        # Check access
        is_supervisor = offer.supervisor_id == request.user.id
        is_admin = is_stage_admin(request.user)

        if not (is_supervisor or is_admin):
            return PermissionDeniedError(
                "Seul le superviseur peut voir les candidatures."
            ).to_response()

        applications = StageApplication.objects.filter(
            offer=offer
        ).select_related("student").order_by("-created")

        if status:
            applications = applications.filter(status=status)

        return 200, [application_to_list_schema(a) for a in applications]

    @http_get(
        "/{offer_id}/applications/count",
        response={200: ApplicationCountSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offer_applications_count",
    )
    def count_offer_applications(self, request: HttpRequest, offer_id: UUID):
        """
        Get application counts for an offer.

        Only accessible by offer supervisor or staff.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        # Check access
        is_supervisor = offer.supervisor_id == request.user.id
        is_admin = is_stage_admin(request.user)

        if not (is_supervisor or is_admin):
            return PermissionDeniedError(
                "Seul le superviseur peut voir les statistiques."
            ).to_response()

        applications = StageApplication.objects.filter(offer=offer)

        return 200, ApplicationCountSchema(
            offer_id=offer.id,
            total=applications.count(),
            pending=applications.filter(status=ApplicationStatus.PENDING).count(),
            accepted=applications.filter(status=ApplicationStatus.ACCEPTED).count(),
            rejected=applications.filter(status=ApplicationStatus.REJECTED).count(),
            confirmed=applications.filter(status=ApplicationStatus.CONFIRMED).count(),
        )

    @http_post(
        "/{offer_id}/applications/{application_id}/accept",
        response={200: StageApplicationDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_application_accept",
    )
    def accept_application(
        self, request: HttpRequest, offer_id: UUID, application_id: UUID
    ):
        """
        Accept an application (5.8).

        Only the offer supervisor or staff can accept.
        Only pending applications can be accepted.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related("offer", "student"),
            id=application_id,
            offer_id=offer_id,
        )

        if not application.can_be_decided_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour accepter cette candidature."
            ).to_response()

        if application.status != ApplicationStatus.PENDING:
            return BadRequestError(
                f"Impossible d'accepter une candidature avec le statut '{application.status}'."
            ).to_response()

        # Check max_students not exceeded
        accepted_count = StageApplication.objects.filter(
            offer=application.offer,
            status__in=[ApplicationStatus.ACCEPTED, ApplicationStatus.CONFIRMED],
        ).count()

        if accepted_count >= application.offer.max_students:
            return BadRequestError(
                f"Le nombre maximum d'etudiants ({application.offer.max_students}) est deja atteint."
            ).to_response()

        application.status = ApplicationStatus.ACCEPTED
        application.decision_date = timezone.now()
        application.decision_by = request.user
        application.save()

        return 200, application_to_detail_schema(application)

    @http_post(
        "/{offer_id}/applications/{application_id}/reject",
        response={200: StageApplicationDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_application_reject",
    )
    def reject_application(
        self,
        request: HttpRequest,
        offer_id: UUID,
        application_id: UUID,
        data: StageApplicationRejectSchema,
    ):
        """
        Reject an application (5.8).

        Only the offer supervisor or staff can reject.
        Requires a rejection reason.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related("offer", "student"),
            id=application_id,
            offer_id=offer_id,
        )

        if not application.can_be_decided_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour rejeter cette candidature."
            ).to_response()

        if application.status != ApplicationStatus.PENDING:
            return BadRequestError(
                f"Impossible de rejeter une candidature avec le statut '{application.status}'."
            ).to_response()

        application.status = ApplicationStatus.REJECTED
        application.decision_date = timezone.now()
        application.decision_by = request.user
        application.rejection_reason = data.reason
        application.save()

        # TODO: 5.10 - Notify rejected applicant (blocked by Epic 7)

        return 200, application_to_detail_schema(application)

    @http_post(
        "/{offer_id}/applications/{application_id}/confirm",
        response={200: StageApplicationDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_application_confirm",
    )
    def confirm_application(
        self,
        request: HttpRequest,
        offer_id: UUID,
        application_id: UUID,
        data: StageApplicationConfirmSchema | None = None,
    ):
        """
        Confirm an accepted application (5.9).

        Only the applicant can confirm.
        This assigns the stage and auto-withdraws other pending applications.
        Optionally assigns an academic supervisor.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related("offer", "student"),
            id=application_id,
            offer_id=offer_id,
        )

        if not application.can_be_confirmed_by(request.user):
            if application.student_id != request.user.id:
                return PermissionDeniedError(
                    "Vous ne pouvez pas confirmer cette candidature."
                ).to_response()
            return BadRequestError(
                "Seules les candidatures acceptees peuvent etre confirmees."
            ).to_response()

        # Check user doesn't already have a confirmed application in this period
        if StageApplication.objects.filter(
            student=request.user,
            offer__stage_period=application.offer.stage_period,
            status=ApplicationStatus.CONFIRMED,
        ).exists():
            return BadRequestError(
                "Vous avez deja confirme un stage pour cette periode."
            ).to_response()

        # Set academic supervisor if provided
        academic_supervisor = None
        if data and data.academic_supervisor_id:
            academic_supervisor = get_object_or_404(User, id=data.academic_supervisor_id)
            # Verify supervisor is an Encadrant
            if not user_has_role(academic_supervisor, Role.ENCADRANT):
                return BadRequestError(
                    "L'encadrant academique selectionne n'est pas un enseignant."
                ).to_response()

        with transaction.atomic():
            # Confirm this application
            application.status = ApplicationStatus.CONFIRMED
            application.confirmed_at = timezone.now()
            if academic_supervisor:
                application.academic_supervisor = academic_supervisor
            application.save()

            # Auto-withdraw other pending applications for same student in same period
            withdrawn_count = StageApplication.objects.filter(
                student=request.user,
                offer__stage_period=application.offer.stage_period,
                status=ApplicationStatus.PENDING,
            ).exclude(id=application.id).update(status=ApplicationStatus.WITHDRAWN)

        return 200, application_to_detail_schema(application)
