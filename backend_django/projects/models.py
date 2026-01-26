"""
Models for academic projects, periods, groups and file attachments.
"""

import uuid
from datetime import date

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition

from backend_django.core.models import BaseModel


def get_current_academic_year() -> str:
    """
    Return the current academic year (e.g., '2024-2025').

    Academic year starts in September:
    - Sept 2024 to Aug 2025 = '2024-2025'
    """
    today = date.today()
    if today.month >= 9:  # September or later
        return f"{today.year}-{today.year + 1}"
    return f"{today.year - 1}-{today.year}"


def attachment_path(instance: "Attachment", filename: str) -> str:
    """Generate upload path for attachments."""
    return f"attachments/{instance.owner_id}/{uuid.uuid4()}/{filename}"


class Attachment(BaseModel):
    """
    File attachment stored in MinIO/S3.
    Replaces the old GridFS FileDocument.

    Inherits from BaseModel:
        - id: UUID primary key
        - created: auto-set on creation
        - modified: auto-updated on save
    """

    file = models.FileField(
        _("file"),
        upload_to=attachment_path,
    )
    original_filename = models.CharField(
        _("original filename"),
        max_length=255,
    )
    content_type = models.CharField(
        _("content type"),
        max_length=100,
    )
    size = models.PositiveIntegerField(
        _("file size"),
        help_text=_("Size in bytes"),
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("owner"),
    )

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")
        ordering = ["-created"]

    def __str__(self) -> str:
        return self.original_filename

    def can_be_viewed_by(self, user) -> bool:
        """Check if user can view this attachment."""
        # Owner can always view
        if self.owner_id == user.id:
            return True
        # Staff can view all
        if user.is_staff:
            return True
        # Check if user is related to a project that uses this attachment
        return self.academic_projects.filter(
            models.Q(student=user) | models.Q(referent=user) | models.Q(supervisor=user)
        ).exists()


class AcademicProjectType(models.TextChoices):
    """Types of academic projects."""

    MEMOIR = "memoir", _("Mémoire")
    INTERNSHIP = "internship", _("Stage")
    SRW = "srw", _("T.E.R.")  # Supervised Research Work


class AcademicProjectStatus(models.TextChoices):
    """Status choices for academic projects."""

    PENDING = "pending", _("En attente de validation")
    VALIDATED = "validated", _("Validé")
    IN_PROGRESS = "in_progress", _("En cours")
    COMPLETED = "completed", _("Terminé")
    ARCHIVED = "archived", _("Archivé")
    REJECTED = "rejected", _("Refusé")


class ProposalStatus(models.TextChoices):
    """Status choices for project proposals."""

    OPEN = "open", _("Ouvert aux candidatures")
    ASSIGNED = "assigned", _("Attribué")
    IN_DEVELOPMENT = "in_development", _("En cours de définition")
    CLOSED = "closed", _("Clôturé")


class ApplicationStatus(models.TextChoices):
    """Status choices for proposal applications."""

    PENDING = "pending", _("En attente")
    ACCEPTED = "accepted", _("Acceptée")
    REJECTED = "rejected", _("Refusée")


class AcademicProject(BaseModel):
    """
    Academic project model.
    Links students with supervisors and tracks project files.

    Inherits from BaseModel:
        - id: UUID primary key
        - created: auto-set on creation
        - modified: auto-updated on save
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects_as_student",
        verbose_name=_("student"),
    )
    referent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="projects_as_referent",
        verbose_name=_("referent"),
    )
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="projects_as_supervisor",
        verbose_name=_("supervisor"),
    )
    subject = models.CharField(
        _("subject"),
        max_length=500,
    )
    project_type = models.CharField(
        _("type"),
        max_length=20,
        choices=AcademicProjectType.choices,
    )
    files = models.ManyToManyField(
        Attachment,
        blank=True,
        related_name="academic_projects",
        verbose_name=_("files"),
    )
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"))

    # Status tracking
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=AcademicProjectStatus.choices,
        default=AcademicProjectStatus.PENDING,
    )

    # Academic year (format: "2024-2025")
    academic_year = models.CharField(
        _("academic year"),
        max_length=9,
        blank=True,
    )

    # Description
    description = models.TextField(
        _("description"),
        blank=True,
    )

    # Company information (for internships)
    company_name = models.CharField(
        _("company name"),
        max_length=200,
        blank=True,
    )
    company_address = models.TextField(
        _("company address"),
        blank=True,
    )
    company_tutor_name = models.CharField(
        _("company tutor name"),
        max_length=200,
        blank=True,
    )
    company_tutor_email = models.EmailField(
        _("company tutor email"),
        blank=True,
    )
    company_tutor_phone = models.CharField(
        _("company tutor phone"),
        max_length=20,
        blank=True,
    )

    # Administrative validation (for internships)
    admin_validated = models.BooleanField(
        _("administratively validated"),
        default=False,
    )
    admin_validated_at = models.DateTimeField(
        _("admin validation date"),
        null=True,
        blank=True,
    )
    admin_validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_validated_projects",
        verbose_name=_("validated by"),
    )

    class Meta:
        verbose_name = _("academic project")
        verbose_name_plural = _("academic projects")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.subject} - {self.student}"

    def save(self, *args, **kwargs):
        """Auto-set academic year if not provided."""
        if not self.academic_year:
            self.academic_year = get_current_academic_year()
        super().save(*args, **kwargs)

    def is_user_involved(self, user) -> bool:
        """Check if user is involved in this project."""
        return (
            self.student_id == user.id
            or self.referent_id == user.id
            or self.supervisor_id == user.id
            or user.is_staff
        )


class Proposal(BaseModel):
    """
    Project proposal model.

    Represents either:
    - A professor's proposal (is_professor_proposal=True): Subject waiting for students
    - A student's proposal (is_professor_proposal=False): Subject in development

    Inherits from BaseModel:
        - id: UUID primary key
        - created: auto-set on creation
        - modified: auto-updated on save
    """

    title = models.CharField(
        _("title"),
        max_length=500,
    )
    description = models.TextField(
        _("description"),
    )
    project_type = models.CharField(
        _("type"),
        max_length=20,
        choices=AcademicProjectType.choices,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ProposalStatus.choices,
        default=ProposalStatus.OPEN,
    )

    # Creator (professor or student)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_proposals",
        verbose_name=_("created by"),
    )

    # Supervising professor
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_proposals",
        verbose_name=_("supervisor"),
    )

    # Academic year
    academic_year = models.CharField(
        _("academic year"),
        max_length=9,
    )

    # Is this a professor proposal (incoming) or student proposal (in development)
    is_professor_proposal = models.BooleanField(
        _("professor proposal"),
        default=True,
    )

    # Resulting project (when proposal is validated and converted)
    resulting_project = models.OneToOneField(
        AcademicProject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_proposal",
        verbose_name=_("resulting project"),
    )

    class Meta:
        verbose_name = _("proposal")
        verbose_name_plural = _("proposals")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_project_type_display()})"

    def save(self, *args, **kwargs):
        """Auto-set academic year if not provided."""
        if not self.academic_year:
            self.academic_year = get_current_academic_year()
        super().save(*args, **kwargs)

    def can_be_managed_by(self, user) -> bool:
        """Check if user can manage this proposal (edit, delete, accept applications)."""
        return (
            self.created_by_id == user.id
            or self.supervisor_id == user.id
            or user.is_staff
        )


class ProposalApplication(BaseModel):
    """
    Application from a student to a proposal.

    Inherits from BaseModel:
        - id: UUID primary key
        - created: auto-set on creation
        - modified: auto-updated on save
    """

    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("proposal"),
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="proposal_applications",
        verbose_name=_("applicant"),
    )
    motivation = models.TextField(
        _("motivation"),
        blank=True,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )

    class Meta:
        verbose_name = _("proposal application")
        verbose_name_plural = _("proposal applications")
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["proposal", "applicant"],
                name="unique_proposal_application",
            )
        ]

    def __str__(self) -> str:
        return f"{self.applicant} - {self.proposal.title}"


class PeriodStatus(models.TextChoices):
    """Status choices for academic periods."""

    DRAFT = "draft", _("Brouillon")
    OPEN = "open", _("Ouvert")
    CLOSED = "closed", _("Clôturé")
    ARCHIVED = "archived", _("Archivé")


class TERPeriod(BaseModel):
    """
    TER (Travail d'Étude et de Recherche) academic period.

    Defines the timeline and configuration for a TER period:
    - Group formation dates
    - Subject selection dates
    - Ranking deadlines
    - Assignment dates
    """

    name = models.CharField(
        _("name"),
        max_length=200,
        help_text=_("e.g., 'TER 2024-2025 S1'"),
    )
    academic_year = models.CharField(
        _("academic year"),
        max_length=9,
        help_text=_("Format: 2024-2025"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PeriodStatus.choices,
        default=PeriodStatus.DRAFT,
    )

    # Group formation phase
    group_formation_start = models.DateField(
        _("group formation start"),
        help_text=_("Date when students can start forming groups"),
    )
    group_formation_end = models.DateField(
        _("group formation end"),
        help_text=_("Deadline for group formation"),
    )

    # Subject selection phase
    subject_selection_start = models.DateField(
        _("subject selection start"),
        help_text=_("Date when groups can start selecting subjects"),
    )
    subject_selection_end = models.DateField(
        _("subject selection end"),
        help_text=_("Deadline for subject selection/ranking"),
    )

    # Assignment phase
    assignment_date = models.DateField(
        _("assignment date"),
        help_text=_("Date when algorithm runs to assign subjects"),
    )

    # Project execution phase
    project_start = models.DateField(
        _("project start"),
        help_text=_("Start date for TER projects"),
    )
    project_end = models.DateField(
        _("project end"),
        help_text=_("End date for TER projects"),
    )

    # Configuration
    min_group_size = models.PositiveSmallIntegerField(
        _("minimum group size"),
        default=1,
    )
    max_group_size = models.PositiveSmallIntegerField(
        _("maximum group size"),
        default=4,
    )

    class Meta:
        verbose_name = _("TER period")
        verbose_name_plural = _("TER periods")
        ordering = ["-academic_year", "-created"]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year})"

    def save(self, *args, **kwargs):
        if not self.academic_year:
            self.academic_year = get_current_academic_year()
        super().save(*args, **kwargs)


class StagePeriod(BaseModel):
    """
    Internship (Stage) academic period.

    Defines the timeline and configuration for an internship period:
    - Offer submission dates
    - Application deadlines
    - Internship execution dates
    """

    name = models.CharField(
        _("name"),
        max_length=200,
        help_text=_("e.g., 'Stage M2 2024-2025'"),
    )
    academic_year = models.CharField(
        _("academic year"),
        max_length=9,
        help_text=_("Format: 2024-2025"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=PeriodStatus.choices,
        default=PeriodStatus.DRAFT,
    )

    # Offer phase
    offer_submission_start = models.DateField(
        _("offer submission start"),
        help_text=_("Date when companies can start submitting offers"),
    )
    offer_submission_end = models.DateField(
        _("offer submission end"),
        help_text=_("Deadline for offer submissions"),
    )

    # Application phase
    application_start = models.DateField(
        _("application start"),
        help_text=_("Date when students can start applying"),
    )
    application_end = models.DateField(
        _("application end"),
        help_text=_("Deadline for applications"),
    )

    # Internship execution
    internship_start = models.DateField(
        _("internship start"),
        help_text=_("Start date for internships"),
    )
    internship_end = models.DateField(
        _("internship end"),
        help_text=_("End date for internships"),
    )

    class Meta:
        verbose_name = _("internship period")
        verbose_name_plural = _("internship periods")
        ordering = ["-academic_year", "-created"]

    def __str__(self) -> str:
        return f"{self.name} ({self.academic_year})"

    def save(self, *args, **kwargs):
        if not self.academic_year:
            self.academic_year = get_current_academic_year()
        super().save(*args, **kwargs)


class GroupStatus(models.TextChoices):
    """Status choices for student groups (FSM states)."""

    OUVERT = "ouvert", _("Ouvert")  # Open for new members
    FORME = "forme", _("Formé")  # Formed, waiting for subject selection
    CLOTURE = "cloture", _("Clôturé")  # Closed, subject assigned


class StudentGroup(BaseModel):
    """
    Student group model for TER and Stage projects.

    Uses django-fsm for state management with protected transitions:
    - ouvert: Group is open for new members to join
    - formé: Group is formed, members locked, can select subjects
    - clôturé: Group is closed, subject has been assigned

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
        choices=AcademicProjectType.choices,
        help_text=_("TER or Stage"),
    )

    # Link to academic period (one of these will be set based on project_type)
    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name=_("TER period"),
    )

    stage_period = models.ForeignKey(
        StagePeriod,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="groups",
        verbose_name=_("internship period"),
    )

    # Assigned subject/proposal (set when group is closed)
    assigned_proposal = models.ForeignKey(
        Proposal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_groups",
        verbose_name=_("assigned proposal"),
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
        Transition from ouvert to formé.

        Called when:
        - Group leader manually locks the group
        - Group formation deadline passes
        """
        pass

    @transition(field=status, source=GroupStatus.FORME, target=GroupStatus.CLOTURE)
    def close_group(self):
        """
        Transition from formé to clôturé.

        Called when:
        - Subject is assigned to the group
        - Assignment algorithm completes
        """
        pass

    @transition(field=status, source=GroupStatus.FORME, target=GroupStatus.OUVERT)
    def reopen_group(self):
        """
        Transition from formé back to ouvert.

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
