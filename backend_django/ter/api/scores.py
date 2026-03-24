"""
TER Criterion Score API controller.

Handles assigning actual grades per criterion per group.
"""

from collections import defaultdict
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.groups.models import Group
from backend_django.ter.models import CriterionScore, GradingCriterion, TERPeriod
from backend_django.ter.schemas.scores import (
    BulkScoreSchema,
    CriterionScoreSchema,
    GroupGradeSummarySchema,
)


# ==================== Helper Functions ====================


def _build_score_tree(criteria, scores_by_criterion) -> list[CriterionScoreSchema]:
    """
    Build a nested tree of criteria with scores filled in.
    """
    by_parent = defaultdict(list)
    for c in criteria:
        by_parent[c.parent_id].append(c)

    def _to_schema(criterion) -> CriterionScoreSchema:
        children = by_parent.get(criterion.id, [])
        score_obj = scores_by_criterion.get(criterion.id)
        return CriterionScoreSchema(
            id=criterion.id,
            name=criterion.name,
            coefficient=criterion.coefficient,
            max=criterion.max_score,
            score=score_obj.score if score_obj else None,
            comment=score_obj.comment if score_obj else "",
            sub_grades=[_to_schema(child) for child in children],
        )

    return [_to_schema(root) for root in by_parent.get(None, [])]


def _compute_total(criteria_tree: list[CriterionScoreSchema], max_grade: float = 20) -> float | None:
    """
    Compute weighted total grade from a scored criteria tree.

    For each root criterion:
      - If it has sub_grades: weighted sum of sub_grades scores (normalized to max_grade)
      - If it's a leaf: its own score (normalized to max_grade)
    Then weighted sum of root criteria.
    """

    def _node_score(node: CriterionScoreSchema) -> float | None:
        if node.sub_grades:
            # Weighted sum of children
            total = 0.0
            has_any = False
            for child in node.sub_grades:
                child_score = _node_score(child)
                if child_score is not None:
                    total += child.coefficient * child_score
                    has_any = True
            return total if has_any else None
        else:
            # Leaf: normalize score to 0-1 range
            if node.score is not None and node.max and node.max > 0:
                return node.score / node.max
            return None

    total = 0.0
    has_any = False
    for root in criteria_tree:
        root_score = _node_score(root)
        if root_score is not None:
            total += root.coefficient * root_score
            has_any = True

    if not has_any:
        return None

    return round(total * max_grade, 2)


# ==================== TER Scores Controller ====================


@api_controller("/ter/scores", tags=["TER Grade Scores"], permissions=[IsAuthenticated])
class TERScoresController(BaseAPI):
    """API for assigning grades per criterion per group."""

    @http_get(
        "/{period_id}/{group_id}",
        response={200: GroupGradeSummarySchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_scores_get",
    )
    def get_group_scores(self, request: HttpRequest, period_id: UUID, group_id: UUID):
        """Get all criterion scores for a group, as a tree with computed total."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        group = get_object_or_404(Group, id=group_id, ter_period=period)

        criteria = GradingCriterion.objects.filter(ter_period=period).order_by("order", "created")
        scores = CriterionScore.objects.filter(
            grading_criterion__ter_period=period, group=group
        ).select_related("grading_criterion")

        scores_by_criterion = {s.grading_criterion_id: s for s in scores}
        tree = _build_score_tree(criteria, scores_by_criterion)
        total = _compute_total(tree)

        return 200, GroupGradeSummarySchema(
            group_id=group.id,
            group_name=group.name,
            total_grade=total,
            max_grade=20,
            criteria=tree,
        )

    @http_put(
        "/{period_id}/{group_id}",
        response={200: GroupGradeSummarySchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_scores_save",
    )
    def save_group_scores(
        self, request: HttpRequest, period_id: UUID, group_id: UUID, payload: BulkScoreSchema
    ):
        """Bulk save criterion scores for a group."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        group = get_object_or_404(Group, id=group_id, ter_period=period)

        # Permission: ter admin or encadrant of the group's subject
        user = request.user
        can_grade = is_ter_admin(user)
        if not can_grade and hasattr(group, "assigned_subject") and group.assigned_subject:
            subject = group.assigned_subject
            if subject.professor_id == user.id or getattr(subject, "supervisor_id", None) == user.id:
                can_grade = True
        if not can_grade:
            return PermissionDeniedError().to_response()

        # Validate and save scores
        criterion_ids = {s.criterion_id for s in payload.scores}
        criteria = GradingCriterion.objects.filter(
            id__in=criterion_ids, ter_period=period
        )
        criteria_map = {c.id: c for c in criteria}

        for score_input in payload.scores:
            criterion = criteria_map.get(score_input.criterion_id)
            if not criterion:
                return BadRequestError(
                    message=f"Critère {score_input.criterion_id} introuvable."
                ).to_response()

            max_score = criterion.max_score or 20
            if score_input.score < 0 or score_input.score > max_score:
                return BadRequestError(
                    message=f'Note pour "{criterion.name}" doit être entre 0 et {max_score}.'
                ).to_response()

            CriterionScore.objects.update_or_create(
                grading_criterion=criterion,
                group=group,
                defaults={
                    "score": score_input.score,
                    "comment": score_input.comment,
                    "graded_by": user,
                },
            )

        # Return updated tree
        all_criteria = GradingCriterion.objects.filter(ter_period=period).order_by("order", "created")
        scores = CriterionScore.objects.filter(
            grading_criterion__ter_period=period, group=group
        ).select_related("grading_criterion")

        scores_by_criterion = {s.grading_criterion_id: s for s in scores}
        tree = _build_score_tree(all_criteria, scores_by_criterion)
        total = _compute_total(tree)

        return 200, GroupGradeSummarySchema(
            group_id=group.id,
            group_name=group.name,
            total_grade=total,
            max_grade=20,
            criteria=tree,
        )

    @http_get(
        "/{period_id}/summary",
        response={200: list[GroupGradeSummarySchema], 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_scores_summary",
    )
    def get_all_scores(self, request: HttpRequest, period_id: UUID):
        """Get grade summaries for all groups in a period."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        groups = Group.objects.filter(ter_period=period).order_by("name")
        criteria = list(GradingCriterion.objects.filter(ter_period=period).order_by("order", "created"))
        all_scores = CriterionScore.objects.filter(
            grading_criterion__ter_period=period
        ).select_related("grading_criterion")

        # Group scores by group_id
        scores_by_group = defaultdict(dict)
        for s in all_scores:
            scores_by_group[s.group_id][s.grading_criterion_id] = s

        result = []
        for group in groups:
            tree = _build_score_tree(criteria, scores_by_group.get(group.id, {}))
            total = _compute_total(tree)
            result.append(GroupGradeSummarySchema(
                group_id=group.id,
                group_name=group.name,
                total_grade=total,
                max_grade=20,
                criteria=tree,
            ))

        return 200, result
