"""
Groups API controller.
"""

import logging
from datetime import date
from uuid import UUID

from django.db.models import Count, Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get, http_post

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    AlreadyExistsError,
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.groups.models import Group, GroupInvitation, GroupStatus, InvitationStatus
from backend_django.groups.schemas.groups import (
    DashboardStatsSchema,
    GroupCreateSchema,
    GroupDetailSchema,
    GroupListSchema,
    InvitationCreateSchema,
    InvitationResponseSchema,
    InvitationSchema,
    MessageSchema,
    SolitaireSchema,
    StagePeriodSchema,
    TERPeriodSchema,
    TransferLeadershipSchema,
    UserMinimalSchema,
)
from backend_django.stages.models import PeriodStatus, StagePeriod
from backend_django.ter.models import TERPeriod
from backend_django.users.models import User

logger = logging.getLogger(__name__)


def ter_period_to_schema(period: TERPeriod) -> TERPeriodSchema:
    """Convert TERPeriod to schema."""
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


def stage_period_to_schema(period: StagePeriod) -> StagePeriodSchema:
    """Convert StagePeriod to schema."""
    return StagePeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        application_start=str(period.application_start),
        application_end=str(period.application_end),
    )


def group_to_list_schema(group: Group) -> GroupListSchema:
    """Convert Group to list schema."""
    return GroupListSchema(
        id=group.id,
        name=group.name,
        leader=UserMinimalSchema.from_user(group.leader),
        member_count=group.member_count,
        status=group.status,
        project_type=group.project_type,
        created=group.created,
    )


def group_to_detail_schema(group: Group) -> GroupDetailSchema:
    """Convert Group to detail schema."""
    members = [UserMinimalSchema.from_user(m) for m in group.members.all()]
    return GroupDetailSchema(
        id=group.id,
        name=group.name,
        leader=UserMinimalSchema.from_user(group.leader),
        member_count=group.member_count,
        status=group.status,
        project_type=group.project_type,
        created=group.created,
        members=members,
        ter_period=ter_period_to_schema(group.ter_period) if group.ter_period else None,
        stage_period=stage_period_to_schema(group.stage_period) if group.stage_period else None,
        assigned_subject_id=group.assigned_subject_id,
    )


def invitation_to_schema(invitation: GroupInvitation) -> InvitationSchema:
    """Convert GroupInvitation to schema."""
    return InvitationSchema(
        id=invitation.id,
        group_id=invitation.group_id,
        group_name=invitation.group.name,
        invitee=UserMinimalSchema.from_user(invitation.invitee),
        invited_by=UserMinimalSchema.from_user(invitation.invited_by),
        status=invitation.status,
        message=invitation.message,
        created=invitation.created,
        responded_at=invitation.responded_at,
    )


@api_controller("/groups", tags=["Groups"], permissions=[IsAuthenticated])
class GroupController(BaseAPI):
    """CRUD operations for student groups."""

    @http_get(
        "/",
        response={200: list[GroupListSchema], 401: ErrorSchema},
        url_name="groups_list",
    )
    def list_groups(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
        stage_period_id: UUID | None = None,
        status: str | None = None,
    ):
        """List groups with optional filtering."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        groups = Group.objects.select_related("leader", "ter_period", "stage_period")

        if ter_period_id:
            groups = groups.filter(ter_period_id=ter_period_id)
        if stage_period_id:
            groups = groups.filter(stage_period_id=stage_period_id)
        if status:
            groups = groups.filter(status=status)

        groups = groups.order_by("-created")

        return 200, [group_to_list_schema(g) for g in groups]

    @http_get(
        "/my",
        response={200: list[GroupListSchema], 401: ErrorSchema},
        url_name="groups_my",
    )
    def my_groups(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
        stage_period_id: UUID | None = None,
    ):
        """
        Get groups where current user is a member.

        Optional filters:
        - ter_period_id: Filter by TER period
        - stage_period_id: Filter by Stage period
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        groups = Group.objects.filter(
            members=request.user
        ).select_related("leader", "ter_period", "stage_period")

        if ter_period_id:
            groups = groups.filter(ter_period_id=ter_period_id)
        if stage_period_id:
            groups = groups.filter(stage_period_id=stage_period_id)

        groups = groups.order_by("-created")

        return 200, [group_to_list_schema(g) for g in groups]

    @http_get(
        "/{group_id}",
        response={200: GroupDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="groups_detail",
    )
    def get_group(self, request: HttpRequest, group_id: UUID):
        """Get group details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(
            Group.objects.select_related("leader", "ter_period", "stage_period").prefetch_related("members"),
            id=group_id,
        )

        return 200, group_to_detail_schema(group)

    @http_post(
        "/",
        response={201: GroupDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="groups_create",
    )
    def create_group(self, request: HttpRequest, data: GroupCreateSchema):
        """
        Create a new group for TER.

        The current user becomes the leader and first member.
        Requires an active TER period in formation phase.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Validate that exactly one period is specified
        if data.ter_period_id and data.stage_period_id:
            return BadRequestError("Specifiez soit une periode TER soit une periode Stage, pas les deux.").to_response()

        if not data.ter_period_id and not data.stage_period_id:
            return BadRequestError("Vous devez specifier une periode TER ou Stage.").to_response()

        ter_period = None
        stage_period = None
        project_type = None

        if data.ter_period_id:
            # TER group creation
            ter_period = TERPeriod.objects.filter(id=data.ter_period_id).first()
            if not ter_period:
                return NotFoundError("Periode TER non trouvee.").to_response()

            # Check period is open
            if ter_period.status != PeriodStatus.OPEN:
                return BadRequestError("La periode TER n'est pas ouverte.").to_response()

            # Check we're in formation phase
            today = date.today()
            if not (ter_period.group_formation_start <= today <= ter_period.group_formation_end):
                return BadRequestError("La periode de formation des groupes est terminee.").to_response()

            # Check user doesn't already lead a group for this period
            existing_group = Group.objects.filter(
                leader=request.user,
                ter_period=ter_period,
            ).first()
            if existing_group:
                return BadRequestError("Vous etes deja leader d'un groupe pour cette periode TER.").to_response()

            project_type = "srw"

        elif data.stage_period_id:
            # Stage group creation
            stage_period = StagePeriod.objects.filter(id=data.stage_period_id).first()
            if not stage_period:
                return NotFoundError("Periode Stage non trouvee.").to_response()

            # Check period is open
            if stage_period.status != PeriodStatus.OPEN:
                return BadRequestError("La periode Stage n'est pas ouverte.").to_response()

            # Check user doesn't already lead a group for this period
            existing_group = Group.objects.filter(
                leader=request.user,
                stage_period=stage_period,
            ).first()
            if existing_group:
                return BadRequestError("Vous etes deja leader d'un groupe pour cette periode Stage.").to_response()

            project_type = "internship"

        # Create the group
        group = Group.objects.create(
            name=data.name,
            leader=request.user,
            project_type=project_type,
            ter_period=ter_period,
            stage_period=stage_period,
        )

        # Reload with related data
        group = Group.objects.select_related(
            "leader", "ter_period", "stage_period"
        ).prefetch_related("members").get(id=group.id)

        return 201, group_to_detail_schema(group)

    # ==================== Invitation Endpoints ====================

    @http_post(
        "/{group_id}/invite",
        response={201: InvitationSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema, 409: ErrorSchema},
        url_name="groups_invite",
    )
    def invite_to_group(self, request: HttpRequest, group_id: UUID, data: InvitationCreateSchema):
        """
        Invite a student to join the group.

        Only the group leader can send invitations.
        Group must be in "ouvert" status.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check user is the leader
        if not group.is_leader(request.user):
            return PermissionDeniedError("Seul le leader peut inviter des membres.").to_response()

        # Check group is open
        if group.status != GroupStatus.OUVERT:
            return BadRequestError("Impossible d'inviter dans un groupe qui n'est pas ouvert.").to_response()

        # Check formation deadline has not passed (TER groups)
        if group.ter_period:
            today = date.today()
            if today > group.ter_period.group_formation_end:
                return BadRequestError("Impossible d'envoyer des invitations apres la deadline de formation.").to_response()

        # Check group can accept more members
        if not group.can_add_member():
            return BadRequestError("Le groupe a atteint sa taille maximale.").to_response()

        # Find the invitee by email
        invitee = User.objects.filter(email=data.invitee_email).first()
        if not invitee:
            return NotFoundError(f"Aucun utilisateur trouve avec l'email {data.invitee_email}.").to_response()

        # Check invitee is not already a member
        if group.is_member(invitee):
            return BadRequestError("Cet utilisateur est deja membre du groupe.").to_response()

        # Check invitee is not the leader
        if group.is_leader(invitee):
            return BadRequestError("Vous ne pouvez pas vous inviter vous-meme.").to_response()

        # Check no pending invitation exists
        existing = GroupInvitation.objects.filter(
            group=group,
            invitee=invitee,
            status=InvitationStatus.PENDING,
        ).first()
        if existing:
            return AlreadyExistsError("Une invitation est deja en attente pour cet utilisateur.").to_response()

        # Create invitation
        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=invitee,
            invited_by=request.user,
            message=data.message,
        )

        # Reload with related data
        invitation = GroupInvitation.objects.select_related(
            "group", "invitee", "invited_by"
        ).get(id=invitation.id)

        return 201, invitation_to_schema(invitation)

    @http_get(
        "/{group_id}/invitations",
        response={200: list[InvitationSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_invitations_list",
    )
    def list_group_invitations(self, request: HttpRequest, group_id: UUID):
        """
        List invitations for a group.

        Only the group leader can see all invitations.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check user is the leader
        if not group.is_leader(request.user):
            return PermissionDeniedError("Seul le leader peut voir les invitations.").to_response()

        invitations = GroupInvitation.objects.filter(
            group=group
        ).select_related("group", "invitee", "invited_by").order_by("-created")

        return 200, [invitation_to_schema(inv) for inv in invitations]

    @http_get(
        "/invitations/received",
        response={200: list[InvitationSchema], 401: ErrorSchema},
        url_name="invitations_received",
    )
    def my_invitations(self, request: HttpRequest):
        """Get invitations received by current user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        invitations = GroupInvitation.objects.filter(
            invitee=request.user
        ).select_related("group", "invitee", "invited_by").order_by("-created")

        return 200, [invitation_to_schema(inv) for inv in invitations]

    @http_post(
        "/invitations/{invitation_id}/respond",
        response={200: InvitationSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="invitations_respond",
    )
    def respond_to_invitation(self, request: HttpRequest, invitation_id: UUID, data: InvitationResponseSchema):
        """
        Accept or decline an invitation.

        Only the invitee can respond.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        invitation = get_object_or_404(
            GroupInvitation.objects.select_related("group", "invitee", "invited_by"),
            id=invitation_id,
        )

        # Check user is the invitee
        if invitation.invitee_id != request.user.id:
            return PermissionDeniedError("Vous ne pouvez repondre qu'a vos propres invitations.").to_response()

        # Check invitation is pending
        if not invitation.can_respond():
            return BadRequestError("Cette invitation n'est plus en attente.").to_response()

        # Check formation deadline has not passed for acceptance (TER groups)
        if data.accept:
            group = invitation.group
            if group.ter_period:
                today = date.today()
                if today > group.ter_period.group_formation_end:
                    return BadRequestError("Impossible d'accepter une invitation apres la deadline de formation.").to_response()

        try:
            if data.accept:
                invitation.accept()
            else:
                invitation.decline()
        except ValueError as e:
            return BadRequestError(str(e)).to_response()

        return 200, invitation_to_schema(invitation)

    @http_post(
        "/{group_id}/invitations/{invitation_id}/cancel",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="invitations_cancel",
    )
    def cancel_invitation(self, request: HttpRequest, group_id: UUID, invitation_id: UUID):
        """
        Cancel a pending invitation.

        Only the group leader can cancel invitations.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)
        invitation = get_object_or_404(GroupInvitation, id=invitation_id, group=group)

        # Check user is the leader
        if not group.is_leader(request.user):
            return PermissionDeniedError("Seul le leader peut annuler les invitations.").to_response()

        # Check invitation is pending
        if not invitation.can_respond():
            return BadRequestError("Cette invitation n'est plus en attente.").to_response()

        invitation.cancel()

        return 200, MessageSchema(success=True, message="Invitation annulee.")

    # ==================== Member Management Endpoints ====================

    @http_post(
        "/{group_id}/leave",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_leave",
    )
    def leave_group(self, request: HttpRequest, group_id: UUID):
        """
        Leave a group.

        Only non-leader members can leave.
        Group must not be closed (cloture).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check user is a member
        if not group.is_member(request.user):
            return BadRequestError("Vous n'etes pas membre de ce groupe.").to_response()

        # Check user is not the leader
        if group.is_leader(request.user):
            return BadRequestError("Le leader doit transferer le leadership avant de quitter.").to_response()

        # Check group is not closed
        if group.status == GroupStatus.CLOTURE:
            return BadRequestError("Impossible de quitter un groupe cloture.").to_response()

        # Remove user from group
        group.members.remove(request.user)

        # Auto-revert: forme -> ouvert when member count drops below 2
        if group.status == GroupStatus.FORME and group.member_count < 2:
            group.reopen_group()
            group.save()
            logger.info(
                "AUTO-TRANSITION: Group '%s' reverted to ouvert (now has %d members)",
                group.name,
                group.member_count,
            )

        # Log notification (placeholder for real notification system)
        logger.info(
            "NOTIFICATION: %s left group '%s' (leader: %s)",
            request.user.get_full_name() or request.user.email,
            group.name,
            group.leader.email,
        )

        return 200, MessageSchema(success=True, message="Vous avez quitte le groupe.")

    @http_post(
        "/{group_id}/transfer-leadership",
        response={200: GroupDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_transfer_leadership",
    )
    def transfer_leadership(self, request: HttpRequest, group_id: UUID, data: TransferLeadershipSchema):
        """
        Transfer group leadership to another member.

        Only the current leader can transfer leadership.
        The new leader must be an existing member.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(
            Group.objects.select_related("leader", "ter_period", "stage_period").prefetch_related("members"),
            id=group_id,
        )

        # Check user is the leader
        if not group.is_leader(request.user):
            return PermissionDeniedError("Seul le leader peut transferer le leadership.").to_response()

        # Find the new leader
        new_leader = User.objects.filter(id=data.new_leader_id).first()
        if not new_leader:
            return NotFoundError("Utilisateur non trouve.").to_response()

        # Check new leader is a member
        if not group.is_member(new_leader):
            return BadRequestError("Le nouveau leader doit etre membre du groupe.").to_response()

        # Check not transferring to self
        if new_leader.id == request.user.id:
            return BadRequestError("Vous etes deja le leader.").to_response()

        # Transfer leadership
        old_leader = group.leader
        group.leader = new_leader
        group.save()

        # Log notification (placeholder for real notification system)
        logger.info(
            "NOTIFICATION: Leadership transferred from %s to %s in group '%s'",
            old_leader.get_full_name() or old_leader.email,
            new_leader.get_full_name() or new_leader.email,
            group.name,
        )

        # Reload group
        group = Group.objects.select_related(
            "leader", "ter_period", "stage_period"
        ).prefetch_related("members").get(id=group.id)

        return 200, group_to_detail_schema(group)

    @http_post(
        "/{group_id}/close",
        response={200: GroupDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_close",
    )
    def close_group(self, request: HttpRequest, group_id: UUID):
        """
        Close a group (forme -> cloture).

        Only the leader can close a group.
        Group must be in "forme" status (has 2+ members).
        Once closed, no members can join or leave.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(
            Group.objects.select_related("leader", "ter_period", "stage_period").prefetch_related("members"),
            id=group_id,
        )

        # Check user is the leader
        if not group.is_leader(request.user):
            return PermissionDeniedError("Seul le leader peut fermer le groupe.").to_response()

        # Check group is in forme status
        if group.status == GroupStatus.OUVERT:
            return BadRequestError("Le groupe doit avoir au moins 2 membres pour etre cloture.").to_response()

        if group.status == GroupStatus.CLOTURE:
            return BadRequestError("Le groupe est deja cloture.").to_response()

        # Transition to cloture
        try:
            group.close_group()
            group.save()
        except Exception as e:
            return BadRequestError(f"Impossible de fermer le groupe: {e!s}").to_response()

        # Log notification
        logger.info(
            "NOTIFICATION: Group '%s' closed by leader %s",
            group.name,
            request.user.email,
        )

        # Reload group
        group = Group.objects.select_related(
            "leader", "ter_period", "stage_period"
        ).prefetch_related("members").get(id=group.id)

        return 200, group_to_detail_schema(group)

    # ==================== Dashboard Endpoints (Respo TER) ====================

    @http_get(
        "/dashboard/{ter_period_id}/stats",
        response={200: DashboardStatsSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_dashboard_stats",
    )
    def dashboard_stats(self, request: HttpRequest, ter_period_id: UUID):
        """
        Get dashboard statistics for a TER period.

        Staff only (Respo TER).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError("Reserve au personnel.").to_response()

        ter_period = get_object_or_404(TERPeriod, id=ter_period_id)

        # Get all groups for this period
        groups = Group.objects.filter(ter_period=ter_period)

        # Count by status
        groups_by_status = {
            GroupStatus.OUVERT: groups.filter(status=GroupStatus.OUVERT).count(),
            GroupStatus.FORME: groups.filter(status=GroupStatus.FORME).count(),
            GroupStatus.CLOTURE: groups.filter(status=GroupStatus.CLOTURE).count(),
        }

        # Count students in groups
        students_in_groups = User.objects.filter(
            student_groups__ter_period=ter_period
        ).distinct().count()

        # Count solitaires (active non-staff users not in any group for this period)
        all_active_students = User.objects.filter(
            is_active=True,
            is_staff=False,
        ).count()
        solitaires_count = all_active_students - students_in_groups

        # Count incomplete groups (1 member only)
        incomplete = groups.annotate(
            members_count=Count("members")
        ).filter(members_count__lt=2).count()

        return 200, DashboardStatsSchema(
            total_groups=groups.count(),
            total_students_in_groups=students_in_groups,
            total_solitaires=solitaires_count,
            groups_by_status=groups_by_status,
            incomplete_groups_count=incomplete,
        )

    @http_get(
        "/dashboard/{ter_period_id}/solitaires",
        response={200: list[SolitaireSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_dashboard_solitaires",
    )
    def list_solitaires(self, request: HttpRequest, ter_period_id: UUID):
        """
        List students without a group for a TER period.

        Staff only (Respo TER).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError("Reserve au personnel.").to_response()

        ter_period = get_object_or_404(TERPeriod, id=ter_period_id)

        # Get all students who are in at least one group for this period
        students_in_groups = User.objects.filter(
            student_groups__ter_period=ter_period
        ).values_list("id", flat=True)

        # Get all active non-staff users NOT in any group for this period
        solitaires = User.objects.filter(
            is_active=True,
            is_staff=False,
        ).exclude(
            id__in=students_in_groups
        ).annotate(
            pending_invitations=Count(
                "group_invitations",
                filter=Q(
                    group_invitations__status=InvitationStatus.PENDING,
                    group_invitations__group__ter_period=ter_period,
                ),
            )
        )

        return 200, [
            SolitaireSchema(
                id=user.id,
                email=user.email,
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                pending_invitations=user.pending_invitations,
            )
            for user in solitaires
        ]

    @http_get(
        "/dashboard/{ter_period_id}/incomplete",
        response={200: list[GroupListSchema], 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="groups_dashboard_incomplete",
    )
    def list_incomplete_groups(self, request: HttpRequest, ter_period_id: UUID):
        """
        List groups with less than 2 members for a TER period.

        Staff only (Respo TER).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_ter_admin(request.user):
            return PermissionDeniedError("Reserve au personnel.").to_response()

        ter_period = get_object_or_404(TERPeriod, id=ter_period_id)

        # Get groups with <2 members
        incomplete_groups = Group.objects.filter(
            ter_period=ter_period
        ).annotate(
            members_count=Count("members")
        ).filter(
            members_count__lt=2
        ).select_related("leader")

        return 200, [group_to_list_schema(g) for g in incomplete_groups]
