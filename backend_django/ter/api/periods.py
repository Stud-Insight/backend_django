"""
TER Periods API controller.
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
from backend_django.groups.models import Group
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.ter.schemas.periods import (
    TERPeriodCopySchema,
    TERPeriodCreateSchema,
    TERPeriodDetailSchema,
    TERPeriodSchema,
    TERPeriodStatsSchema,
    TERPeriodUpdateSchema,
)
from backend_django.users.models import User


# ==================== Helper Functions ====================


def ter_period_to_schema(period: TERPeriod) -> TERPeriodSchema:
    """Convert TERPeriod to basic schema."""
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


def ter_period_to_detail_schema(period: TERPeriod) -> TERPeriodDetailSchema:
    """Convert TERPeriod to detailed schema."""
    return TERPeriodDetailSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        group_formation_start=str(period.group_formation_start),
        group_formation_end=str(period.group_formation_end),
        subject_selection_start=str(period.subject_selection_start),
        subject_selection_end=str(period.subject_selection_end),
        assignment_date=str(period.assignment_date),
        project_start=str(period.project_start),
        project_end=str(period.project_end),
        min_group_size=period.min_group_size,
        max_group_size=period.max_group_size,
        created=str(period.created),
        modified=str(period.modified),
    )


# ==================== TER Periods Controller ====================


@api_controller("/ter/periods", tags=["TER Periods"], permissions=[IsAuthenticated])
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

        if not request.user.is_staff:
            # Non-staff users only see periods where they are enrolled
            periods = periods.filter(
                enrolled_students=request.user,
                status=PeriodStatus.OPEN,
            )
        elif status:
            periods = periods.filter(status=status)

        if academic_year:
            periods = periods.filter(academic_year=academic_year)

        periods = periods.order_by("-academic_year", "-created")

        return 200, [ter_period_to_schema(p) for p in periods]

    @http_get(
        "/{period_id}",
        response={200: TERPeriodDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_detail",
    )
    def get_ter_period(self, request: HttpRequest, period_id: UUID):
        """Get TER period details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Non-staff users can only see open periods
        if not request.user.is_staff and period.status != PeriodStatus.OPEN:
            return NotFoundError("Periode TER non trouvee.").to_response()

        return 200, ter_period_to_detail_schema(period)

    @http_post(
        "/",
        response={201: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="ter_periods_create",
    )
    def create_ter_period(self, request: HttpRequest, data: TERPeriodCreateSchema):
        """
        Create a new TER period.

        Only staff members (Respo TER) can create periods.
        New periods are created with status 'draft'.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent creer des periodes."
            ).to_response()

        # Check for duplicate name in same academic year
        if TERPeriod.objects.filter(
            name=data.name,
            academic_year=data.academic_year,
        ).exists():
            return BadRequestError(
                "Une periode avec ce nom existe deja pour cette annee academique."
            ).to_response()

        period = TERPeriod.objects.create(
            name=data.name,
            academic_year=data.academic_year,
            status=PeriodStatus.DRAFT,
            group_formation_start=data.group_formation_start,
            group_formation_end=data.group_formation_end,
            subject_selection_start=data.subject_selection_start,
            subject_selection_end=data.subject_selection_end,
            assignment_date=data.assignment_date,
            project_start=data.project_start,
            project_end=data.project_end,
            min_group_size=data.min_group_size,
            max_group_size=data.max_group_size,
        )

        return 201, ter_period_to_detail_schema(period)

    @http_put(
        "/{period_id}",
        response={200: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_update",
    )
    def update_ter_period(
        self, request: HttpRequest, period_id: UUID, data: TERPeriodUpdateSchema
    ):
        """
        Update a TER period.

        Only staff members can update periods.
        Only draft periods can be fully edited.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent modifier des periodes."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Only allow full edits on draft periods
        if period.status != PeriodStatus.DRAFT:
            return BadRequestError(
                "Seules les periodes en brouillon peuvent etre modifiees."
            ).to_response()

        # Update fields if provided
        if data.name is not None:
            period.name = data.name
        if data.group_formation_start is not None:
            period.group_formation_start = data.group_formation_start
        if data.group_formation_end is not None:
            period.group_formation_end = data.group_formation_end
        if data.subject_selection_start is not None:
            period.subject_selection_start = data.subject_selection_start
        if data.subject_selection_end is not None:
            period.subject_selection_end = data.subject_selection_end
        if data.assignment_date is not None:
            period.assignment_date = data.assignment_date
        if data.project_start is not None:
            period.project_start = data.project_start
        if data.project_end is not None:
            period.project_end = data.project_end
        if data.min_group_size is not None:
            period.min_group_size = data.min_group_size
        if data.max_group_size is not None:
            period.max_group_size = data.max_group_size

        period.save()

        return 200, ter_period_to_detail_schema(period)

    @http_post(
        "/{period_id}/open",
        response={200: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_open",
    )
    def open_ter_period(self, request: HttpRequest, period_id: UUID):
        """
        Open a TER period (transition from draft to open).

        Only staff members can open periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent ouvrir des periodes."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        if period.status != PeriodStatus.DRAFT:
            return BadRequestError(
                f"Impossible d'ouvrir une periode avec le statut '{period.status}'."
            ).to_response()

        period.status = PeriodStatus.OPEN
        period.save()

        return 200, ter_period_to_detail_schema(period)

    @http_post(
        "/{period_id}/close",
        response={200: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_close",
    )
    def close_ter_period(self, request: HttpRequest, period_id: UUID):
        """
        Close a TER period (transition from open to closed).

        Only staff members can close periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent cloturer des periodes."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        if period.status != PeriodStatus.OPEN:
            return BadRequestError(
                f"Impossible de cloturer une periode avec le statut '{period.status}'."
            ).to_response()

        period.status = PeriodStatus.CLOSED
        period.save()

        return 200, ter_period_to_detail_schema(period)

    @http_post(
        "/{period_id}/copy",
        response={201: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_copy",
    )
    def copy_ter_period(
        self, request: HttpRequest, period_id: UUID, data: TERPeriodCopySchema
    ):
        """
        Copy a TER period to a new academic year.

        Creates a new draft period with the same configuration but shifted dates.
        Only staff members can copy periods.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent copier des periodes."
            ).to_response()

        source_period = get_object_or_404(TERPeriod, id=period_id)

        # Check for duplicate name in target academic year
        if TERPeriod.objects.filter(
            name=data.name,
            academic_year=data.academic_year,
        ).exists():
            return BadRequestError(
                "Une periode avec ce nom existe deja pour cette annee academique."
            ).to_response()

        # Calculate year offset between source and target academic years
        source_start_year = int(source_period.academic_year[:4])
        target_start_year = int(data.academic_year[:4])
        year_offset = target_start_year - source_start_year

        # Shift all dates by the year offset (approximately 365 days per year)
        days_offset = year_offset * 365

        new_period = TERPeriod.objects.create(
            name=data.name,
            academic_year=data.academic_year,
            status=PeriodStatus.DRAFT,
            group_formation_start=source_period.group_formation_start + timedelta(days=days_offset),
            group_formation_end=source_period.group_formation_end + timedelta(days=days_offset),
            subject_selection_start=source_period.subject_selection_start + timedelta(days=days_offset),
            subject_selection_end=source_period.subject_selection_end + timedelta(days=days_offset),
            assignment_date=source_period.assignment_date + timedelta(days=days_offset),
            project_start=source_period.project_start + timedelta(days=days_offset),
            project_end=source_period.project_end + timedelta(days=days_offset),
            min_group_size=source_period.min_group_size,
            max_group_size=source_period.max_group_size,
        )

        return 201, ter_period_to_detail_schema(new_period)

    @http_get(
        "/{period_id}/stats",
        response={200: TERPeriodStatsSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_stats",
    )
    def get_period_stats(self, request: HttpRequest, period_id: UUID):
        """
        Get statistics for a TER period dashboard.

        Returns counts for:
        - Enrolled students, students in groups, solitaires
        - Total groups, complete groups, assigned groups
        - Total subjects, validated subjects, assignments

        Only staff members (Respo TER) can view stats.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not request.user.is_staff:
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent consulter les statistiques."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Enrolled students
        students_enrolled = period.enrolled_students.count()

        # Students in groups for this period
        students_in_groups_ids = User.objects.filter(
            student_groups__ter_period=period
        ).distinct().values_list("id", flat=True)
        students_in_groups = len(students_in_groups_ids)

        # Solitaires = enrolled but not in any group
        students_solitaires = period.enrolled_students.exclude(
            id__in=students_in_groups_ids
        ).count()

        # Groups for this period
        groups = Group.objects.filter(ter_period=period)
        groups_total = groups.count()

        # Complete groups (member count >= min_group_size)
        groups_complete = sum(
            1 for g in groups if g.member_count >= period.min_group_size
        )

        # Assigned groups (have an assigned subject)
        groups_assigned = groups.filter(assigned_subject__isnull=False).count()

        # Subjects for this period
        subjects = TERSubject.objects.filter(ter_period=period)
        subjects_total = subjects.count()
        subjects_validated = subjects.filter(status=SubjectStatus.VALIDATED).count()

        # Total assignments = groups with assigned subjects
        subjects_assigned = groups_assigned

        return 200, TERPeriodStatsSchema(
            students_enrolled=students_enrolled,
            students_in_groups=students_in_groups,
            students_solitaires=students_solitaires,
            groups_total=groups_total,
            groups_complete=groups_complete,
            groups_assigned=groups_assigned,
            subjects_total=subjects_total,
            subjects_validated=subjects_validated,
            subjects_assigned=subjects_assigned,
        )
