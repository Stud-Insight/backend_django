"""
TER Grading API controller.

Handles group grades, individual grades, and peer reviews.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
from backend_django.groups.models import Group
from backend_django.ter.models import (
    GradeStatus,
    PeerReview,
    PeerReviewSession,
    TERGrade,
    TERIndividualGrade,
    TERPeriod,
)
from backend_django.ter.schemas.grading import (
    GradeExportSchema,
    GradeFinalizeSchema,
    PeerReviewAggregateSchema,
    PeerReviewCreateSchema,
    PeerReviewSchema,
    PeerReviewSessionSchema,
    StudentOptInSchema,
    TERGradeCreateSchema,
    TERGradeSchema,
    TERGradeUpdateSchema,
    TERIndividualGradeSchema,
    TERIndividualGradeUpdateSchema,
)


def is_encadrant_for_group(user, group: Group) -> bool:
    """Check if user is encadrant (professor/supervisor) for the group's subject."""
    if hasattr(group, "assigned_subject") and group.assigned_subject:
        subject = group.assigned_subject
        return subject.professor_id == user.id or subject.supervisor_id == user.id
    return False


@api_controller("/ter/grades", tags=["TER Grading"], permissions=[IsAuthenticated])
class TERGradingController(BaseAPI):
    """API endpoints for TER grading (group grades, individual grades)."""

    @http_get(
        "/group/{group_id}",
        response={200: TERGradeSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_grade_get",
    )
    def get_group_grade(self, request: HttpRequest, group_id: UUID):
        """Get grade for a group."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission
        is_member = group.members.filter(id=request.user.id).exists()
        is_encadrant = is_encadrant_for_group(request.user, group)
        is_admin = is_ter_admin(request.user)

        if not is_member and not is_encadrant and not is_admin:
            return PermissionDeniedError(
                "Vous n'avez pas accès aux notes de ce groupe."
            ).to_response()

        # Get or create grade record
        grade, _ = TERGrade.objects.get_or_create(
            group=group,
            defaults={
                "ter_period": group.ter_period,
            },
        )

        return 200, TERGradeSchema(
            id=grade.id,
            ter_period_id=grade.ter_period_id,
            group_id=grade.group_id,
            graded_by_id=grade.graded_by_id,
            group_grade=grade.group_grade,
            group_grade_comment=grade.group_grade_comment,
            individual_grading_enabled=grade.individual_grading_enabled,
            status=grade.status,
            finalized_at=grade.finalized_at,
            finalized_by_id=grade.finalized_by_id,
            created=grade.created,
            modified=grade.modified,
        )

    @http_put(
        "/group/{group_id}",
        response={200: TERGradeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_grade_update",
    )
    def update_group_grade(
        self, request: HttpRequest, group_id: UUID, data: TERGradeUpdateSchema
    ):
        """Update grade for a group (encadrant only)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission
        is_encadrant = is_encadrant_for_group(request.user, group)
        is_admin = is_ter_admin(request.user)

        if not is_encadrant and not is_admin:
            return PermissionDeniedError(
                "Seul l'encadrant peut modifier les notes."
            ).to_response()

        # Get or create grade record
        grade, _ = TERGrade.objects.get_or_create(
            group=group,
            defaults={
                "ter_period": group.ter_period,
            },
        )

        # Check if grade is modifiable
        if not grade.is_modifiable():
            return BadRequestError(
                "Les notes ont été finalisées et ne peuvent plus être modifiées."
            ).to_response()

        # Update fields
        if data.group_grade is not None:
            grade.group_grade = data.group_grade
        if data.group_grade_comment is not None:
            grade.group_grade_comment = data.group_grade_comment
        if data.individual_grading_enabled is not None:
            grade.individual_grading_enabled = data.individual_grading_enabled

        grade.graded_by = request.user
        grade.status = GradeStatus.SUBMITTED
        grade.save()

        # Create individual grade records for all group members if not exist
        for member in group.members.all():
            TERIndividualGrade.objects.get_or_create(
                grade=grade,
                student=member,
            )

        return 200, TERGradeSchema(
            id=grade.id,
            ter_period_id=grade.ter_period_id,
            group_id=grade.group_id,
            graded_by_id=grade.graded_by_id,
            group_grade=grade.group_grade,
            group_grade_comment=grade.group_grade_comment,
            individual_grading_enabled=grade.individual_grading_enabled,
            status=grade.status,
            finalized_at=grade.finalized_at,
            finalized_by_id=grade.finalized_by_id,
            created=grade.created,
            modified=grade.modified,
        )

    @http_get(
        "/group/{group_id}/individual",
        response={200: list[TERIndividualGradeSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_individual_grades_list",
    )
    def list_individual_grades(self, request: HttpRequest, group_id: UUID):
        """List all individual grades for a group (encadrant only)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission
        is_encadrant = is_encadrant_for_group(request.user, group)
        is_admin = is_ter_admin(request.user)

        if not is_encadrant and not is_admin:
            return PermissionDeniedError(
                "Seul l'encadrant peut voir les notes individuelles."
            ).to_response()

        grade = get_object_or_404(TERGrade, group=group)
        individual_grades = TERIndividualGrade.objects.filter(grade=grade).select_related("student")

        return 200, [
            TERIndividualGradeSchema(
                id=ig.id,
                grade_id=ig.grade_id,
                student_id=ig.student_id,
                student_email=ig.student.email,
                student_name=f"{ig.student.first_name} {ig.student.last_name}".strip() or ig.student.email,
                opted_in=ig.opted_in,
                opted_in_at=ig.opted_in_at,
                individual_grade=ig.individual_grade,
                individual_grade_comment=ig.individual_grade_comment,
                final_grade=ig.final_grade,
            )
            for ig in individual_grades
        ]

    @http_put(
        "/individual/{individual_grade_id}",
        response={200: TERIndividualGradeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_individual_grade_update",
    )
    def update_individual_grade(
        self, request: HttpRequest, individual_grade_id: UUID, data: TERIndividualGradeUpdateSchema
    ):
        """Update an individual grade (encadrant only)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        individual_grade = get_object_or_404(
            TERIndividualGrade.objects.select_related("grade__group", "student"),
            id=individual_grade_id,
        )

        group = individual_grade.grade.group

        # Check permission
        is_encadrant = is_encadrant_for_group(request.user, group)
        is_admin = is_ter_admin(request.user)

        if not is_encadrant and not is_admin:
            return PermissionDeniedError(
                "Seul l'encadrant peut modifier les notes individuelles."
            ).to_response()

        # Check if grade is modifiable
        if not individual_grade.grade.is_modifiable():
            return BadRequestError(
                "Les notes ont été finalisées et ne peuvent plus être modifiées."
            ).to_response()

        # Check if individual grading is enabled
        if not individual_grade.grade.individual_grading_enabled:
            return BadRequestError(
                "La notation individuelle n'est pas activée pour ce groupe."
            ).to_response()

        # Check if student opted in
        if not individual_grade.opted_in:
            return BadRequestError(
                "L'étudiant n'a pas opté pour la notation individuelle."
            ).to_response()

        # Update fields
        if data.individual_grade is not None:
            individual_grade.individual_grade = data.individual_grade
        if data.individual_grade_comment is not None:
            individual_grade.individual_grade_comment = data.individual_grade_comment

        individual_grade.compute_final_grade()
        individual_grade.save()

        return 200, TERIndividualGradeSchema(
            id=individual_grade.id,
            grade_id=individual_grade.grade_id,
            student_id=individual_grade.student_id,
            student_email=individual_grade.student.email,
            student_name=f"{individual_grade.student.first_name} {individual_grade.student.last_name}".strip() or individual_grade.student.email,
            opted_in=individual_grade.opted_in,
            opted_in_at=individual_grade.opted_in_at,
            individual_grade=individual_grade.individual_grade,
            individual_grade_comment=individual_grade.individual_grade_comment,
            final_grade=individual_grade.final_grade,
        )

    @http_post(
        "/group/{group_id}/opt-in",
        response={200: StudentOptInSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_grade_opt_in",
    )
    def student_opt_in(self, request: HttpRequest, group_id: UUID):
        """Student opts in for individual grading."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check user is a member
        if not group.members.filter(id=request.user.id).exists():
            return PermissionDeniedError(
                "Vous devez être membre du groupe."
            ).to_response()

        # Get grade record
        grade = get_object_or_404(TERGrade, group=group)

        # Check if individual grading is enabled
        if not grade.individual_grading_enabled:
            return BadRequestError(
                "La notation individuelle n'est pas activée pour ce groupe."
            ).to_response()

        # Check if grade is modifiable
        if not grade.is_modifiable():
            return BadRequestError(
                "Les notes ont été finalisées."
            ).to_response()

        # Get or create individual grade record
        individual_grade, _ = TERIndividualGrade.objects.get_or_create(
            grade=grade,
            student=request.user,
        )

        if individual_grade.opted_in:
            return 200, StudentOptInSchema(
                success=True,
                message="Vous êtes déjà inscrit pour la notation individuelle.",
                opted_in=True,
                opted_in_at=individual_grade.opted_in_at,
            )

        individual_grade.opted_in = True
        individual_grade.opted_in_at = timezone.now()
        individual_grade.save()

        return 200, StudentOptInSchema(
            success=True,
            message="Vous êtes maintenant inscrit pour la notation individuelle.",
            opted_in=True,
            opted_in_at=individual_grade.opted_in_at,
        )

    @http_post(
        "/group/{group_id}/finalize",
        response={200: GradeFinalizeSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_grade_finalize",
    )
    def finalize_grades(self, request: HttpRequest, group_id: UUID):
        """Finalize grades for a group (prevents further modifications)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission (admin only can finalize)
        if not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Seul l'administrateur peut finaliser les notes."
            ).to_response()

        grade = get_object_or_404(TERGrade, group=group)

        if grade.status == GradeStatus.FINALIZED:
            return BadRequestError(
                "Les notes sont déjà finalisées."
            ).to_response()

        if grade.group_grade is None:
            return BadRequestError(
                "La note de groupe doit être saisie avant la finalisation."
            ).to_response()

        # Compute final grades for all members
        for individual_grade in grade.individual_grades.all():
            individual_grade.compute_final_grade()
            individual_grade.save()

        # Finalize
        grade.status = GradeStatus.FINALIZED
        grade.finalized_at = timezone.now()
        grade.finalized_by = request.user
        grade.save()

        return 200, GradeFinalizeSchema(
            success=True,
            message="Les notes ont été finalisées.",
            finalized_at=grade.finalized_at,
        )

    @http_get(
        "/my-grade",
        response={200: TERIndividualGradeSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_my_grade",
    )
    def get_my_grade(self, request: HttpRequest, period_id: UUID | None = None):
        """Get current user's grade for their group."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Find user's group
        groups_query = Group.objects.filter(members=request.user)
        if period_id:
            groups_query = groups_query.filter(ter_period_id=period_id)

        group = groups_query.first()
        if not group:
            return NotFoundError("Vous n'êtes membre d'aucun groupe.").to_response()

        try:
            grade = TERGrade.objects.get(group=group)
            individual_grade = TERIndividualGrade.objects.get(
                grade=grade,
                student=request.user,
            )
        except (TERGrade.DoesNotExist, TERIndividualGrade.DoesNotExist):
            return NotFoundError("Aucune note disponible.").to_response()

        return 200, TERIndividualGradeSchema(
            id=individual_grade.id,
            grade_id=individual_grade.grade_id,
            student_id=individual_grade.student_id,
            student_email=individual_grade.student.email,
            student_name=f"{individual_grade.student.first_name} {individual_grade.student.last_name}".strip() or individual_grade.student.email,
            opted_in=individual_grade.opted_in,
            opted_in_at=individual_grade.opted_in_at,
            individual_grade=individual_grade.individual_grade if grade.status == GradeStatus.FINALIZED else None,
            individual_grade_comment=individual_grade.individual_grade_comment if grade.status == GradeStatus.FINALIZED else "",
            final_grade=individual_grade.final_grade if grade.status == GradeStatus.FINALIZED else None,
        )


@api_controller("/ter/peer-reviews", tags=["TER Peer Review"], permissions=[IsAuthenticated])
class TERPeerReviewController(BaseAPI):
    """API endpoints for anonymous peer reviews."""

    @http_get(
        "/session",
        response={200: PeerReviewSessionSchema, 400: ErrorSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_peer_review_session",
    )
    def get_or_create_session(self, request: HttpRequest, period_id: UUID | None = None):
        """Get or create a peer review session with ephemeral token."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Find user's group
        groups_query = Group.objects.filter(members=request.user)
        if period_id:
            groups_query = groups_query.filter(ter_period_id=period_id)

        group = groups_query.first()
        if not group:
            return NotFoundError("Vous n'êtes membre d'aucun groupe.").to_response()

        if not group.ter_period:
            return BadRequestError("Le groupe n'est pas associé à une période TER.").to_response()

        # Get or create session
        # Convert project_end (date) to datetime at end of day + 7 days
        project_end_dt = datetime.combine(
            group.ter_period.project_end,
            datetime.max.time(),
            tzinfo=dt_timezone.utc,
        )
        session, created = PeerReviewSession.objects.get_or_create(
            ter_period=group.ter_period,
            student=request.user,
            defaults={
                "group": group,
                "expires_at": project_end_dt + timedelta(days=7),
            },
        )

        # Check if expired
        if session.expires_at < timezone.now():
            return BadRequestError("La période de peer review est terminée.").to_response()

        # Get members to review (excluding self)
        members = group.members.exclude(id=request.user.id)
        members_to_review = [
            {
                "id": str(m.id),
                "email": m.email,
                "name": f"{m.first_name} {m.last_name}".strip() or m.email,
            }
            for m in members
        ]

        # Get already reviewed members
        already_reviewed = list(
            PeerReview.objects.filter(
                group=group,
                reviewer_token=str(session.ephemeral_token),
            ).values_list("reviewed_student_id", flat=True)
        )

        return 200, PeerReviewSessionSchema(
            ephemeral_token=session.ephemeral_token,
            group_id=group.id,
            group_name=group.name,
            expires_at=session.expires_at,
            members_to_review=members_to_review,
            already_reviewed=already_reviewed,
        )

    @http_post(
        "/submit",
        response={201: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="ter_peer_review_submit",
    )
    def submit_peer_review(self, request: HttpRequest, data: PeerReviewCreateSchema):
        """Submit a peer review for a group member."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Get user's session
        session = PeerReviewSession.objects.filter(
            student=request.user,
        ).first()

        if not session:
            return BadRequestError("Aucune session de peer review active.").to_response()

        if session.expires_at < timezone.now():
            return BadRequestError("La période de peer review est terminée.").to_response()

        # Verify reviewed student is in the same group
        if not session.group.members.filter(id=data.reviewed_student_id).exists():
            return BadRequestError("L'étudiant à évaluer n'est pas dans votre groupe.").to_response()

        # Cannot review self
        if data.reviewed_student_id == request.user.id:
            return BadRequestError("Vous ne pouvez pas vous auto-évaluer.").to_response()

        # Check if already reviewed
        if PeerReview.objects.filter(
            group=session.group,
            reviewer_token=str(session.ephemeral_token),
            reviewed_student_id=data.reviewed_student_id,
        ).exists():
            return BadRequestError("Vous avez déjà évalué cet étudiant.").to_response()

        # Create review
        PeerReview.objects.create(
            ter_period=session.ter_period,
            group=session.group,
            reviewer_token=str(session.ephemeral_token),
            reviewed_student_id=data.reviewed_student_id,
            contribution_score=data.contribution_score,
            collaboration_score=data.collaboration_score,
            technical_skill_score=data.technical_skill_score,
            comment=data.comment,
        )

        return 201, {"success": True, "message": "Evaluation soumise avec succès."}

    @http_get(
        "/group/{group_id}/aggregate",
        response={200: list[PeerReviewAggregateSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_peer_review_aggregate",
    )
    def get_aggregated_reviews(self, request: HttpRequest, group_id: UUID):
        """Get aggregated peer review scores for a group (encadrant only)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permission
        is_encadrant = is_encadrant_for_group(request.user, group)
        is_admin = is_ter_admin(request.user)

        if not is_encadrant and not is_admin:
            return PermissionDeniedError(
                "Seul l'encadrant peut voir les évaluations."
            ).to_response()

        # Get all reviews for the group
        reviews = PeerReview.objects.filter(group=group).select_related("reviewed_student")

        # Aggregate by reviewed student
        aggregates = {}
        for review in reviews:
            student_id = review.reviewed_student_id
            if student_id not in aggregates:
                aggregates[student_id] = {
                    "student": review.reviewed_student,
                    "contribution_scores": [],
                    "collaboration_scores": [],
                    "technical_scores": [],
                    "comments": [],
                }
            aggregates[student_id]["contribution_scores"].append(review.contribution_score)
            aggregates[student_id]["collaboration_scores"].append(review.collaboration_score)
            aggregates[student_id]["technical_scores"].append(review.technical_skill_score)
            if review.comment:
                aggregates[student_id]["comments"].append(review.comment)

        result = []
        for student_id, data in aggregates.items():
            student = data["student"]
            avg_contrib = sum(data["contribution_scores"]) / len(data["contribution_scores"]) if data["contribution_scores"] else 0
            avg_collab = sum(data["collaboration_scores"]) / len(data["collaboration_scores"]) if data["collaboration_scores"] else 0
            avg_tech = sum(data["technical_scores"]) / len(data["technical_scores"]) if data["technical_scores"] else 0
            overall = (avg_contrib + avg_collab + avg_tech) / 3 if data["contribution_scores"] else 0

            result.append(
                PeerReviewAggregateSchema(
                    student_id=student_id,
                    student_email=student.email,
                    student_name=f"{student.first_name} {student.last_name}".strip() or student.email,
                    review_count=len(data["contribution_scores"]),
                    avg_contribution=round(avg_contrib, 2),
                    avg_collaboration=round(avg_collab, 2),
                    avg_technical_skill=round(avg_tech, 2),
                    overall_average=round(overall, 2),
                    comments=data["comments"],
                )
            )

        return 200, result
