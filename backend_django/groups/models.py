"""
Models for Student Group management.

Contains:
- Group: Student groups for TER and Stage projects (renamed from StudentGroup)
- GroupInvitation: Invitations to join groups
"""

import logging

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition

from backend_django.core.models import BaseModel

logger = logging.getLogger(__name__)


class GroupStatus(models.TextChoices):
    """Status choices for student groups (FSM states)."""

    OUVERT = "ouvert", _("Ouvert")  # Open for new members
    FORME = "forme", _("Forme")  # Formed, waiting for subject selection
    CLOTURE = "cloture", _("Cloture")  # Closed, subject assigned


class Group(BaseModel):
    """
    Student group model for TER and Stage projects.

    Renamed from StudentGroup for simplicity.

    Uses django-fsm for state management with protected transitions:
    - ouvert: Group is open for new members to join
    - forme: Group is formed, members locked, can select subjects
    - cloture: Group is closed, subject has been assigned

    Inherits from BaseModel:
        - id: UUID primary key
        - created: auto-set on creation
        - modified: auto-updated on save
    """

    name = models.CharField(
        _("name"),
        max_length=200,
        help_text=_("Group name chosen by the leader"),
    )

    max_group_size = models.PositiveIntegerField(
        _("maximum group size"),
        null=True,
        blank=True,
        help_text=_("Maximum number of members allowed in this group. Null means unlimited."),
    )

    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="led_groups",
        verbose_name=_("leader"),
        help_text=_("The student who created and leads the group"),
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="student_groups",
        verbose_name=_("members"),
        help_text=_("All group members including the leader"),
    )

    # FSM status field with protected transitions
    status = FSMField(
        _("status"),
        default=GroupStatus.OUVERT,
        choices=GroupStatus.choices,
        protected=True,
    )

    project_type = models.CharField(
        _("project type"),
        max_length=20,
        help_text=_("TER or Stage"),
    )

    # Link to academic period (one of these will be set based on project_type)
    ter_period = models.ForeignKey(
        "ter.TERPeriod",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name=_("TER period"),
    )

    stage_period = models.ForeignKey(
        "stages.StagePeriod",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name=_("internship period"),
    )

    # Assigned subject (set when group is closed) - for TER groups
    assigned_subject = models.ForeignKey(
        "ter.TERSubject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_groups",
        verbose_name=_("assigned subject"),
    )

    # Assigned offer (set when student is accepted) - for Stage groups
    assigned_offer = models.ForeignKey(
        "stages.StageOffer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_groups",
        verbose_name=_("assigned offer"),
    )

    class Meta:
        verbose_name = _("student group")
        verbose_name_plural = _("student groups")
        ordering = ["-created"]
        constraints = [
            # Ensure either ter_period or stage_period is set, but not both
            models.CheckConstraint(
                condition=(
                    models.Q(ter_period__isnull=False, stage_period__isnull=True) |
                    models.Q(ter_period__isnull=True, stage_period__isnull=False)
                ),
                name="group_period_exclusive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """Ensure leader is always in members and auto-form if min_group_size reached."""
        super().save(*args, **kwargs)
        if self.leader and not self.members.filter(id=self.leader_id).exists():
            self.members.add(self.leader)
            # Check if we should auto-form after adding leader
            self.check_and_auto_form()

    def check_and_auto_form(self):
        """
        Auto-transition to 'formé' if group meets min_group_size requirement.

        Called after:
        - Group creation (leader added)
        - Invitation acceptance (new member added)

        Only applies to TER groups (Stage groups don't have min_group_size).
        """
        if self.status != GroupStatus.OUVERT:
            return

        # Only TER periods have min_group_size
        period = self.ter_period
        if not period:
            return

        if self.member_count >= period.min_group_size:
            self.form_group()
            self.save(update_fields=["status"])
            logger.info(
                "AUTO-TRANSITION: Group '%s' formed (has %d members, min_group_size=%d)",
                self.name,
                self.member_count,
                period.min_group_size,
            )

    def check_and_auto_reopen(self):
        """
        Auto-transition back to 'ouvert' if group drops below min_group_size.

        Called after:
        - Member leaves the group
        - Leader removes a member
        """
        if self.status != GroupStatus.FORME:
            return

        period = self.ter_period
        min_size = period.min_group_size if period else 2

        if self.member_count < min_size:
            self.reopen_group()
            self.save(update_fields=["status"])
            logger.info(
                "AUTO-TRANSITION: Group '%s' reopened (has %d members, min_group_size=%d)",
                self.name,
                self.member_count,
                min_size,
            )

    # FSM Transitions

    @transition(field=status, source=GroupStatus.OUVERT, target=GroupStatus.FORME)
    def form_group(self):
        """
        Transition from ouvert to forme.

        Called when:
        - Group leader manually locks the group
        - Group formation deadline passes
        """
        pass

    @transition(field=status, source=GroupStatus.FORME, target=GroupStatus.CLOTURE)
    def close_group(self):
        """
        Transition from forme to cloture.

        Called when:
        - Subject is assigned to the group
        - Assignment algorithm completes
        """
        pass

    @transition(field=status, source=GroupStatus.FORME, target=GroupStatus.OUVERT)
    def reopen_group(self):
        """
        Transition from forme back to ouvert.

        Called when:
        - Admin needs to allow group modifications
        - Only possible before subject assignment
        """
        pass

    # Admin override methods

    def force_form(self):
        """
        Force transition to 'forme' status regardless of current state.

        Admin-only operation that bypasses normal FSM transitions.
        Use with caution - should only be called by Respo TER.
        """
        if self.status == GroupStatus.CLOTURE:
            raise ValueError("Cannot force form a closed group with assigned subject")

        old_status = self.status
        # Bypass FSM protection by using update() directly
        Group.objects.filter(pk=self.pk).update(status=GroupStatus.FORME)
        # Manually update the in-memory state without triggering FSM setter
        # Access the internal state directly
        self.__dict__["status"] = GroupStatus.FORME

        logger.info(
            "ADMIN-OVERRIDE: Group '%s' force-formed (was %s)",
            self.name,
            old_status,
        )

    def force_reopen(self):
        """
        Force transition to 'ouvert' status regardless of current state.

        Admin-only operation that bypasses normal FSM transitions.
        Clears assigned_subject if present.
        Use with caution - should only be called by Respo TER.
        """
        old_status = self.status
        old_subject = self.assigned_subject

        # Bypass FSM protection by using update() directly
        Group.objects.filter(pk=self.pk).update(
            status=GroupStatus.OUVERT,
            assigned_subject=None,
        )
        # Manually update the in-memory state without triggering FSM setter
        self.__dict__["status"] = GroupStatus.OUVERT
        self.assigned_subject = None
        self.assigned_subject_id = None

        logger.info(
            "ADMIN-OVERRIDE: Group '%s' force-reopened (was %s, had subject: %s)",
            self.name,
            old_status,
            old_subject.title if old_subject else None,
        )

    def can_add_member(self) -> bool:
        """
        Check if new members can be added to the group.

        Uses max_group_size from group if set, otherwise from ter_period.
        """
        if self.status != GroupStatus.OUVERT:
            return False

        # Use group's max_group_size, fallback to ter_period's
        max_size = self.max_group_size
        if max_size is None and self.ter_period:
            max_size = self.ter_period.max_group_size

        if max_size:
            return self.members.count() < max_size

        return True

    def admin_add_member(self, user):
        """
        Admin-only: Add a member to the group bypassing status checks.

        Args:
            user: User instance to add

        Raises:
            ValueError: If max_group_size would be exceeded
        """
        max_size = self.max_group_size
        if max_size is None and self.ter_period:
            max_size = self.ter_period.max_group_size

        if max_size:
            if self.member_count >= max_size:
                raise ValueError(
                    f"Cannot add member: group already at max size ({max_size})"
                )

        self.members.add(user)
        logger.info(
            "ADMIN-OVERRIDE: Added member %s to group '%s'",
            user.email,
            self.name,
        )

    def admin_remove_member(self, user):
        """
        Admin-only: Remove a member from the group bypassing status checks.

        Cannot remove the leader.

        Args:
            user: User instance to remove

        Raises:
            ValueError: If user is the leader
        """
        if user.id == self.leader_id:
            raise ValueError("Cannot remove the group leader")

        if not self.members.filter(id=user.id).exists():
            raise ValueError("User is not a member of this group")

        self.members.remove(user)
        logger.info(
            "ADMIN-OVERRIDE: Removed member %s from group '%s'",
            user.email,
            self.name,
        )

    # Helper methods

    def can_remove_member(self, user) -> bool:
        """Check if a member can be removed from the group."""
        if self.status != GroupStatus.OUVERT:
            return False

        # Cannot remove the leader
        if user.id == self.leader_id:
            return False

        return self.members.filter(id=user.id).exists()

    def is_member(self, user) -> bool:
        """Check if user is a member of this group."""
        return self.members.filter(id=user.id).exists()

    def is_leader(self, user) -> bool:
        if not self.leader_id:
            return False
        return self.leader_id == user.id

    def get_period(self):
        """Get the associated period (TER or Stage)."""
        return self.ter_period or self.stage_period

    @property
    def member_count(self) -> int:
        """Return the number of members in the group."""
        return self.members.count()


# Alias for backward compatibility
StudentGroup = Group


class InvitationStatus(models.TextChoices):
    """Status choices for group invitations."""

    PENDING = "pending", _("En attente")
    ACCEPTED = "accepted", _("Acceptee")
    DECLINED = "declined", _("Refusee")
    CANCELLED = "cancelled", _("Annulee")


class GroupInvitation(BaseModel):
    """
    Invitation to join a student group.

    Tracks invitations sent by group leaders to students.
    """

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="invitations",
        verbose_name=_("group"),
    )

    invitee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="group_invitations",
        verbose_name=_("invitee"),
        help_text=_("The student being invited"),
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_invitations",
        verbose_name=_("invited by"),
        help_text=_("The leader who sent the invitation"),
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )

    message = models.TextField(
        _("message"),
        blank=True,
        help_text=_("Optional message from the leader"),
    )

    responded_at = models.DateTimeField(
        _("responded at"),
        null=True,
        blank=True,
        help_text=_("When the invitee responded"),
    )

    class Meta:
        verbose_name = _("group invitation")
        verbose_name_plural = _("group invitations")
        ordering = ["-created"]
        constraints = [
            # One pending invitation per user per group
            models.UniqueConstraint(
                fields=["group", "invitee"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation",
            ),
        ]

    def __str__(self) -> str:
        return f"Invitation to {self.invitee.email} for {self.group.name}"

    def can_respond(self) -> bool:
        """Check if invitation can still be responded to."""
        return self.status == InvitationStatus.PENDING

    def accept(self):
        """
        Accept the invitation and add user to group.

        Also auto-declines other pending invitations for the same period.
        Triggers automatic status transition if group reaches 2+ members.
        Uses database-level locking to prevent race conditions.
        """
        from django.db import transaction
        from django.utils import timezone

        if not self.can_respond():
            raise ValueError("Cannot accept invitation that is not pending")

        with transaction.atomic():
            # Lock the group row to prevent concurrent acceptance
            group = Group.objects.select_for_update().get(id=self.group_id)

            if not group.can_add_member():
                raise ValueError("Group cannot accept new members")

            # Check invitee is not already in another group for the same period
            period_filter = {}
            if group.ter_period_id:
                period_filter["ter_period"] = group.ter_period_id
            elif group.stage_period_id:
                period_filter["stage_period"] = group.stage_period_id
            if period_filter:
                existing_group = Group.objects.filter(
                    members=self.invitee, **period_filter
                ).exclude(id=group.id).first()
                if existing_group:
                    raise ValueError(
                        f"Vous êtes déjà membre du groupe « {existing_group.name} ». "
                        "Quittez-le avant d'accepter cette invitation."
                    )

            self.status = InvitationStatus.ACCEPTED
            self.responded_at = timezone.now()
            self.save()

            # Add to group members
            group.members.add(self.invitee)

            # Auto-transition if min_group_size reached
            group.check_and_auto_form()

        # Auto-decline other pending invitations for the same period
        self._auto_decline_other_invitations()

        self._notify_leader_accepted()

    def _auto_decline_other_invitations(self):
        """Auto-decline other pending invitations for the same period."""
        from django.utils import timezone

        # Get the period from the accepted group
        period = self.group.get_period()
        if not period:
            return

        # Find other pending invitations for groups in the same period
        other_invitations = GroupInvitation.objects.filter(
            invitee=self.invitee,
            status=InvitationStatus.PENDING,
        ).exclude(id=self.id)

        # Filter by same period type
        if self.group.ter_period:
            other_invitations = other_invitations.filter(
                group__ter_period=self.group.ter_period
            )
        elif self.group.stage_period:
            other_invitations = other_invitations.filter(
                group__stage_period=self.group.stage_period
            )

        # Decline them all
        now = timezone.now()
        other_invitations.update(
            status=InvitationStatus.DECLINED,
            responded_at=now,
        )

    def decline(self):
        """Decline the invitation."""
        from django.utils import timezone

        if not self.can_respond():
            raise ValueError("Cannot decline invitation that is not pending")

        self.status = InvitationStatus.DECLINED
        self.responded_at = timezone.now()
        self.save()

        self._notify_leader_declined()

    def cancel(self):
        """Cancel the invitation (by leader)."""
        if not self.can_respond():
            raise ValueError("Cannot cancel invitation that is not pending")

        self.status = InvitationStatus.CANCELLED
        self.save()

    def _notify_leader_accepted(self):
        """Notify the group leader that the invitation was accepted."""
        from backend_django.notifications.services import send_notification

        invitee_name = self.invitee.get_full_name() or self.invitee.email
        send_notification(
            recipient=self.group.leader,
            notification_type="group.invitation_accepted",
            title="Invitation acceptée",
            message=f"{invitee_name} a rejoint le groupe « {self.group.name} ».",
            data={"group_id": str(self.group.id), "user_id": str(self.invitee.id)},
        )

    def _notify_leader_declined(self):
        """Notify the group leader that the invitation was declined."""
        from backend_django.notifications.services import send_notification

        invitee_name = self.invitee.get_full_name() or self.invitee.email
        send_notification(
            recipient=self.group.leader,
            notification_type="group.invitation_declined",
            title="Invitation refusée",
            message=f"{invitee_name} a décliné l'invitation au groupe « {self.group.name} ».",
            data={"group_id": str(self.group.id), "user_id": str(self.invitee.id)},
        )
