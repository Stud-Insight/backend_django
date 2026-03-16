"""
Stage Grading API controller.

Handles academic grades (encadrant), company grades (externe),
grade finalization, and student grade viewing.
"""

from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja_extra import api_controller, http_get, http_post, http_put

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
    StageApplication,
    StageGrade,
    StageGradeStatus,
    StagePeriod,
)
from backend_django.stages.schemas.grading import (
    StageGradeAcademicUpdateSchema,
    StageGradeCompanyUpdateSchema,
    StageGradeFinalizeSchema,
    StageGradeSchema,
    StudentStageGradeSchema,
)


def _grade_to_schema(grade: StageGrade) -> StageGradeSchema:
    """Convert a StageGrade instance to its schema representation."""
    app = grade.application
    student = app.student
    offer = app.offer
    return StageGradeSchema(
        id=grade.id,
        application_id=app.id,
        stage_period_id=grade.stage_period_id,
        student_email=student.email,
        student_name=f"{student.first_name} {student.last_name}".strip() or student.email,
        offer_title=offer.title,
        company_name=offer.company_name,
        academic_grade=grade.academic_grade,
        academic_grade_comment=grade.academic_grade_comment,
        academic_graded_by_id=grade.academic_graded_by_id,
        academic_graded_at=grade.academic_graded_at,
        company_grade=grade.company_grade,
        company_grade_comment=grade.company_grade_comment,
        company_graded_by_id=grade.company_graded_by_id,
        company_graded_at=grade.company_graded_at,
        final_grade=grade.final_grade,
        status=grade.status,
        finalized_at=grade.finalized_at,
        finalized_by_id=grade.finalized_by_id,
        created=grade.created,
        modified=grade.modified,
    )


@api_controller("/stages/grades", tags=["Stage Grading"], permissions=[IsAuthenticated])
class StageGradingController(BaseAPI):
    """API endpoints for stage grading."""

    # Static paths must be declared before dynamic /{application_id} paths

    @http_get(
        "/my-grades",
        response={200: list[StudentStageGradeSchema], 401: ErrorSchema},
        url_name="stage_my_grades",
    )
    def get_my_grades(self, request: HttpRequest):
        """Get current student's grades (only visible if finalized)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        applications = StageApplication.objects.filter(
            student=request.user,
            status=ApplicationStatus.CONFIRMED,
        ).select_related("offer")

        results = []
        for app in applications:
            try:
                grade = app.grade
            except StageGrade.DoesNotExist:
                continue

            is_finalized = grade.status == StageGradeStatus.FINALIZED
            results.append(StudentStageGradeSchema(
                id=grade.id,
                application_id=app.id,
                offer_title=app.offer.title,
                company_name=app.offer.company_name,
                academic_grade=grade.academic_grade if is_finalized else None,
                academic_grade_comment=grade.academic_grade_comment if is_finalized else "",
                company_grade=grade.company_grade if is_finalized else None,
                company_grade_comment=grade.company_grade_comment if is_finalized else "",
                final_grade=grade.final_grade if is_finalized else None,
                status=grade.status,
            ))

        return 200, results

    @http_get(
        "/period/{period_id}",
        response={200: list[StageGradeSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_grades_by_period",
    )
    def list_grades_by_period(self, request: HttpRequest, period_id: UUID):
        """List grades for a period (encadrant sees own supervised, admin sees all)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(StagePeriod, id=period_id)
        user = request.user
        is_admin = is_stage_admin(user)
        is_encadrant = user_has_role(user, Role.ENCADRANT)

        if not is_admin and not is_encadrant:
            return PermissionDeniedError(
                "Vous n'avez pas acces aux notes de cette periode."
            ).to_response()

        grades = StageGrade.objects.filter(
            stage_period=period,
        ).select_related(
            "application__student",
            "application__offer",
        )

        if not is_admin:
            # Encadrant only sees students they supervise
            grades = grades.filter(application__academic_supervisor=user)

        return 200, [_grade_to_schema(g) for g in grades]

    @http_get(
        "/{application_id}",
        response={200: StageGradeSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_grade_get",
    )
    def get_grade(self, request: HttpRequest, application_id: UUID):
        """Get grade for a stage application."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related(
                "student", "offer", "academic_supervisor"
            ),
            id=application_id,
            status=ApplicationStatus.CONFIRMED,
        )

        # Check permission: student (own), academic_supervisor, offer supervisor, admin
        user = request.user
        is_own = application.student_id == user.id
        is_academic = application.academic_supervisor_id == user.id
        is_company = application.offer.supervisor_id == user.id
        is_admin = is_stage_admin(user)

        if not (is_own or is_academic or is_company or is_admin):
            return PermissionDeniedError(
                "Vous n'avez pas acces a cette note."
            ).to_response()

        grade, _ = StageGrade.objects.get_or_create(
            application=application,
            defaults={"stage_period": application.offer.stage_period},
        )
        # Ensure related objects are loaded
        grade.application = application

        return 200, _grade_to_schema(grade)

    @http_put(
        "/{application_id}/academic",
        response={200: StageGradeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_grade_academic_update",
    )
    def update_academic_grade(
        self, request: HttpRequest, application_id: UUID, data: StageGradeAcademicUpdateSchema
    ):
        """Update academic grade (encadrant or admin)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related(
                "student", "offer", "academic_supervisor"
            ),
            id=application_id,
            status=ApplicationStatus.CONFIRMED,
        )

        # Permission: academic_supervisor or stage admin
        user = request.user
        is_academic = application.academic_supervisor_id == user.id
        is_admin = is_stage_admin(user)

        if not is_academic and not is_admin:
            return PermissionDeniedError(
                "Seul le superviseur academique peut modifier cette note."
            ).to_response()

        grade, _ = StageGrade.objects.get_or_create(
            application=application,
            defaults={"stage_period": application.offer.stage_period},
        )

        if not grade.is_modifiable():
            return BadRequestError(
                "Les notes ont ete finalisees et ne peuvent plus etre modifiees."
            ).to_response()

        grade.academic_grade = data.academic_grade
        grade.academic_grade_comment = data.academic_grade_comment
        grade.academic_graded_by = user
        grade.academic_graded_at = timezone.now()
        if grade.status == StageGradeStatus.DRAFT:
            grade.status = StageGradeStatus.SUBMITTED
        grade.save()

        grade.application = application
        return 200, _grade_to_schema(grade)

    @http_put(
        "/{application_id}/company",
        response={200: StageGradeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_grade_company_update",
    )
    def update_company_grade(
        self, request: HttpRequest, application_id: UUID, data: StageGradeCompanyUpdateSchema
    ):
        """Update company grade (externe supervisor or admin)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related(
                "student", "offer", "academic_supervisor"
            ),
            id=application_id,
            status=ApplicationStatus.CONFIRMED,
        )

        # Permission: offer supervisor (externe) or stage admin
        user = request.user
        is_company = application.offer.supervisor_id == user.id
        is_admin = is_stage_admin(user)

        if not is_company and not is_admin:
            return PermissionDeniedError(
                "Seul le superviseur entreprise peut modifier cette note."
            ).to_response()

        grade, _ = StageGrade.objects.get_or_create(
            application=application,
            defaults={"stage_period": application.offer.stage_period},
        )

        if not grade.is_modifiable():
            return BadRequestError(
                "Les notes ont ete finalisees et ne peuvent plus etre modifiees."
            ).to_response()

        grade.company_grade = data.company_grade
        grade.company_grade_comment = data.company_grade_comment
        grade.company_graded_by = user
        grade.company_graded_at = timezone.now()
        if grade.status == StageGradeStatus.DRAFT:
            grade.status = StageGradeStatus.SUBMITTED
        grade.save()

        grade.application = application
        return 200, _grade_to_schema(grade)

    @http_post(
        "/{application_id}/finalize",
        response={200: StageGradeFinalizeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_grade_finalize",
    )
    def finalize_grade(self, request: HttpRequest, application_id: UUID):
        """Finalize grade (stage admin only, both grades required)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seul l'administrateur peut finaliser les notes."
            ).to_response()

        application = get_object_or_404(
            StageApplication.objects.select_related("student", "offer"),
            id=application_id,
            status=ApplicationStatus.CONFIRMED,
        )

        grade = get_object_or_404(StageGrade, application=application)

        if grade.status == StageGradeStatus.FINALIZED:
            return BadRequestError("Les notes sont deja finalisees.").to_response()

        if grade.academic_grade is None:
            return BadRequestError(
                "La note academique doit etre saisie avant la finalisation."
            ).to_response()

        if grade.company_grade is None:
            return BadRequestError(
                "La note entreprise doit etre saisie avant la finalisation."
            ).to_response()

        grade.compute_final_grade()
        grade.status = StageGradeStatus.FINALIZED
        grade.finalized_at = timezone.now()
        grade.finalized_by = request.user
        grade.save()

        return 200, StageGradeFinalizeSchema(
            success=True,
            message="Les notes ont ete finalisees.",
            finalized_at=grade.finalized_at,
        )
