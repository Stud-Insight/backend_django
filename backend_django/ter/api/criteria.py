"""
TER Grading Criteria API controller.

Manages the grading canvas (hierarchical evaluation criteria templates)
for TER periods.
"""

from collections import defaultdict
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_delete, http_get, http_post, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.ter.models import GradingCriterion, TERPeriod
from backend_django.ter.schemas.criteria import (
    BulkReorderSchema,
    GradingCriterionAddSubSchema,
    GradingCriterionCreateSchema,
    GradingCriterionSchema,
    GradingCriterionUpdateSchema,
)


# ==================== Helper Functions ====================


def _build_tree(criteria) -> list[GradingCriterionSchema]:
    """
    Build a nested tree from a flat queryset of GradingCriterion.

    Groups criteria by parent_id, then recursively builds the tree
    starting from root nodes (parent_id=None).
    """
    by_parent = defaultdict(list)
    for c in criteria:
        by_parent[c.parent_id].append(c)

    def _to_schema(criterion) -> GradingCriterionSchema:
        children = by_parent.get(criterion.id, [])
        return GradingCriterionSchema(
            id=criterion.id,
            ter_period_id=criterion.ter_period_id,
            name=criterion.name,
            coefficient=criterion.coefficient,
            max=criterion.max_score,
            sub_grades=[_to_schema(child) for child in children],
        )

    return [_to_schema(root) for root in by_parent.get(None, [])]


def _check_siblings_sum(ter_period, parent, new_coefficient: float, exclude_id=None):
    """
    Check that adding new_coefficient to existing siblings doesn't exceed 1.0.

    Returns None if OK, or a BadRequestError response tuple if exceeded.
    """
    siblings = GradingCriterion.objects.filter(ter_period=ter_period, parent=parent)
    if exclude_id:
        siblings = siblings.exclude(id=exclude_id)
    current_sum = sum(s.coefficient for s in siblings)
    total = round(current_sum + new_coefficient, 10)  # avoid float precision issues
    if total > 1.0:
        pct_current = round(current_sum * 100)
        pct_new = round(new_coefficient * 100)
        return BadRequestError(
            message=f"La somme des coefficients dépasserait 100% ({pct_current}% existants + {pct_new}% = {pct_current + pct_new}%)."
        ).to_response()
    return None


# ==================== TER Criteria Controller ====================


@api_controller("/ter/criteria", tags=["TER Grading Criteria"], permissions=[IsAuthenticated])
class TERCriteriaController(BaseAPI):
    """API for managing TER grading criteria (canvas de notation)."""

    @http_get(
        "/{period_id}",
        response={200: list[GradingCriterionSchema], 401: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_list",
    )
    def list_criteria(self, request: HttpRequest, period_id: UUID):
        """List all grading criteria for a TER period as a nested tree."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        criteria = GradingCriterion.objects.filter(ter_period=period).order_by("order", "created")
        return 200, _build_tree(criteria)

    @http_post(
        "/{period_id}",
        response={201: GradingCriterionSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_create",
    )
    def create_root_criterion(
        self, request: HttpRequest, period_id: UUID, payload: GradingCriterionCreateSchema
    ):
        """Create a root-level grading criterion."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        # Check coefficient sum won't exceed 100%
        error = _check_siblings_sum(period, None, payload.coefficient)
        if error:
            return error

        # Auto-assign order: next after existing root criteria
        max_order = (
            GradingCriterion.objects.filter(ter_period=period, parent=None)
            .order_by("-order")
            .values_list("order", flat=True)
            .first()
        )
        next_order = (max_order or 0) + 1

        criterion = GradingCriterion.objects.create(
            ter_period=period,
            parent=None,
            name=payload.name,
            coefficient=payload.coefficient,
            max_score=payload.max_score,
            order=next_order,
        )

        return 201, GradingCriterionSchema(
            id=criterion.id,
            ter_period_id=criterion.ter_period_id,
            name=criterion.name,
            coefficient=criterion.coefficient,
            max=criterion.max_score,
            sub_grades=[],
        )

    @http_post(
        "/{period_id}/{parent_id}/sub",
        response={201: GradingCriterionSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_create_sub",
    )
    def create_sub_criterion(
        self,
        request: HttpRequest,
        period_id: UUID,
        parent_id: UUID,
        payload: GradingCriterionAddSubSchema,
    ):
        """Create a sub-criterion under a parent criterion."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)
        parent = get_object_or_404(GradingCriterion, id=parent_id, ter_period=period)

        # Check coefficient sum won't exceed 100%
        error = _check_siblings_sum(period, parent, payload.coefficient)
        if error:
            return error

        # Auto-assign order: next after existing children
        max_order = (
            GradingCriterion.objects.filter(parent=parent)
            .order_by("-order")
            .values_list("order", flat=True)
            .first()
        )
        next_order = (max_order or 0) + 1

        criterion = GradingCriterion.objects.create(
            ter_period=period,
            parent=parent,
            name=payload.name,
            coefficient=payload.coefficient,
            max_score=payload.max_score,
            order=next_order,
        )

        return 201, GradingCriterionSchema(
            id=criterion.id,
            ter_period_id=criterion.ter_period_id,
            name=criterion.name,
            coefficient=criterion.coefficient,
            max=criterion.max_score,
            sub_grades=[],
        )

    @http_put(
        "/detail/{criterion_id}",
        response={200: GradingCriterionSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_update",
    )
    def update_criterion(
        self, request: HttpRequest, criterion_id: UUID, payload: GradingCriterionUpdateSchema
    ):
        """Update a grading criterion."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        criterion = get_object_or_404(GradingCriterion, id=criterion_id)

        # Only validate coefficient sum when the coefficient itself is being changed
        # (not when just moving between parents — user adjusts coefficients after regrouping)
        if payload.coefficient is not None:
            target_parent = criterion.parent
            if payload.remove_parent:
                target_parent = None
            elif payload.parent_id is not None:
                target_parent = get_object_or_404(
                    GradingCriterion, id=payload.parent_id, ter_period=criterion.ter_period
                )
            error = _check_siblings_sum(
                criterion.ter_period, target_parent, payload.coefficient, exclude_id=criterion.id
            )
            if error:
                return error

        if payload.name is not None:
            criterion.name = payload.name
        if payload.coefficient is not None:
            criterion.coefficient = payload.coefficient
        if payload.max_score is not None:
            criterion.max_score = payload.max_score
        if payload.order is not None:
            criterion.order = payload.order
        if payload.remove_parent:
            criterion.parent = None
        elif payload.parent_id is not None:
            if payload.parent_id == criterion.id:
                return BadRequestError(message="Un critère ne peut pas être son propre parent.").to_response()
            parent = get_object_or_404(
                GradingCriterion, id=payload.parent_id, ter_period=criterion.ter_period
            )
            criterion.parent = parent

        criterion.save()

        # Return with children
        children = GradingCriterion.objects.filter(parent=criterion).order_by("order", "created")
        sub_grades = [
            GradingCriterionSchema(
                id=c.id,
                ter_period_id=c.ter_period_id,
                name=c.name,
                coefficient=c.coefficient,
                max=c.max_score,
                sub_grades=[],
            )
            for c in children
        ]

        return 200, GradingCriterionSchema(
            id=criterion.id,
            ter_period_id=criterion.ter_period_id,
            name=criterion.name,
            coefficient=criterion.coefficient,
            max=criterion.max_score,
            sub_grades=sub_grades,
        )

    @http_delete(
        "/detail/{criterion_id}",
        response={204: None, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_delete",
    )
    def delete_criterion(self, request: HttpRequest, criterion_id: UUID):
        """Delete a grading criterion (cascades to children)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        criterion = get_object_or_404(GradingCriterion, id=criterion_id)
        criterion.delete()
        return 204, None

    @http_put(
        "/{period_id}/reorder",
        response={200: list[GradingCriterionSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_reorder",
    )
    def reorder_criteria(
        self, request: HttpRequest, period_id: UUID, payload: BulkReorderSchema
    ):
        """Bulk reorder criteria (drag & drop support)."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        period = get_object_or_404(TERPeriod, id=period_id)

        for item in payload.items:
            GradingCriterion.objects.filter(id=item.id, ter_period=period).update(
                order=item.order,
                parent_id=item.parent_id,
            )

        criteria = GradingCriterion.objects.filter(ter_period=period).order_by("order", "created")
        return 200, _build_tree(criteria)

    @http_post(
        "/{target_period_id}/clone-from/{source_period_id}",
        response={201: list[GradingCriterionSchema], 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_criteria_clone",
    )
    def clone_criteria(
        self, request: HttpRequest, target_period_id: UUID, source_period_id: UUID
    ):
        """Clone all grading criteria from one period to another."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()
        if not is_ter_admin(request.user):
            return PermissionDeniedError().to_response()

        target = get_object_or_404(TERPeriod, id=target_period_id)
        source = get_object_or_404(TERPeriod, id=source_period_id)

        if target.id == source.id:
            return BadRequestError(message="Impossible de cloner depuis la même période.").to_response()

        if GradingCriterion.objects.filter(ter_period=target).exists():
            return BadRequestError(
                message="La période cible contient déjà des critères. Supprimez-les d'abord."
            ).to_response()

        source_list = list(
            GradingCriterion.objects.filter(ter_period=source)
            .order_by("order", "created")
            .values("id", "parent_id", "name", "coefficient", "order", "max_score")
        )

        if not source_list:
            return BadRequestError(message="La période source n'a aucun critère.").to_response()

        # First pass: create all without parents
        id_map = {}
        for item in source_list:
            new_c = GradingCriterion.objects.create(
                ter_period=target,
                parent=None,
                name=item["name"],
                coefficient=item["coefficient"],
                order=item["order"],
                max_score=item["max_score"],
            )
            id_map[item["id"]] = new_c

        # Second pass: set parent references
        for item in source_list:
            if item["parent_id"] and item["parent_id"] in id_map:
                new_c = id_map[item["id"]]
                new_c.parent = id_map[item["parent_id"]]
                new_c.save(update_fields=["parent"])

        cloned = GradingCriterion.objects.filter(ter_period=target).order_by("order", "created")
        return 201, _build_tree(cloned)
