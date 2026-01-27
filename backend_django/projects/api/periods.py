"""
Periods API controller for TER and Stage periods.
"""

from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import ErrorSchema, NotAuthenticatedError, NotFoundError
from backend_django.projects.models import PeriodStatus, TERPeriod, StagePeriod
from backend_django.projects.schemas.groups import TERPeriodSchema, StagePeriodSchema


def ter_period_to_schema(period: TERPeriod) -> TERPeriodSchema:
    """Convert TERPeriod to schema."""
    return TERPeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        group_formation_start=str(period.group_formation_start),
        group_formation_end=str(period.group_formation_end),
        min_group_size=period.min_group_size,
        max_group_size=period.max_group_size,
    )


def stage_period_to_schema(period: StagePeriod) -> StagePeriodSchema:
    """Convert StagePeriod to schema."""
    return StagePeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        application_start=str(period.application_start),
        application_end=str(period.application_end),
    )


@api_controller("/ter-periods", tags=["TER Periods"], permissions=[IsAuthenticated])
class TERPeriodController(BaseAPI):
    """API for TER periods."""

    @http_get(
        "/",
        response={200: list[TERPeriodSchema], 401: ErrorSchema},
        url_name="ter_periods_list",
    )
    def list_ter_periods(
        self,
        request: HttpRequest,
        status: str | None = None,
        academic_year: str | None = None,
    ):
        """
        List TER periods.

        Optional filters:
        - status: Filter by period status (draft, open, closed, archived)
        - academic_year: Filter by academic year (e.g., "2024-2025")
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        periods = TERPeriod.objects.all()

        # Non-staff users only see open periods
        if not request.user.is_staff:
            periods = periods.filter(status=PeriodStatus.OPEN)
        elif status:
            periods = periods.filter(status=status)

        if academic_year:
            periods = periods.filter(academic_year=academic_year)

        periods = periods.order_by("-academic_year", "-created")

        return 200, [ter_period_to_schema(p) for p in periods]

    @http_get(
        "/{period_id}",
        response={200: TERPeriodSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_detail",
    )
    def get_ter_period(self, request: HttpRequest, period_id: UUID):
        """Get TER period details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Non-staff users can only see open periods
        if not request.user.is_staff and period.status != PeriodStatus.OPEN:
            return NotFoundError("Période TER non trouvée.").to_response()

        return 200, ter_period_to_schema(period)


@api_controller("/stage-periods", tags=["Stage Periods"], permissions=[IsAuthenticated])
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
        if not request.user.is_staff:
            periods = periods.filter(status=PeriodStatus.OPEN)
        elif status:
            periods = periods.filter(status=status)

        if academic_year:
            periods = periods.filter(academic_year=academic_year)

        periods = periods.order_by("-academic_year", "-created")

        return 200, [stage_period_to_schema(p) for p in periods]

    @http_get(
        "/{period_id}",
        response={200: StagePeriodSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="stage_periods_detail",
    )
    def get_stage_period(self, request: HttpRequest, period_id: UUID):
        """Get Stage period details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        # Non-staff users can only see open periods
        if not request.user.is_staff and period.status != PeriodStatus.OPEN:
            return NotFoundError("Période Stage non trouvée.").to_response()

        return 200, stage_period_to_schema(period)
