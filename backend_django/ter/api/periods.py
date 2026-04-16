"""
TER Periods API controller.
"""

from datetime import timedelta
from uuid import UUID

from django.core.cache import cache
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

TER_STATS_CACHE_TTL = 60  # seconds
from ninja_extra import api_controller, http_delete, http_get, http_post, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.guards import check_period_not_archived
from backend_django.core.exceptions import (
    AlreadyExistsError,
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.core.schemas import PaginatedResponseSchema, paginate_queryset
from backend_django.groups.models import Group
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERRanking, TERSubject
from backend_django.ter.schemas.periods import (
    AddStudentSchema,
    AssignmentStatisticsSchema,
    ChoiceDistributionSchema,
    TERPeriodCopySchema,
    TERPeriodCreateSchema,
    TERPeriodDetailSchema,
    TERPeriodSchema,
    TERPeriodStatsSchema,
    TERPeriodUpdateSchema,
    UnassignedGroupSchema,
    UnassignedSubjectSchema,
)
from backend_django.users.schemas import UserMinimalSchema
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
        "/me",
        response={200: list[TERPeriodSchema], 401: ErrorSchema},
        url_name="ter_periods_me",
    )
    def get_my_periods(self, request: HttpRequest):
        """
        Return all TER periods the current student is enrolled in.

        This allows a student to get their periods without providing a UUID.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Fetch periods where the current user is enrolled
        periods = TERPeriod.objects.filter(enrolled_students=request.user).order_by(
            "-academic_year", "-created"
        )

        return 200, [ter_period_to_schema(p) for p in periods]

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

        if not is_ter_admin(request.user):
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

        # Non-admin users can only see open periods
        if not is_ter_admin(request.user) and period.status != PeriodStatus.OPEN:
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

        if not is_ter_admin(request.user):
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

        if not is_ter_admin(request.user):
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

        if not is_ter_admin(request.user):
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

        if not is_ter_admin(request.user):
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
        "/{period_id}/archive",
        response={200: TERPeriodDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_archive",
    )
    def archive_ter_period(self, request: HttpRequest, period_id: UUID):
        """
        Archive a TER period (transition from closed to archived).

        Archived periods become read-only. Only staff members can archive.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent archiver des periodes."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        if period.status != PeriodStatus.CLOSED:
            return BadRequestError(
                f"Impossible d'archiver une periode avec le statut '{period.status}'. "
                "Seules les periodes cloturees peuvent etre archivees."
            ).to_response()

        period.status = PeriodStatus.ARCHIVED
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

        if not is_ter_admin(request.user):
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

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent consulter les statistiques."
            ).to_response()

        cache_key = f"ter_period_stats_{period_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return 200, cached

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

        result = TERPeriodStatsSchema(
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
        cache.set(cache_key, result, TER_STATS_CACHE_TTL)
        return 200, result

    @http_get(
        "/{period_id}/assignment-statistics",
        response={200: AssignmentStatisticsSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_assignment_stats",
    )
    def get_assignment_statistics(self, request: HttpRequest, period_id: UUID):
        """
        Get detailed assignment statistics for algorithm quality evaluation.

        Returns:
        - Distribution of groups by their assigned choice rank
        - Average satisfaction score
        - Lists of unassigned groups and subjects
        - Percentage metrics for quality assessment

        Only staff members (Respo TER) can view assignment statistics.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent consulter les statistiques d'affectation."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Get all groups for this period
        all_groups = Group.objects.filter(ter_period=period)
        total_groups = all_groups.count()

        # Get assigned and unassigned groups
        assigned_groups = all_groups.filter(assigned_subject__isnull=False)
        unassigned_groups = all_groups.filter(assigned_subject__isnull=True)
        assigned_groups_count = assigned_groups.count()
        unassigned_groups_count = unassigned_groups.count()

        # Get all validated subjects
        all_subjects = TERSubject.objects.filter(
            ter_period=period,
            status=SubjectStatus.VALIDATED,
        )
        total_subjects = all_subjects.count()

        # Get subjects with at least one assignment
        assigned_subject_ids = assigned_groups.values_list("assigned_subject_id", flat=True)
        assigned_subjects_count = len(set(assigned_subject_ids))
        unassigned_subjects_count = total_subjects - assigned_subjects_count

        # Calculate choice distribution
        choice_counts = {}
        total_rank_sum = 0
        valid_assignments = 0

        for group in assigned_groups:
            # Find this group's ranking for their assigned subject
            ranking = TERRanking.objects.filter(
                group=group,
                subject=group.assigned_subject,
            ).first()

            if ranking:
                rank = ranking.rank
                choice_counts[rank] = choice_counts.get(rank, 0) + 1
                total_rank_sum += rank
                valid_assignments += 1

        # Build choice distribution
        choice_distribution = []
        for rank in sorted(choice_counts.keys()):
            count = choice_counts[rank]
            percentage = (count / assigned_groups_count * 100) if assigned_groups_count > 0 else 0
            choice_distribution.append(ChoiceDistributionSchema(
                rank=rank,
                count=count,
                percentage=round(percentage, 1),
            ))

        # Calculate average choice rank
        average_choice_rank = None
        if valid_assignments > 0:
            average_choice_rank = round(total_rank_sum / valid_assignments, 2)

        # Calculate satisfaction metrics
        groups_with_first_choice = choice_counts.get(1, 0)
        groups_with_first_choice_pct = (
            (groups_with_first_choice / assigned_groups_count * 100)
            if assigned_groups_count > 0 else 0
        )

        groups_with_top_3 = sum(choice_counts.get(i, 0) for i in [1, 2, 3])
        groups_with_top_3_pct = (
            (groups_with_top_3 / assigned_groups_count * 100)
            if assigned_groups_count > 0 else 0
        )

        # Build unassigned groups list
        unassigned_groups_list = []
        for group in unassigned_groups:
            has_rankings = TERRanking.objects.filter(group=group).exists()
            unassigned_groups_list.append(UnassignedGroupSchema(
                id=group.id,
                name=group.name,
                member_count=group.member_count,
                has_rankings=has_rankings,
            ))

        # Build unassigned subjects list
        unassigned_subjects_list = []
        for subject in all_subjects.exclude(id__in=assigned_subject_ids):
            current_count = Group.objects.filter(
                ter_period=period,
                assigned_subject=subject,
            ).count()
            unassigned_subjects_list.append(UnassignedSubjectSchema(
                id=subject.id,
                title=subject.title,
                max_groups=subject.max_groups,
                current_assignments=current_count,
            ))

        return 200, AssignmentStatisticsSchema(
            total_groups=total_groups,
            assigned_groups=assigned_groups_count,
            unassigned_groups=unassigned_groups_count,
            total_subjects=total_subjects,
            assigned_subjects=assigned_subjects_count,
            unassigned_subjects=unassigned_subjects_count,
            choice_distribution=choice_distribution,
            average_choice_rank=average_choice_rank,
            unassigned_groups_list=unassigned_groups_list,
            unassigned_subjects_list=unassigned_subjects_list,
            groups_with_first_choice=groups_with_first_choice,
            groups_with_first_choice_percentage=round(groups_with_first_choice_pct, 1),
            groups_with_top_3_choice=groups_with_top_3,
            groups_with_top_3_choice_percentage=round(groups_with_top_3_pct, 1),
        )

    # ==================== Students Management ====================
    @http_get(
        "/{period_id}/students",
        response={200: PaginatedResponseSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_students_list",
    )
    def list_students(self, request: HttpRequest, period_id: UUID, search: str = "", page: int = 1, page_size: int = 20):
        """
        List students enrolled in a TER period (paginated).

        Accessible to Respo TER / Admin, or any student enrolled in the period.
        Supports optional `search` query param to filter by name or email.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        is_enrolled = period.enrolled_students.filter(id=request.user.id).exists()
        if not is_ter_admin(request.user) and not is_enrolled:
            return PermissionDeniedError(
                "Vous devez être inscrit à cette période ou être responsable TER."
            ).to_response()

        students = period.enrolled_students.order_by("last_name", "first_name")

        if search:
            students = students.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        items, count, pg, ps = paginate_queryset(students, page, page_size)

        return 200, PaginatedResponseSchema(
            count=count, page=pg, page_size=ps,
            results=[UserMinimalSchema.from_user(s) for s in items],
        )

    @http_post(
        "/{period_id}/students",
        response={
            201: UserMinimalSchema,
            400: ErrorSchema,
            401: ErrorSchema,
            403: ErrorSchema,
            404: ErrorSchema,
            409: ErrorSchema,
        },
        url_name="ter_periods_students_add",
    )
    def add_student(self, request: HttpRequest, period_id: UUID, data: AddStudentSchema):
        """
        Add a student to a TER period.

        Only Respo TER / Admin can add students.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent ajouter des étudiants."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        error = check_period_not_archived(period)
        if error:
            return error

        try:
            student = User.objects.get(id=data.user_id)
        except User.DoesNotExist:
            return NotFoundError("Utilisateur introuvable.").to_response()

        if period.enrolled_students.filter(id=student.id).exists():
            return AlreadyExistsError(
                "Cet étudiant est déjà inscrit à cette période TER."
            ).to_response()

        period.enrolled_students.add(student)

        return 201, UserMinimalSchema.from_user(student)

    @http_delete(
        "/{period_id}/students/{user_id}",
        response={204: None, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_students_remove",
    )
    def remove_student(self, request: HttpRequest, period_id: UUID, user_id: UUID):
        """
        Remove a student from a TER period.

        Only Respo TER / Admin can remove students.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent retirer des étudiants."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        error = check_period_not_archived(period)
        if error:
            return error

        if not period.enrolled_students.filter(id=user_id).exists():
            return NotFoundError(
                "Cet étudiant n'est pas inscrit à cette période TER."
            ).to_response()

        period.enrolled_students.remove(user_id)

        return 204, None

    # ==================== Encadrants ====================
    @http_get(
        "/{period_id}/encadrants",
        response={200: PaginatedResponseSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_encadrants_list",
    )
    def list_encadrants(self, request: HttpRequest, period_id: UUID, page: int = 1, page_size: int = 20):
        """
        List encadrants for a TER period (paginated).

        Returns the union of:
        - Professors explicitly added to the period (period.professors)
        - Professors/supervisors who have subjects in this period

        Only Respo TER / Admin can view encadrants.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent consulter les encadrants."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Encadrants inscrits explicitement
        explicit_ids = period.professors.values_list("id", flat=True)

        # Encadrants ayant des sujets (professor ou supervisor)
        from_subjects = User.objects.filter(
            Q(ter_subjects_created__ter_period=period) |
            Q(ter_subjects_supervised__ter_period=period)
        ).values_list("id", flat=True)

        # Union des deux sources
        all_ids = set(explicit_ids) | set(from_subjects)
        encadrants = User.objects.filter(id__in=all_ids).order_by("last_name", "first_name")

        items, count, pg, ps = paginate_queryset(encadrants, page, page_size)

        return 200, PaginatedResponseSchema(
            count=count,
            page=pg,
            page_size=ps,
            results=[UserMinimalSchema.from_user(e) for e in items],
        )

    @http_post(
        "/{period_id}/encadrants/{user_id}",
        response={200: UserMinimalSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_encadrants_add",
    )
    def add_encadrant(self, request: HttpRequest, period_id: UUID, user_id: UUID):
        """
        Add an encadrant to a TER period.

        This allows adding professors before they create subjects.
        Only Respo TER / Admin can add encadrants.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError("Accès réservé aux responsables TER.").to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        error = check_period_not_archived(period)
        if error:
            return error

        user = get_object_or_404(User, id=user_id)

        period.professors.add(user)

        return 200, UserMinimalSchema.from_user(user)

    @http_delete(
        "/{period_id}/encadrants/{user_id}",
        response={204: None, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_periods_encadrants_remove",
    )
    def remove_encadrant(self, request: HttpRequest, period_id: UUID, user_id: UUID):
        """
        Remove an encadrant from a TER period.

        Only removes from the explicit list (professors field).
        If the encadrant has subjects, they will still appear in the list.
        Only Respo TER / Admin can remove encadrants.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError("Accès réservé aux responsables TER.").to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        error = check_period_not_archived(period)
        if error:
            return error

        period.professors.remove(user_id)

        return 204, None
