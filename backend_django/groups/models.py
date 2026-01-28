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
        """Ensure leader is always in members."""
        super().save(*args, **kwargs)
        if self.leader and not self.members.filter(id=self.leader_id).exists():
            self.members.add(self.leader)

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

    # Helper methods

    def can_add_member(self) -> bool:
        """
        Check if new members can be added to the group.

        Rules:
        - Only groups with status "ouvert" can accept new members.
        - TER groups are limited by ter_period.max_group_size.
        - Stage groups have no size limit (internships are typically individual).
        """
        if self.status != GroupStatus.OUVERT:
            return False

        # Check group size limits (only TER periods have max_group_size)
        if self.ter_period and self.ter_period.max_group_size:
            return self.members.count() < self.ter_period.max_group_size

        return True

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
        """Check if user is the leader of this group."""
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

            self.status = InvitationStatus.ACCEPTED
            self.responded_at = timezone.now()
            self.save()

            # Add to group members
            group.members.add(self.invitee)

            # Auto-transition: ouvert -> forme when 2nd member joins
            if group.status == GroupStatus.OUVERT and group.member_count >= 2:
                group.form_group()
                group.save()
                logger.info(
                    "AUTO-TRANSITION: Group '%s' formed (now has %d members)",
                    group.name,
                    group.member_count,
                )

        # Auto-decline other pending invitations for the same period
        self._auto_decline_other_invitations()

        # TODO: Send real notification when notification system is implemented
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

        # TODO: Send real notification when notification system is implemented
        self._notify_leader_declined()

    def cancel(self):
        """Cancel the invitation (by leader)."""
        if not self.can_respond():
            raise ValueError("Cannot cancel invitation that is not pending")

        self.status = InvitationStatus.CANCELLED
        self.save()

    def _notify_leader_accepted(self):
        """
        Notify the group leader that the invitation was accepted.

        TODO: Replace with real notification system (email, in-app, etc.)
        """
        logger.info(
            "NOTIFICATION: %s joined group '%s' (leader: %s)",
            self.invitee.get_full_name() or self.invitee.email,
            self.group.name,
            self.group.leader.email,
        )

    def _notify_leader_declined(self):
        """
        Notify the group leader that the invitation was declined.

        TODO: Replace with real notification system (email, in-app, etc.)
        """
        logger.info(
            "NOTIFICATION: %s declined invitation to group '%s' (leader: %s)",
            self.invitee.get_full_name() or self.invitee.email,
            self.group.name,
            self.group.leader.email,
        )
