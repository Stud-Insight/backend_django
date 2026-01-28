"""
Stage Periods API controller.
"""

from datetime import timedelta
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get, http_post, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_stage_admin
from backend_django.stages.models import PeriodStatus, StagePeriod
from backend_django.stages.schemas.periods import (
    StagePeriodCreateSchema,
    StagePeriodDetailSchema,
    StagePeriodSchema,
    StagePeriodUpdateSchema,
)


# ==================== Helper Functions ====================


def stage_period_to_schema(period: StagePeriod) -> StagePeriodSchema:
    """Convert StagePeriod to basic schema."""
    return StagePeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        application_start=str(period.application_start),
        application_end=str(period.application_end),
    )


def stage_period_to_detail_schema(period: StagePeriod) -> StagePeriodDetailSchema:
    """Convert StagePeriod to detailed schema."""
    return StagePeriodDetailSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        offer_submission_start=str(period.offer_submission_start),
        offer_submission_end=str(period.offer_submission_end),
        application_start=str(period.application_start),
        application_end=str(period.application_end),
        internship_start=str(period.internship_start),
        internship_end=str(period.internship_end),
        created=str(period.created),
        modified=str(period.modified),
    )


# ==================== Stage Periods Controller ====================


@api_controller("/stages/periods", tags=["Stage Periods"], permissions=[IsAuthenticated])
class StagePeriodController(BaseAPI):
    """API for Stage (internship) periods."""

    @http_get(
        "/",
        response={200: list[StagePeriodSchema], 401: ErrorSchema},
        url_name="stage_periods_list",
    )
    def list_stage_periods(
        self,
        request: HttpRequest,
        status: str | None = None,
        academic_year: str | None = None,
    ):
        """
        List Stage periods.

        Optional filters:
        - status: Filter by period status (draft, open, closed, archived)
        - academic_year: Filter by academic year (e.g., "2024-2025")
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        periods = StagePeriod.objects.all()

        # Non-staff users only see open periods
        if not is_stage_admin(request.user):
            periods = periods.filter(status=PeriodStatus.OPEN)
        elif status:
            periods = periods.filter(status=status)

        if academic_year:
            periods = periods.filter(academic_year=academic_year)

        periods = periods.order_by("-academic_year", "-created")

        return 200, [stage_period_to_schema(p) for p in periods]

    @http_get(
        "/{period_id}",
        response={200: StagePeriodDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="stage_periods_detail",
    )
    def get_stage_period(self, request: HttpRequest, period_id: UUID):
        """Get Stage period details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        # Non-admin users can only see open periods
        if not is_stage_admin(request.user) and period.status != PeriodStatus.OPEN:
            return NotFoundError("Periode Stage non trouvee.").to_response()

        return 200, stage_period_to_detail_schema(period)

    @http_post(
        "/",
        response={201: StagePeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="stage_periods_create",
    )
    def create_stage_period(self, request: HttpRequest, data: StagePeriodCreateSchema):
        """
        Create a new Stage period.

        Only staff members (Respo Stage) can create periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent creer des periodes."
            ).to_response()

        # Check for duplicate
        if StagePeriod.objects.filter(
            name=data.name,
            academic_year=data.academic_year,
        ).exists():
            return BadRequestError(
                "Une periode avec ce nom existe deja pour cette annee academique."
            ).to_response()

        period = StagePeriod.objects.create(
            name=data.name,
            academic_year=data.academic_year,
            status=PeriodStatus.DRAFT,
            offer_submission_start=data.offer_submission_start,
            offer_submission_end=data.offer_submission_end,
            application_start=data.application_start,
            application_end=data.application_end,
            internship_start=data.internship_start,
            internship_end=data.internship_end,
        )

        return 201, stage_period_to_detail_schema(period)

    @http_put(
        "/{period_id}",
        response={200: StagePeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_periods_update",
    )
    def update_stage_period(
        self, request: HttpRequest, period_id: UUID, data: StagePeriodUpdateSchema
    ):
        """
        Update a Stage period.

        Only staff members can update periods.
        Only draft periods can be fully edited.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent modifier des periodes."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        if period.status != PeriodStatus.DRAFT:
            return BadRequestError(
                "Seules les periodes en brouillon peuvent etre modifiees."
            ).to_response()

        if data.name is not None:
            period.name = data.name
        if data.offer_submission_start is not None:
            period.offer_submission_start = data.offer_submission_start
        if data.offer_submission_end is not None:
            period.offer_submission_end = data.offer_submission_end
        if data.application_start is not None:
            period.application_start = data.application_start
        if data.application_end is not None:
            period.application_end = data.application_end
        if data.internship_start is not None:
            period.internship_start = data.internship_start
        if data.internship_end is not None:
            period.internship_end = data.internship_end

        period.save()

        return 200, stage_period_to_detail_schema(period)

    @http_post(
        "/{period_id}/open",
        response={200: StagePeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_periods_open",
    )
    def open_stage_period(self, request: HttpRequest, period_id: UUID):
        """
        Open a Stage period (transition from draft to open).

        Only staff members can open periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent ouvrir des periodes."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        if period.status != PeriodStatus.DRAFT:
            return BadRequestError(
                f"Impossible d'ouvrir une periode avec le statut '{period.status}'."
            ).to_response()

        period.status = PeriodStatus.OPEN
        period.save()

        return 200, stage_period_to_detail_schema(period)

    @http_post(
        "/{period_id}/close",
        response={200: StagePeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_periods_close",
    )
    def close_stage_period(self, request: HttpRequest, period_id: UUID):
        """
        Close a Stage period (transition from open to closed).

        Only staff members can close periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent cloturer des periodes."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        if period.status != PeriodStatus.OPEN:
            return BadRequestError(
                f"Impossible de cloturer une periode avec le statut '{period.status}'."
            ).to_response()

        period.status = PeriodStatus.CLOSED
        period.save()

        return 200, stage_period_to_detail_schema(period)
