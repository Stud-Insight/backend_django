"""
Stage Dashboard API controller.

Implements:
- 12-7: Stage CSV export
- 12-8: Stage workflow gating warnings
"""

import csv
import io
from uuid import UUID

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    ErrorSchema,
    NotAuthenticatedError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_stage_admin
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    StageApplication,
    StageGrade,
    StageGradeStatus,
    StageOffer,
    StagePeriod,
)
from backend_django.ter.schemas.dashboard import (
    WorkflowWarningSchema,
    WorkflowWarningsResponseSchema,
)

DASHBOARD_CACHE_TTL = 60  # seconds


def _compute_stage_phase(period: StagePeriod) -> str:
    """Compute current stage phase based on dates."""
    from datetime import date as date_type
    today = date_type.today()

    if today < period.offer_submission_start:
        return "upcoming"
    if today <= period.offer_submission_end:
        return "offers"
    if today < period.application_start:
        return "review"
    if today <= period.application_end:
        return "applications"
    if today < period.internship_start:
        return "assignment"
    if today <= period.internship_end:
        return "execution"
    return "finished"


@api_controller("/stages/dashboard", tags=["Stage Dashboard"], permissions=[IsAuthenticated])
class StageDashboardController(BaseAPI):
    """API endpoints for stage dashboard and exports."""

    # ==================== 12-8: Workflow Gating Warnings ====================

    @http_get(
        "/warnings/{period_id}",
        response={200: WorkflowWarningsResponseSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_dashboard_warnings",
    )
    def workflow_warnings(self, request: HttpRequest, period_id: UUID):
        """
        Get workflow gating warnings for a Stage period.

        Returns pre-condition checks that help Respo Stage
        understand what needs attention.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent consulter les alertes."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        cache_key = f"stage_warnings_{period_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return 200, cached

        current_phase = _compute_stage_phase(period)
        warnings = []

        # Counts
        total_offers = StageOffer.objects.filter(stage_period=period).count()
        validated_offers = StageOffer.objects.filter(
            stage_period=period, status=OfferStatus.VALIDATED
        ).count()
        pending_offers = StageOffer.objects.filter(
            stage_period=period, status=OfferStatus.SUBMITTED
        ).count()
        draft_offers = StageOffer.objects.filter(
            stage_period=period, status=OfferStatus.DRAFT
        ).count()

        total_applications = StageApplication.objects.filter(
            offer__stage_period=period
        ).count()
        pending_applications = StageApplication.objects.filter(
            offer__stage_period=period, status=ApplicationStatus.PENDING
        ).count()
        accepted_applications = StageApplication.objects.filter(
            offer__stage_period=period, status=ApplicationStatus.ACCEPTED
        ).count()
        confirmed_applications = StageApplication.objects.filter(
            offer__stage_period=period, status=ApplicationStatus.CONFIRMED
        ).count()

        # Applications without academic supervisor
        no_supervisor = StageApplication.objects.filter(
            offer__stage_period=period,
            status=ApplicationStatus.CONFIRMED,
            academic_supervisor__isnull=True,
        ).count()

        # Grading
        total_grades = StageGrade.objects.filter(stage_period=period).count()
        finalized_grades = StageGrade.objects.filter(
            stage_period=period, status=StageGradeStatus.FINALIZED
        ).count()
        grades_missing_academic = StageGrade.objects.filter(
            stage_period=period, academic_grade__isnull=True
        ).count()
        grades_missing_company = StageGrade.objects.filter(
            stage_period=period, company_grade__isnull=True
        ).count()

        # --- Offer warnings ---
        if total_offers == 0:
            warnings.append(WorkflowWarningSchema(
                level="error", phase="offers",
                message="Aucune offre de stage creee pour cette periode.",
            ))
        if pending_offers > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="offers",
                message=f"{pending_offers} offre(s) en attente de validation.",
                count=pending_offers, total=total_offers,
            ))
        if draft_offers > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="offers",
                message=f"{draft_offers} offre(s) encore en brouillon.",
                count=draft_offers, total=total_offers,
            ))
        if validated_offers == 0 and total_offers > 0:
            warnings.append(WorkflowWarningSchema(
                level="error", phase="applications",
                message="Aucune offre validee. Les candidatures sont impossibles.",
                count=0, total=total_offers,
            ))

        # --- Application warnings ---
        if pending_applications > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="applications",
                message=f"{pending_applications} candidature(s) en attente de decision.",
                count=pending_applications, total=total_applications,
            ))
        if accepted_applications > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="applications",
                message=f"{accepted_applications} candidature(s) acceptee(s) non confirmee(s) par l'etudiant.",
                count=accepted_applications, total=total_applications,
            ))

        # --- Assignment warnings ---
        if no_supervisor > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="assignment",
                message=f"{no_supervisor} stage(s) confirme(s) sans superviseur academique.",
                count=no_supervisor, total=confirmed_applications,
            ))

        # --- Grading warnings ---
        if confirmed_applications > 0 and total_grades < confirmed_applications:
            missing = confirmed_applications - total_grades
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="execution",
                message=f"{missing} stage(s) confirme(s) sans fiche de note.",
                count=missing, total=confirmed_applications,
            ))
        if grades_missing_academic > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="execution",
                message=f"{grades_missing_academic} note(s) academique(s) manquante(s).",
                count=grades_missing_academic, total=total_grades,
            ))
        if grades_missing_company > 0:
            warnings.append(WorkflowWarningSchema(
                level="warning", phase="execution",
                message=f"{grades_missing_company} note(s) entreprise manquante(s).",
                count=grades_missing_company, total=total_grades,
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
            current_phase=current_phase,
            warnings=warnings,
        )

        cache.set(cache_key, result, DASHBOARD_CACHE_TTL)
        return 200, result

    # ==================== 12-7: Stage CSV Export ====================

    @http_get(
        "/export/{period_id}/csv",
        response={401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_dashboard_export_csv",
    )
    def export_stage_csv(self, request: HttpRequest, period_id: UUID):
        """
        Export stage period data as CSV.

        Includes confirmed applications with grades.
        Only Respo Stage / Admin can export.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent exporter les donnees."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=period_id)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")

        writer.writerow([
            "Etudiant Email",
            "Nom",
            "Prenom",
            "Offre",
            "Entreprise",
            "Superviseur Entreprise",
            "Superviseur Academique",
            "Note Academique",
            "Note Entreprise",
            "Note Finale",
            "Statut",
        ])

        applications = StageApplication.objects.filter(
            offer__stage_period=period,
            status=ApplicationStatus.CONFIRMED,
        ).select_related(
            "student",
            "offer",
            "offer__supervisor",
            "academic_supervisor",
        ).order_by("student__last_name", "student__first_name")

        for app in applications:
            grade = StageGrade.objects.filter(application=app).first()
            student = app.student
            offer = app.offer

            writer.writerow([
                student.email,
                student.last_name,
                student.first_name,
                offer.title,
                offer.company_name,
                offer.supervisor.get_full_name() if offer.supervisor else "",
                app.academic_supervisor.get_full_name() if app.academic_supervisor else "",
                str(grade.academic_grade) if grade and grade.academic_grade is not None else "",
                str(grade.company_grade) if grade and grade.company_grade is not None else "",
                str(grade.final_grade) if grade and grade.final_grade is not None else "",
                grade.status if grade else "non_note",
            ])

        response = HttpResponse(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
        )
        filename = f"export_stages_{period.name}_{period.academic_year}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
