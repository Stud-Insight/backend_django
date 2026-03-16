"""
Stage Dashboard API controller.

Implements:
- 12-7: Stage CSV export
"""

import csv
import io
from uuid import UUID

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
    StageApplication,
    StageGrade,
    StagePeriod,
)


@api_controller("/stages/dashboard", tags=["Stage Dashboard"], permissions=[IsAuthenticated])
class StageDashboardController(BaseAPI):
    """API endpoints for stage dashboard and exports."""

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
