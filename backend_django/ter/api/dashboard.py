"""
TER Dashboard API controller.

Implements:
- 12-3: Encadrant dashboard (assigned groups + progress)
- 12-4: Student dashboard (current phase + deadlines)
- 12-5: Admin system-wide statistics
- 12-6: TER CSV export
"""

import csv
import io
from datetime import date
from uuid import UUID

from django.core.cache import cache
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    ErrorSchema,
    NotAuthenticatedError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_admin, is_ter_admin, user_has_role, Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    GradeStatus,
    PeriodStatus,
    SubjectStatus,
    TERDeliverable,
    TERGrade,
    TERIndividualGrade,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.ter.schemas.dashboard import (
    AdminSystemStatsSchema,
    EncadrantDashboardSchema,
    EncadrantGroupDeliverableSchema,
    EncadrantGroupSchema,
    StudentDashboardSchema,
    StudentPhaseSchema,
    WorkflowWarningSchema,
    WorkflowWarningsResponseSchema,
)
from backend_django.users.models import User
from backend_django.users.schemas import UserMinimalSchema

DASHBOARD_CACHE_TTL = 60  # seconds


# ==================== Helper Functions ====================


def compute_phase(period: TERPeriod) -> StudentPhaseSchema:
    """Compute the current phase for a TER period based on today's date."""
    today = date.today()

    phases = [
        (
            period.group_formation_start,
            period.group_formation_end,
            "formation",
            "Formation des groupes",
            period.group_formation_end,
            "Fin formation groupes",
        ),
        (
            period.subject_selection_start,
            period.subject_selection_end,
            "selection",
            "Classement des sujets",
            period.subject_selection_end,
            "Fin classement sujets",
        ),
        (
            period.subject_selection_end,
            period.assignment_date,
            "assignment",
            "Affectation",
            period.assignment_date,
            "Date d'affectation",
        ),
        (
            period.project_start,
            period.project_end,
            "execution",
            "Execution du projet",
            period.project_end,
            "Fin du projet",
        ),
    ]

    for start, end, phase_key, phase_label, deadline, deadline_label in phases:
        if start <= today <= end:
            days = (deadline - today).days
            return StudentPhaseSchema(
                current_phase=phase_key,
                current_phase_label=phase_label,
                next_deadline=deadline,
                next_deadline_label=deadline_label,
                days_remaining=max(0, days),
            )

    # Between assignment and project start
    if period.assignment_date <= today < period.project_start:
        days = (period.project_start - today).days
        return StudentPhaseSchema(
            current_phase="assignment",
            current_phase_label="En attente du projet",
            next_deadline=period.project_start,
            next_deadline_label="Debut du projet",
            days_remaining=max(0, days),
        )

    if today > period.project_end:
        return StudentPhaseSchema(
            current_phase="finished",
            current_phase_label="Termine",
            next_deadline=None,
            next_deadline_label=None,
            days_remaining=None,
        )

    # Before start
    if today < period.group_formation_start:
        days = (period.group_formation_start - today).days
        return StudentPhaseSchema(
            current_phase="upcoming",
            current_phase_label="A venir",
            next_deadline=period.group_formation_start,
            next_deadline_label="Debut formation groupes",
            days_remaining=max(0, days),
        )

    return StudentPhaseSchema(
        current_phase="unknown",
        current_phase_label="Inconnu",
        next_deadline=None,
        next_deadline_label=None,
        days_remaining=None,
    )


# ==================== TER Dashboard Controller ====================


@api_controller("/ter/dashboard", tags=["TER Dashboard"], permissions=[IsAuthenticated])
class TERDashboardController(BaseAPI):
    """API for TER dashboards."""

    # ==================== Encadrant Periods ====================

    @http_get(
        "/encadrant/periods",
        response={200: list[dict], 401: ErrorSchema},
        url_name="ter_dashboard_encadrant_periods",
    )
    def encadrant_periods(self, request: HttpRequest):
        """
        Get TER periods where the current user is professor or supervisor of at least one subject.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        user = request.user
        period_ids = TERSubject.objects.filter(
            Q(professor=user) | Q(supervisor=user)
        ).values_list("ter_period_id", flat=True).distinct()

        periods = TERPeriod.objects.filter(id__in=period_ids).order_by("-academic_year", "-created")

        return 200, [
            {
                "id": str(p.id),
                "name": p.name,
                "academic_year": p.academic_year,
                "status": p.status,
            }
            for p in periods
        ]

    # ==================== 12-3: Encadrant Dashboard ====================

    @http_get(
        "/encadrant/{period_id}",
        response={200: EncadrantDashboardSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_dashboard_encadrant",
    )
    def encadrant_dashboard(self, request: HttpRequest, period_id: UUID):
        """
        Get encadrant dashboard for a TER period.

        Shows all groups where the encadrant is professor or supervisor
        of the assigned subject, with deliverables and grade info.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        user = request.user

        cache_key = f"ter_encadrant_dashboard_{period_id}_{user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return 200, cached

        # Find groups assigned to subjects where user is professor or supervisor
        groups = Group.objects.filter(
            ter_period=period,
            assigned_subject__isnull=False,
        ).filter(
            Q(assigned_subject__professor=user) | Q(assigned_subject__supervisor=user)
        ).select_related(
            "assigned_subject",
        ).prefetch_related("members").distinct()

        group_schemas = []
        graded_count = 0
        finalized_count = 0

        for group in groups:
            subject = group.assigned_subject
            members = [UserMinimalSchema.from_user(m) for m in group.members.all()]

            # Deliverables
            deliverables_total = TERDeliverable.objects.filter(group=group).count()
            deliverables_submitted = TERDeliverable.objects.filter(
                group=group,
                upload_status="completed",
            ).count()

            # Grade
            grade = TERGrade.objects.filter(group=group, ter_period=period).first()
            grade_status = grade.status if grade else None
            group_grade = grade.group_grade if grade else None

            if grade and grade.group_grade is not None:
                graded_count += 1
            if grade and grade.status == GradeStatus.FINALIZED:
                finalized_count += 1

            group_schemas.append(EncadrantGroupSchema(
                id=group.id,
                name=group.name,
                members=members,
                subject_title=subject.title,
                subject_id=subject.id,
                deliverables=EncadrantGroupDeliverableSchema(
                    total=deliverables_total,
                    submitted=deliverables_submitted,
                ),
                grade_status=grade_status,
                group_grade=group_grade,
            ))

        result = EncadrantDashboardSchema(
            ter_period_id=period.id,
            ter_period_name=period.name,
            groups=group_schemas,
            total_groups=len(group_schemas),
            graded_groups=graded_count,
            finalized_groups=finalized_count,
        )
        cache.set(cache_key, result, DASHBOARD_CACHE_TTL)
        return 200, result

    # ==================== 12-4: Student Dashboard ====================

    @http_get(
        "/student",
        response={200: StudentDashboardSchema, 401: ErrorSchema},
        url_name="ter_dashboard_student",
    )
    def student_dashboard(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
    ):
        """
        Get student dashboard with current phase and deadlines.

        Returns phase information, group status, and next deadline.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        user = request.user

        # Find period
        if ter_period_id:
            period = get_object_or_404(TERPeriod, id=ter_period_id)
        else:
            period = TERPeriod.objects.filter(
                status=PeriodStatus.OPEN,
                enrolled_students=user,
            ).first()

        if not period:
            return 200, StudentDashboardSchema(
                ter_period_id=None,
                ter_period_name=None,
                status="no_period",
                phase=None,
                group_name=None,
                group_id=None,
                subject_title=None,
                subject_id=None,
            )

        # Find group
        group = Group.objects.filter(
            ter_period=period,
            members=user,
        ).select_related("assigned_subject").first()

        # Compute status
        if not group:
            status = "no_group"
        elif group.assigned_subject:
            status = "subject_assigned"
        elif group.status == "forme":
            status = "group_formed"
        else:
            status = "group_forming"

        # Compute phase
        phase = compute_phase(period)

        return 200, StudentDashboardSchema(
            ter_period_id=period.id,
            ter_period_name=period.name,
            status=status,
            phase=phase,
            group_name=group.name if group else None,
            group_id=group.id if group else None,
            subject_title=group.assigned_subject.title if group and group.assigned_subject else None,
            subject_id=group.assigned_subject_id if group and group.assigned_subject_id else None,
        )

    # ==================== 12-5: Admin System-Wide Stats ====================

    @http_get(
        "/admin/stats",
        response={200: AdminSystemStatsSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="ter_dashboard_admin_stats",
    )
    def admin_system_stats(self, request: HttpRequest):
        """
        Get system-wide statistics for admin dashboard.

        Only accessible to Admin users.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_admin(request.user) and not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les administrateurs peuvent consulter les statistiques systeme."
            ).to_response()

        cache_key = "ter_admin_stats"
        cached = cache.get(cache_key)
        if cached is not None:
            return 200, cached

        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        total_students = User.objects.filter(groups__name=Role.ETUDIANT.value).distinct().count()
        total_encadrants = User.objects.filter(groups__name=Role.ENCADRANT.value).distinct().count()
        total_externes = User.objects.filter(groups__name=Role.EXTERNE.value).distinct().count()

        active_ter = TERPeriod.objects.filter(status=PeriodStatus.OPEN).count()
        draft_ter = TERPeriod.objects.filter(status=PeriodStatus.DRAFT).count()
        archived_ter = TERPeriod.objects.filter(status=PeriodStatus.ARCHIVED).count()

        # Stage periods (import conditionally to avoid circular imports)
        try:
            from backend_django.stages.models import PeriodStatus as StagePeriodStatus, StagePeriod
            active_stage = StagePeriod.objects.filter(status=StagePeriodStatus.OPEN).count()
        except (ImportError, Exception):
            active_stage = 0

        result = AdminSystemStatsSchema(
            total_users=total_users,
            active_users=active_users,
            total_students=total_students,
            total_encadrants=total_encadrants,
            total_externes=total_externes,
            active_ter_periods=active_ter,
            draft_ter_periods=draft_ter,
            archived_ter_periods=archived_ter,
            active_stage_periods=active_stage,
        )
        cache.set(cache_key, result, DASHBOARD_CACHE_TTL)
        return 200, result

    # ==================== 12-8: Workflow Gating Warnings ====================

    @http_get(
        "/warnings/{period_id}",
        response={200: WorkflowWarningsResponseSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_dashboard_warnings",
    )
    def workflow_warnings(self, request: HttpRequest, period_id: UUID):
        """
        Get workflow gating warnings for a TER period.

        Returns pre-condition checks and warnings that help Respo TER
        understand what needs to happen before phase transitions.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent consulter les alertes."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        cache_key = f"ter_warnings_{period_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return 200, cached

        phase = compute_phase(period)
        warnings = []

        # Counts
        total_subjects = TERSubject.objects.filter(ter_period=period).count()
        validated_subjects = TERSubject.objects.filter(
            ter_period=period, status=SubjectStatus.VALIDATED
        ).count()
        pending_subjects = TERSubject.objects.filter(
            ter_period=period, status=SubjectStatus.SUBMITTED
        ).count()
        draft_subjects = TERSubject.objects.filter(
            ter_period=period, status=SubjectStatus.DRAFT
        ).count()

        enrolled_count = period.enrolled_students.count()
        groups = Group.objects.filter(ter_period=period)
        total_groups = groups.count()
        formed_groups = groups.filter(
            status__in=[GroupStatus.FORME, GroupStatus.CLOTURE]
        ).count()
        students_in_groups = User.objects.filter(
            student_groups__ter_period=period
        ).distinct().count()
        solitaires = enrolled_count - students_in_groups

        groups_with_ranking = TERRanking.objects.filter(
            group__ter_period=period
        ).values("group").distinct().count()

        assigned_groups = groups.filter(assigned_subject__isnull=False).count()

        grades = TERGrade.objects.filter(ter_period=period)
        total_grades = grades.count()
        finalized_grades = grades.filter(status=GradeStatus.FINALIZED).count()

        # --- Subject validation warnings ---
        if total_subjects == 0:
            warnings.append(WorkflowWarningSchema(
                level="error", phase="formation",
                message="Aucun sujet cree pour cette periode.",
            ))
        if pending_subjects > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="formation",
                message=f"{pending_subjects} sujet(s) en attente de validation.",
                count=pending_subjects, total=total_subjects,
            ))
        if draft_subjects > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="formation",
                message=f"{draft_subjects} sujet(s) encore en brouillon.",
                count=draft_subjects, total=total_subjects,
            ))

        # --- Enrollment warnings ---
        if enrolled_count == 0:
            warnings.append(WorkflowWarningSchema(
                level="error", phase="formation",
                message="Aucun etudiant inscrit a cette periode.",
            ))

        # --- Group formation warnings ---
        if solitaires > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="formation",
                message=f"{solitaires} etudiant(s) sans groupe.",
                count=solitaires, total=enrolled_count,
            ))
        if total_groups > 0 and formed_groups < total_groups:
            incomplete = total_groups - formed_groups
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="formation",
                message=f"{incomplete} groupe(s) non forme(s) (statut ouvert).",
                count=incomplete, total=total_groups,
            ))

        # --- Ranking warnings ---
        if validated_subjects == 0 and total_subjects > 0:
            warnings.append(WorkflowWarningSchema(
                level="error", phase="selection",
                message="Aucun sujet valide. Le classement est impossible.",
                count=0, total=total_subjects,
            ))
        if formed_groups > 0 and groups_with_ranking < formed_groups:
            missing = formed_groups - groups_with_ranking
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="selection",
                message=f"{missing} groupe(s) n'ont pas soumis de classement.",
                count=missing, total=formed_groups,
            ))

        # --- Assignment warnings ---
        if formed_groups > 0 and assigned_groups < formed_groups:
            unassigned = formed_groups - assigned_groups
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="assignment",
                message=f"{unassigned} groupe(s) non affecte(s) a un sujet.",
                count=unassigned, total=formed_groups,
            ))

        # --- Grading warnings ---
        if assigned_groups > 0 and total_grades < assigned_groups:
            missing = assigned_groups - total_grades
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="execution",
                message=f"{missing} groupe(s) sans note saisie.",
                count=missing, total=assigned_groups,
            ))
        if total_grades > 0 and finalized_grades < total_grades:
            pending = total_grades - finalized_grades
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="execution",
                message=f"{pending} note(s) non finalisee(s).",
                count=pending, total=total_grades,
            ))

        result = WorkflowWarningsResponseSchema(
            period_id=period.id,
            period_name=period.name,
            current_phase=phase.current_phase,
            warnings=warnings,
        )

        cache.set(cache_key, result, DASHBOARD_CACHE_TTL)
        return 200, result

    # ==================== 12-6: TER CSV Export ====================

    @http_get(
        "/export/{period_id}/csv",
        response={401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_dashboard_export_csv",
    )
    def export_ter_csv(self, request: HttpRequest, period_id: UUID):
        """
        Export TER period data as CSV.

        Includes groups, members, subjects, and grades.
        Only Respo TER / Admin can export.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables TER peuvent exporter les donnees."
            ).to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")

        # Header
        writer.writerow([
            "Groupe",
            "Etudiant Email",
            "Etudiant Nom",
            "Etudiant Prenom",
            "Sujet",
            "Encadrant",
            "Note Groupe",
            "Notation Individuelle",
            "Note Individuelle",
            "Note Finale",
            "Statut Note",
        ])

        # Get all groups with assigned subjects
        groups = Group.objects.filter(
            ter_period=period,
        ).select_related(
            "assigned_subject",
            "assigned_subject__professor",
        ).prefetch_related("members").order_by("name")

        for group in groups:
            subject = group.assigned_subject
            grade = TERGrade.objects.filter(group=group, ter_period=period).first()

            for member in group.members.all().order_by("last_name", "first_name"):
                # Individual grade
                individual = None
                if grade:
                    individual = TERIndividualGrade.objects.filter(
                        grade=grade, student=member
                    ).first()

                writer.writerow([
                    group.name,
                    member.email,
                    member.last_name,
                    member.first_name,
                    subject.title if subject else "",
                    subject.professor.get_full_name() if subject and subject.professor else "",
                    str(grade.group_grade) if grade and grade.group_grade is not None else "",
                    "Oui" if individual and individual.opted_in else "Non",
                    str(individual.individual_grade) if individual and individual.individual_grade is not None else "",
                    str(individual.final_grade) if individual and individual.final_grade is not None else (
                        str(grade.group_grade) if grade and grade.group_grade is not None else ""
                    ),
                    grade.status if grade else "non_note",
                ])

        # Students without groups
        students_in_groups = User.objects.filter(
            student_groups__ter_period=period
        ).values_list("id", flat=True)

        solitaires = period.enrolled_students.exclude(
            id__in=students_in_groups
        ).order_by("last_name", "first_name")

        for student in solitaires:
            writer.writerow([
                "(sans groupe)",
                student.email,
                student.last_name,
                student.first_name,
                "",
                "",
                "",
                "",
                "",
                "",
                "non_note",
            ])

        # Return CSV response
        response = HttpResponse(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
        )
        filename = f"export_ter_{period.name}_{period.academic_year}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
