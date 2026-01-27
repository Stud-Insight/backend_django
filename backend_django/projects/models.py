"""
Models for academic projects and file attachments.

Note: TERPeriod, StagePeriod, StudentGroup, GroupInvitation have been moved to
their respective apps (ter/, stages/, groups/). Backward compatibility imports
are provided at the bottom of this file.
"""

import logging
import uuid
from datetime import date

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from backend_django.core.models import BaseModel

logger = logging.getLogger(__name__)


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


# =============================================================================
# Backward Compatibility Re-exports from new apps
# These allow existing code to import from projects.models while we transition
# =============================================================================

# Re-export PeriodStatus from ter (canonical location)
from backend_django.ter.models import PeriodStatus  # noqa: F401, E402

# Re-export TERPeriod and related models
from backend_django.ter.models import (  # noqa: F401, E402
    SubjectStatus as TERSubjectStatus,
    TERPeriod,
    TERSubject,
    TERRanking,
    TERFavorite,
)

# Re-export StagePeriod and related models
from backend_django.stages.models import (  # noqa: F401, E402
    OfferStatus as StageOfferStatus,
    StagePeriod,
    StageOffer,
    StageRanking,
    StageFavorite,
)

# NOTE: Group models are NOT re-exported here to avoid Django model conflicts.
# Import directly from backend_django.groups.models instead:
#   from backend_django.groups.models import (
#       Group, GroupStatus, GroupInvitation, InvitationStatus
#   )
# The alias StudentGroup = Group is also available in groups.models.
