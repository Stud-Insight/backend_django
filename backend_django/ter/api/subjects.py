"""
TER Subjects API controller.
"""

from uuid import UUID

from django.db import models
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
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
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERFavorite, TERPeriod, TERSubject
from backend_django.ter.schemas.subjects import (
    TERFavoriteSchema,
    TERSubjectCreateSchema,
    TERSubjectDetailSchema,
    TERSubjectListSchema,
    TERSubjectRejectSchema,
    TERSubjectUpdateSchema,
    UserMinimalSchema,
)
from backend_django.users.models import User


# ==================== Helper Functions ====================


def user_to_minimal_schema(user: User | None) -> UserMinimalSchema | None:
    """Convert User to minimal schema."""
    if not user:
        return None
    return UserMinimalSchema(
        id=user.id,
        email=user.email,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )


def subject_to_list_schema(subject: TERSubject) -> TERSubjectListSchema:
    """Convert TERSubject to list schema."""
    return TERSubjectListSchema(
        id=subject.id,
        title=subject.title,
        domain=subject.domain,
        professor=user_to_minimal_schema(subject.professor),
        status=subject.status,
        max_groups=subject.max_groups,
        ter_period_id=subject.ter_period_id,
        created=str(subject.created),
    )


def subject_to_detail_schema(subject: TERSubject, is_favorite: bool = False) -> TERSubjectDetailSchema:
    """Convert TERSubject to detailed schema."""
    return TERSubjectDetailSchema(
        id=subject.id,
        title=subject.title,
        description=subject.description,
        domain=subject.domain,
        prerequisites=subject.prerequisites,
        professor=user_to_minimal_schema(subject.professor),
        supervisor=user_to_minimal_schema(subject.supervisor),
        max_groups=subject.max_groups,
        status=subject.status,
        rejection_reason=subject.rejection_reason,
        ter_period_id=subject.ter_period_id,
        created=str(subject.created),
        modified=str(subject.modified),
        is_favorite=is_favorite,
    )


# ==================== TER Subjects Controller ====================


@api_controller("/ter/subjects", tags=["TER Subjects"], permissions=[IsAuthenticated])
class TERSubjectController(BaseAPI):
    """API for TER subjects."""

    @http_get(
        "/",
        response={200: list[TERSubjectListSchema], 401: ErrorSchema},
        url_name="ter_subjects_list",
    )
    def list_subjects(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
        status: str | None = None,
        domain: str | None = None,
    ):
        """
        List TER subjects.

        Optional filters:
        - ter_period_id: Filter by TER period
        - status: Filter by status (draft, submitted, validated, rejected)
        - domain: Filter by domain
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        subjects = TERSubject.objects.select_related("professor", "ter_period").all()

        # Non-staff users only see validated subjects (and their own drafts/submitted)
        if not is_ter_admin(request.user):
            subjects = subjects.filter(
                models.Q(status=SubjectStatus.VALIDATED) |
                models.Q(professor=request.user)
            )
        elif status:
            subjects = subjects.filter(status=status)

        if ter_period_id:
            subjects = subjects.filter(ter_period_id=ter_period_id)

        if domain:
            subjects = subjects.filter(domain__icontains=domain)

        subjects = subjects.order_by("-created")

        return 200, [subject_to_list_schema(s) for s in subjects]

    @http_get(
        "/{subject_id}",
        response={200: TERSubjectDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_detail",
    )
    def get_subject(self, request: HttpRequest, subject_id: UUID):
        """Get TER subject details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        subject = get_object_or_404(
            TERSubject.objects.select_related("professor", "supervisor", "ter_period"),
            id=subject_id
        )

        # Non-staff/non-owners can only see validated subjects
        if not is_ter_admin(request.user) and not subject.can_be_managed_by(request.user):
            if subject.status != SubjectStatus.VALIDATED:
                return NotFoundError("Sujet TER non trouve.").to_response()

        # Check if user has favorited this subject
        is_favorite = TERFavorite.objects.filter(
            student=request.user,
            subject=subject,
        ).exists()

        return 200, subject_to_detail_schema(subject, is_favorite=is_favorite)

    @http_post(
        "/",
        response={201: TERSubjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="ter_subjects_create",
    )
    def create_subject(self, request: HttpRequest, data: TERSubjectCreateSchema):
        """
        Create a new TER subject.

        Professors and staff can create subjects.
        New subjects are created with status 'draft'.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Check TER period exists and is open
        ter_period = get_object_or_404(TERPeriod, id=data.ter_period_id)
        if ter_period.status != PeriodStatus.OPEN and not is_ter_admin(request.user):
            return BadRequestError(
                "La periode TER n'est pas ouverte."
            ).to_response()

        # Validate supervisor if provided
        supervisor = None
        if data.supervisor_id:
            supervisor = get_object_or_404(User, id=data.supervisor_id)

        subject = TERSubject.objects.create(
            ter_period=ter_period,
            title=data.title,
            description=data.description,
            domain=data.domain,
            prerequisites=data.prerequisites,
            professor=request.user,
            supervisor=supervisor,
            max_groups=data.max_groups,
            status=SubjectStatus.DRAFT,
        )

        return 201, subject_to_detail_schema(subject)

    @http_put(
        "/{subject_id}",
        response={200: TERSubjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_update",
    )
    def update_subject(
        self, request: HttpRequest, subject_id: UUID, data: TERSubjectUpdateSchema
    ):
        """
        Update a TER subject.

        Only owner/staff can update. Only draft/rejected subjects can be edited.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        subject = get_object_or_404(TERSubject, id=subject_id)

        if not subject.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour modifier ce sujet."
            ).to_response()

        # Only draft or rejected subjects can be edited
        if subject.status not in [SubjectStatus.DRAFT, SubjectStatus.REJECTED]:
            return BadRequestError(
                "Seuls les sujets en brouillon ou rejetes peuvent etre modifies."
            ).to_response()

        if data.title is not None:
            subject.title = data.title
        if data.description is not None:
            subject.description = data.description
        if data.domain is not None:
            subject.domain = data.domain
        if data.prerequisites is not None:
            subject.prerequisites = data.prerequisites
        if data.supervisor_id is not None:
            subject.supervisor = get_object_or_404(User, id=data.supervisor_id)
        if data.max_groups is not None:
            subject.max_groups = data.max_groups

        # Reset to draft if was rejected
        if subject.status == SubjectStatus.REJECTED:
            subject.status = SubjectStatus.DRAFT
            subject.rejection_reason = ""

        subject.save()

        return 200, subject_to_detail_schema(subject)

    @http_post(
        "/{subject_id}/submit",
        response={200: TERSubjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_submit",
    )
    def submit_subject(self, request: HttpRequest, subject_id: UUID):
        """
        Submit a TER subject for validation.

        Transitions from draft to submitted.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        subject = get_object_or_404(TERSubject, id=subject_id)

        if not subject.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour soumettre ce sujet."
            ).to_response()

        if subject.status != SubjectStatus.DRAFT:
            return BadRequestError(
                f"Impossible de soumettre un sujet avec le statut '{subject.status}'."
            ).to_response()

        subject.status = SubjectStatus.SUBMITTED
        subject.save()

        return 200, subject_to_detail_schema(subject)

    @http_post(
        "/{subject_id}/validate",
        response={200: TERSubjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_validate",
    )
    def validate_subject(self, request: HttpRequest, subject_id: UUID):
        """
        Validate a TER subject.

        Only staff (Respo TER) can validate subjects.
        Transitions from submitted to validated.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent valider des sujets."
            ).to_response()

        subject = get_object_or_404(TERSubject, id=subject_id)

        if subject.status != SubjectStatus.SUBMITTED:
            return BadRequestError(
                f"Impossible de valider un sujet avec le statut '{subject.status}'."
            ).to_response()

        subject.status = SubjectStatus.VALIDATED
        subject.save()

        return 200, subject_to_detail_schema(subject)

    @http_post(
        "/{subject_id}/reject",
        response={200: TERSubjectDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_reject",
    )
    def reject_subject(self, request: HttpRequest, subject_id: UUID, data: TERSubjectRejectSchema):
        """
        Reject a TER subject.

        Only staff (Respo TER) can reject subjects.
        Requires a reason for rejection.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent rejeter des sujets."
            ).to_response()

        subject = get_object_or_404(TERSubject, id=subject_id)

        if subject.status != SubjectStatus.SUBMITTED:
            return BadRequestError(
                f"Impossible de rejeter un sujet avec le statut '{subject.status}'."
            ).to_response()

        subject.status = SubjectStatus.REJECTED
        subject.rejection_reason = data.reason
        subject.save()

        return 200, subject_to_detail_schema(subject)

    @http_post(
        "/{subject_id}/favorite",
        response={201: TERFavoriteSchema, 400: ErrorSchema, 401: ErrorSchema, 404: ErrorSchema, 409: ErrorSchema},
        url_name="ter_subjects_add_favorite",
    )
    def add_favorite(self, request: HttpRequest, subject_id: UUID):
        """
        Add a TER subject to favorites.

        Students can mark validated subjects as favorites.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        subject = get_object_or_404(TERSubject, id=subject_id)

        # Only validated subjects can be favorited
        if subject.status != SubjectStatus.VALIDATED:
            return BadRequestError(
                "Seuls les sujets valides peuvent etre mis en favoris."
            ).to_response()

        # Check if already favorited
        if TERFavorite.objects.filter(student=request.user, subject=subject).exists():
            return 409, {"message": "Ce sujet est deja dans vos favoris."}

        favorite = TERFavorite.objects.create(
            student=request.user,
            subject=subject,
        )

        return 201, TERFavoriteSchema(
            id=favorite.id,
            student_id=favorite.student_id,
            subject_id=favorite.subject_id,
            created=str(favorite.created),
        )

    @http_delete(
        "/{subject_id}/favorite",
        response={204: None, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_subjects_remove_favorite",
    )
    def remove_favorite(self, request: HttpRequest, subject_id: UUID):
        """
        Remove a TER subject from favorites.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        favorite = get_object_or_404(
            TERFavorite,
            student=request.user,
            subject_id=subject_id,
        )

        favorite.delete()

        return 204, None
