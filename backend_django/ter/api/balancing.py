"""
TER Group Balancing API controller.

Provides endpoints for Respo TER to manage group balancing operations:
- Preview balancing effects
- Run automatic balancing
- Move students between groups
- Merge groups
- Force-assign subjects
- Revert assignments
- Force-form groups
"""

from uuid import UUID

from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get, http_post

from backend_django.algorithms.balancing import (
    add_student_to_group,
    identify_problematic_entities,
    merge_groups as merge_groups_algo,
    preview_balancing,
    run_balancing,
)
from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.core.schemas import paginate_queryset
from backend_django.groups.models import Group, GroupInvitation, GroupStatus, InvitationStatus
from backend_django.ter.models import (
    BalancingOperation,
    BalancingOperationType,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.ter.schemas.balancing import (
    BalanceGroupsRequestSchema,
    BalanceGroupsResponseSchema,
    BalancingOperationListSchema,
    BalancingOperationSchema,
    BalancingPreviewSchema,
    ForceAssignRequestSchema,
    ForceFormRequestSchema,
    MergeGroupsRequestSchema,
    MergeOperationSchema,
    MoveStudentRequestSchema,
    RevertAssignmentRequestSchema,
)
from backend_django.users.models import User


# ==================== Helper Functions ====================


def _check_ter_admin(request: HttpRequest):
    """Check if user is TER admin, return error response if not."""
    if not request.user.is_authenticated:
        return NotAuthenticatedError().to_response()
    if not is_ter_admin(request.user):
        return PermissionDeniedError(
            "Seuls les responsables TER peuvent effectuer cette operation."
        ).to_response()
    return None


def _log_operation(
    period: TERPeriod,
    operation_type: str,
    user: User,
    details: dict,
    reason: str = "",
    is_automatic: bool = False,
) -> BalancingOperation:
    """Log a balancing operation to the audit trail."""
    return BalancingOperation.objects.create(
        ter_period=period,
        operation_type=operation_type,
        performed_by=user if not is_automatic else None,
        details=details,
        is_automatic=is_automatic,
        reason=reason,
    )


def _operation_to_schema(op: BalancingOperation) -> BalancingOperationSchema:
    """Convert BalancingOperation to schema."""
    return BalancingOperationSchema(
        id=op.id,
        ter_period_id=op.ter_period_id,
        operation_type=op.operation_type,
        performed_by_id=op.performed_by_id,
        performed_by_email=op.performed_by.email if op.performed_by else None,
        details=op.details,
        is_automatic=op.is_automatic,
        reason=op.reason,
        created=str(op.created),
    )


# ==================== Balancing Controller ====================


@api_controller("/ter/periods", tags=["TER Balancing"], permissions=[IsAuthenticated])
class TERBalancingController(BaseAPI):
    """API for TER group balancing operations (Respo TER only)."""

    # ==================== Preview & Auto-Balance ====================

    @http_get(
        "/{period_id}/balancing-preview",
        response={200: BalancingPreviewSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_balancing_preview",
    )
    def get_balancing_preview(self, request: HttpRequest, period_id: UUID):
        """
        Preview what the balancing algorithm would do.

        Returns counts of problematic entities and sample potential matches.
        Does not make any changes.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)
        preview = preview_balancing(period)

        return 200, BalancingPreviewSchema(**preview)

    @http_post(
        "/{period_id}/balance-groups",
        response={200: BalanceGroupsResponseSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_balance_groups",
    )
    def balance_groups(
        self, request: HttpRequest, period_id: UUID, data: BalanceGroupsRequestSchema
    ):
        """
        Run the automatic group balancing algorithm.

        This will:
        - Merge solo students into incomplete groups (by preference similarity)
        - Merge solo groups together
        - Fill remaining gaps round-robin
        - Auto-form groups meeting min_group_size

        Use dry_run=true to preview without making changes.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        result = run_balancing(
            period,
            merge_solo_students=data.merge_solo_students,
            merge_incomplete_groups=data.merge_incomplete_groups,
            auto_form_groups=data.auto_form_groups,
            dry_run=data.dry_run,
        )

        # Log operations if not dry run
        if not data.dry_run and result.operations:
            for op in result.operations:
                _log_operation(
                    period=period,
                    operation_type=op.operation_type,
                    user=request.user,
                    details={
                        "entity_a_id": str(op.entity_a_id),
                        "entity_b_id": str(op.entity_b_id),
                        "similarity_score": op.similarity_score,
                    },
                    reason=op.reason,
                    is_automatic=True,
                )

        return 200, BalanceGroupsResponseSchema(
            success=result.success,
            message=result.message,
            operations=[
                MergeOperationSchema(
                    operation_type=op.operation_type,
                    entity_a_id=op.entity_a_id,
                    entity_b_id=op.entity_b_id,
                    similarity_score=op.similarity_score,
                    reason=op.reason,
                )
                for op in result.operations
            ],
            students_assigned=result.students_assigned,
            groups_merged=result.groups_merged,
            groups_auto_formed=result.groups_auto_formed,
            warnings=result.warnings,
            remaining_solo_students=result.remaining_solo_students,
            remaining_incomplete_groups=result.remaining_incomplete_groups,
        )

    # ==================== Manual Operations ====================

    @http_post(
        "/{period_id}/groups/move-student",
        response={200: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_move_student",
    )
    def move_student(
        self, request: HttpRequest, period_id: UUID, data: MoveStudentRequestSchema
    ):
        """
        Move a student between groups or add a solo student to a group.

        If source_group_id is provided, removes student from that group first.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        # Validate student exists
        try:
            student = User.objects.get(id=data.student_id)
        except User.DoesNotExist:
            return NotFoundError("Etudiant introuvable.").to_response()

        # Validate target group
        try:
            target_group = Group.objects.get(id=data.target_group_id, ter_period=period)
        except Group.DoesNotExist:
            return NotFoundError("Groupe cible introuvable.").to_response()

        # Check max_group_size
        if target_group.member_count >= period.max_group_size:
            return BadRequestError(
                f"Le groupe cible a atteint la taille maximale ({period.max_group_size})."
            ).to_response()

        with transaction.atomic():
            source_group = None

            # Remove from source group if specified
            if data.source_group_id:
                try:
                    source_group = Group.objects.select_for_update().get(
                        id=data.source_group_id, ter_period=period
                    )
                except Group.DoesNotExist:
                    return NotFoundError("Groupe source introuvable.").to_response()

                if not source_group.members.filter(id=student.id).exists():
                    return BadRequestError(
                        "L'etudiant n'est pas membre du groupe source."
                    ).to_response()

                if source_group.leader_id == student.id:
                    return BadRequestError(
                        "Impossible de deplacer le leader d'un groupe. "
                        "Transferez d'abord le leadership."
                    ).to_response()

                source_group.admin_remove_member(student)

            # Add to target group
            target_group = Group.objects.select_for_update().get(id=data.target_group_id)
            target_group.admin_add_member(student)

            # Log operation
            _log_operation(
                period=period,
                operation_type=BalancingOperationType.MOVE_STUDENT,
                user=request.user,
                details={
                    "student_id": str(student.id),
                    "student_email": student.email,
                    "source_group_id": str(data.source_group_id) if data.source_group_id else None,
                    "source_group_name": source_group.name if source_group else None,
                    "target_group_id": str(target_group.id),
                    "target_group_name": target_group.name,
                },
                reason=data.reason,
            )

        return 200, {
            "success": True,
            "message": f"Etudiant {student.email} deplace vers {target_group.name}.",
            "student_id": str(student.id),
            "target_group_id": str(target_group.id),
        }

    @http_post(
        "/{period_id}/groups/merge",
        response={200: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_merge_groups",
    )
    def merge_groups(
        self, request: HttpRequest, period_id: UUID, data: MergeGroupsRequestSchema
    ):
        """
        Merge two groups into one.

        The surviving group keeps its rankings. The dissolved group's members
        are moved and its rankings are deleted. Pending invitations are cancelled.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        # Validate both groups exist and belong to this period
        try:
            group_a = Group.objects.get(id=data.group_a_id, ter_period=period)
            group_b = Group.objects.get(id=data.group_b_id, ter_period=period)
        except Group.DoesNotExist:
            return NotFoundError("Un ou plusieurs groupes introuvables.").to_response()

        if group_a.id == group_b.id:
            return BadRequestError("Impossible de fusionner un groupe avec lui-meme.").to_response()

        # Check that combined size doesn't exceed max
        combined_size = group_a.member_count + group_b.member_count
        if combined_size > period.max_group_size:
            return BadRequestError(
                f"La fusion depasserait la taille maximale ({period.max_group_size}). "
                f"Taille combinee: {combined_size}."
            ).to_response()

        # Check that neither group is closed
        if group_a.status == GroupStatus.CLOTURE or group_b.status == GroupStatus.CLOTURE:
            return BadRequestError(
                "Impossible de fusionner un groupe cloture avec un sujet assigne."
            ).to_response()

        with transaction.atomic():
            # Determine which group to keep
            keep_group_id = data.group_a_id  # Default to group_a
            if data.new_leader_id:
                # Keep the group that has the new leader
                if group_b.members.filter(id=data.new_leader_id).exists():
                    keep_group_id = data.group_b_id

            # Perform merge
            operation = merge_groups_algo(
                data.group_a_id, data.group_b_id, period,
                keep_group_id=keep_group_id,
                reason=data.reason,
            )

            # Update surviving group's name and leader if specified
            surviving_group = Group.objects.get(id=keep_group_id)
            if data.new_name:
                surviving_group.name = data.new_name
            if data.new_leader_id:
                try:
                    new_leader = User.objects.get(id=data.new_leader_id)
                    if surviving_group.members.filter(id=new_leader.id).exists():
                        surviving_group.leader = new_leader
                except User.DoesNotExist:
                    pass  # Ignore invalid leader ID
            surviving_group.save()

            # Log operation
            _log_operation(
                period=period,
                operation_type=BalancingOperationType.MERGE_GROUPS,
                user=request.user,
                details={
                    "group_a_id": str(data.group_a_id),
                    "group_a_name": group_a.name,
                    "group_b_id": str(data.group_b_id),
                    "group_b_name": group_b.name,
                    "surviving_group_id": str(surviving_group.id),
                    "similarity_score": operation.similarity_score,
                },
                reason=data.reason,
            )

        return 200, {
            "success": True,
            "message": f"Groupes fusionnes. Groupe survivant: {surviving_group.name}.",
            "surviving_group_id": str(surviving_group.id),
            "surviving_group_name": surviving_group.name,
            "member_count": surviving_group.member_count,
        }

    @http_post(
        "/{period_id}/groups/force-assign",
        response={200: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_force_assign",
    )
    def force_assign_subject(
        self, request: HttpRequest, period_id: UUID, data: ForceAssignRequestSchema
    ):
        """
        Force-assign a subject to a group, bypassing the algorithm.

        This directly assigns the subject and optionally closes the group.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        # Validate group
        try:
            group = Group.objects.get(id=data.group_id, ter_period=period)
        except Group.DoesNotExist:
            return NotFoundError("Groupe introuvable.").to_response()

        # Validate subject
        try:
            subject = TERSubject.objects.get(id=data.subject_id, ter_period=period)
        except TERSubject.DoesNotExist:
            return NotFoundError("Sujet introuvable.").to_response()

        # Check if group already has an assignment
        if group.assigned_subject:
            return BadRequestError(
                f"Le groupe a deja un sujet assigne: {group.assigned_subject.title}. "
                "Annulez d'abord l'affectation actuelle."
            ).to_response()

        # Check subject capacity
        current_assignments = Group.objects.filter(
            ter_period=period, assigned_subject=subject
        ).count()
        if current_assignments >= subject.max_groups:
            return BadRequestError(
                f"Le sujet a atteint sa capacite maximale ({subject.max_groups} groupes)."
            ).to_response()

        with transaction.atomic():
            group = Group.objects.select_for_update().get(id=data.group_id)
            group.assigned_subject = subject

            if data.close_group and group.status != GroupStatus.CLOTURE:
                # Force to forme first if needed, then close
                if group.status == GroupStatus.OUVERT:
                    group.status = GroupStatus.FORME
                group.close_group()

            group.save()

            # Log operation
            _log_operation(
                period=period,
                operation_type=BalancingOperationType.FORCE_ASSIGN,
                user=request.user,
                details={
                    "group_id": str(group.id),
                    "group_name": group.name,
                    "subject_id": str(subject.id),
                    "subject_title": subject.title,
                    "closed_group": data.close_group,
                },
                reason=data.reason,
            )

        return 200, {
            "success": True,
            "message": f"Sujet '{subject.title}' assigne au groupe '{group.name}'.",
            "group_id": str(group.id),
            "subject_id": str(subject.id),
            "group_status": group.status,
        }

    @http_post(
        "/{period_id}/groups/{group_id}/revert-assignment",
        response={200: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_revert_assignment",
    )
    def revert_assignment(
        self,
        request: HttpRequest,
        period_id: UUID,
        group_id: UUID,
        data: RevertAssignmentRequestSchema,
    ):
        """
        Revert a subject assignment, optionally reopening the group.

        Removes the assigned subject and can transition group back to 'forme' or 'ouvert'.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        try:
            group = Group.objects.get(id=group_id, ter_period=period)
        except Group.DoesNotExist:
            return NotFoundError("Groupe introuvable.").to_response()

        if not group.assigned_subject:
            return BadRequestError("Ce groupe n'a pas de sujet assigne.").to_response()

        with transaction.atomic():
            group = Group.objects.select_for_update().get(id=group_id)
            old_subject = group.assigned_subject

            group.assigned_subject = None

            if data.reopen_group:
                group.force_reopen()
            else:
                # Just go back to forme
                group.status = GroupStatus.FORME
                group.save(update_fields=["status", "assigned_subject"])

            # Log operation
            _log_operation(
                period=period,
                operation_type=BalancingOperationType.REVERT_ASSIGNMENT,
                user=request.user,
                details={
                    "group_id": str(group.id),
                    "group_name": group.name,
                    "previous_subject_id": str(old_subject.id),
                    "previous_subject_title": old_subject.title,
                    "reopened": data.reopen_group,
                },
                reason=data.reason,
            )

        return 200, {
            "success": True,
            "message": f"Affectation du sujet '{old_subject.title}' annulee.",
            "group_id": str(group.id),
            "group_status": group.status,
        }

    @http_post(
        "/{period_id}/groups/{group_id}/force-form",
        response={200: dict, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_force_form",
    )
    def force_form_group(
        self,
        request: HttpRequest,
        period_id: UUID,
        group_id: UUID,
        data: ForceFormRequestSchema,
    ):
        """
        Force a group to 'forme' status regardless of member count.

        This allows groups below min_group_size to submit rankings and
        participate in the assignment algorithm.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        try:
            group = Group.objects.get(id=group_id, ter_period=period)
        except Group.DoesNotExist:
            return NotFoundError("Groupe introuvable.").to_response()

        if group.status == GroupStatus.CLOTURE:
            return BadRequestError(
                "Impossible de modifier un groupe cloture avec un sujet assigne."
            ).to_response()

        if group.status == GroupStatus.FORME:
            return BadRequestError("Ce groupe est deja forme.").to_response()

        with transaction.atomic():
            group = Group.objects.select_for_update().get(id=group_id)
            group.force_form()

            # Log operation
            _log_operation(
                period=period,
                operation_type=BalancingOperationType.FORCE_FORM,
                user=request.user,
                details={
                    "group_id": str(group.id),
                    "group_name": group.name,
                    "member_count": group.member_count,
                    "min_group_size": period.min_group_size,
                },
                reason=data.reason,
            )

        return 200, {
            "success": True,
            "message": f"Groupe '{group.name}' force a l'etat 'forme'.",
            "group_id": str(group.id),
            "group_status": group.status,
            "member_count": group.member_count,
        }

    # ==================== Audit Trail ====================

    @http_get(
        "/{period_id}/balancing-operations",
        response={200: BalancingOperationListSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_balancing_operations",
    )
    def list_balancing_operations(
        self,
        request: HttpRequest,
        period_id: UUID,
        page: int = 1,
        page_size: int = 20,
        operation_type: str | None = None,
        is_automatic: bool | None = None,
    ):
        """
        List balancing operations for audit purposes.

        Supports filtering by operation_type and is_automatic.
        """
        error = _check_ter_admin(request)
        if error:
            return error

        period = get_object_or_404(TERPeriod, id=period_id)

        operations = BalancingOperation.objects.filter(ter_period=period)

        if operation_type:
            operations = operations.filter(operation_type=operation_type)
        if is_automatic is not None:
            operations = operations.filter(is_automatic=is_automatic)

        operations = operations.select_related("performed_by").order_by("-created")

        items, count, pg, ps = paginate_queryset(operations, page, page_size)

        return 200, BalancingOperationListSchema(
            count=count,
            page=pg,
            page_size=ps,
            results=[_operation_to_schema(op) for op in items],
        )
