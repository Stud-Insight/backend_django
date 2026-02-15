"""
Models for TER (Travail d'Etude et de Recherche) management.

Contains:
- TERPeriod: Academic period for TER projects
- TERSubject: Subject proposals for TER (replaces Proposal for TER)
- TERRanking: Group rankings of subjects
- TERFavorite: Individual student favorites
- BalancingOperation: Audit log for group balancing operations
- TERDeliverable: File deliverables uploaded by groups
- DeliverableUpload: Async upload tracking for large files
"""

import logging
import uuid
from datetime import date
from typing import Optional

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField

from backend_django.core.models import BaseModel

# File size limit: 50MB
MAX_DELIVERABLE_SIZE_BYTES = 50 * 1024 * 1024  # 50MB

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


class PeriodStatus(models.TextChoices):
    """Status choices for academic periods."""

    DRAFT = "draft", _("Brouillon")
    OPEN = "open", _("Ouvert")
    CLOSED = "closed", _("Cloture")
    ARCHIVED = "archived", _("Archive")


class SubjectStatus(models.TextChoices):
    """Status choices for TER subjects."""

    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Soumis")
    VALIDATED = "validated", _("Valide")
    REJECTED = "rejected", _("Rejete")


class TERPeriod(BaseModel):
    """
    TER (Travail d'Etude et de Recherche) academic period.

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

    # Enrolled students for this period
    enrolled_students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="enrolled_ter_periods",
        blank=True,
        verbose_name=_("enrolled students"),
        help_text=_("Students registered for this TER period"),
    )

    professors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="ter_periods_as_professor",
        blank=True,
        verbose_name=_("professors"),
        help_text=_("Professors/encadrants participating in this TER period"),
    )

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ter_periods_as_responsable",
        verbose_name=_("responsable TER"),
        help_text=_("Main responsible for this TER period"),
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


class TERSubject(BaseModel):
    """
    TER subject proposed by a professor/supervisor.

    Replaces the Proposal model specifically for TER projects.
    Links to a TERPeriod and can be assigned to groups.
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="subjects",
        verbose_name=_("TER period"),
        null=True,
        blank=True,
        help_text=_("Optional: can be assigned later when submitting for approval"),
    )
    title = models.CharField(
        _("title"),
        max_length=500,
    )
    description = models.TextField(
        _("description"),
    )
    domain = models.CharField(
        _("domain"),
        max_length=100,
        help_text=_("e.g., 'IA/ML', 'Securite', 'Web', 'Systemes'"),
    )
    tags = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
        verbose_name=_("tags"),
        help_text=_("Technology tags, e.g., ['Python', 'React', 'PostgreSQL']"),
    )
    taches = ArrayField(
        models.CharField(max_length=200),
        default=list,
        blank=True,
        verbose_name=_("taches"),
        help_text=_("Task list for the project"),
    )
    prerequisites = models.TextField(
        _("prerequisites"),
        blank=True,
        help_text=_("Required skills or knowledge"),
    )

    # Professor who created the subject
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ter_subjects_created",
        verbose_name=_("professor"),
    )

    # Supervisor assigned to guide the project (can be different from professor)
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ter_subjects_supervised",
        verbose_name=_("supervisor"),
    )

    max_groups = models.PositiveSmallIntegerField(
        _("maximum groups"),
        default=1,
        help_text=_("Number of groups that can work on this subject"),
    )

    min_group_size = models.PositiveSmallIntegerField(
        _("minimum group size"),
        null=True,
        blank=True,
        help_text=_("Minimum group size for this subject. Must be >= period min_group_size."),
    )
    max_group_size = models.PositiveSmallIntegerField(
        _("maximum group size"),
        null=True,
        blank=True,
        help_text=_("Maximum group size for this subject. Must be <= period max_group_size."),
    )

    status = FSMField(
        _("status"),
        default=SubjectStatus.DRAFT,
        choices=SubjectStatus.choices,
    )

    rejection_reason = models.TextField(
        _("rejection reason"),
        blank=True,
    )

    class Meta:
        verbose_name = _("TER subject")
        verbose_name_plural = _("TER subjects")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.title} ({self.ter_period.name})"

    def clean(self):
        """Validate that subject group size bounds are within period bounds."""
        from django.core.exceptions import ValidationError

        errors = {}
        period = self.ter_period

        if self.min_group_size is not None:
            if self.min_group_size < period.min_group_size:
                errors["min_group_size"] = (
                    f"Ne peut pas être inférieur à la valeur de la période ({period.min_group_size})."
                )
            if self.max_group_size is not None and self.min_group_size > self.max_group_size:
                errors["min_group_size"] = "Ne peut pas être supérieur à max_group_size."

        if self.max_group_size is not None:
            if self.max_group_size > period.max_group_size:
                errors["max_group_size"] = (
                    f"Ne peut pas être supérieur à la valeur de la période ({period.max_group_size})."
                )

        if errors:
            raise ValidationError(errors)

    def can_be_managed_by(self, user) -> bool:
        """Check if user can manage this subject (edit, delete)."""
        return (
            self.professor_id == user.id
            or self.supervisor_id == user.id
            or user.is_staff
        )


class TERRanking(BaseModel):
    """
    Group ranking of TER subjects.

    Each group ranks subjects in order of preference.
    Used by the assignment algorithm to match groups to subjects.
    """

    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.CASCADE,
        related_name="ter_rankings",
        verbose_name=_("group"),
    )
    subject = models.ForeignKey(
        TERSubject,
        on_delete=models.CASCADE,
        related_name="rankings",
        verbose_name=_("subject"),
    )
    rank = models.PositiveSmallIntegerField(
        _("rank"),
        help_text=_("1 = most preferred"),
    )

    class Meta:
        verbose_name = _("TER ranking")
        verbose_name_plural = _("TER rankings")
        ordering = ["group", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "subject"],
                name="unique_ter_group_subject",
            ),
            models.UniqueConstraint(
                fields=["group", "rank"],
                name="unique_ter_group_rank",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.group.name} - #{self.rank}: {self.subject.title}"


class TERFavorite(BaseModel):
    """
    Individual student favorite for TER subjects.

    Allows students to mark subjects as favorites before group discussion.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ter_favorites",
        verbose_name=_("student"),
    )
    subject = models.ForeignKey(
        TERSubject,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name=_("subject"),
    )

    class Meta:
        verbose_name = _("TER favorite")
        verbose_name_plural = _("TER favorites")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject"],
                name="unique_ter_student_favorite",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student.email} - {self.subject.title}"


class BalancingOperationType(models.TextChoices):
    """Types of balancing operations."""

    STUDENT_TO_GROUP = "student_to_group", _("Etudiant vers groupe")
    MERGE_GROUPS = "merge_groups", _("Fusion de groupes")
    FORCE_FORM = "force_form", _("Formation forcee")
    FORCE_ASSIGN = "force_assign", _("Affectation forcee")
    REVERT_ASSIGNMENT = "revert_assignment", _("Annulation d'affectation")
    MOVE_STUDENT = "move_student", _("Deplacement d'etudiant")


class BalancingOperation(BaseModel):
    """
    Audit log for group balancing operations.

    Records all manual and automatic balancing operations performed
    by Respo TER or the balancing algorithm. Provides full traceability
    for group management actions.
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="balancing_operations",
        verbose_name=_("TER period"),
    )

    operation_type = models.CharField(
        _("operation type"),
        max_length=30,
        choices=BalancingOperationType.choices,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="balancing_operations",
        verbose_name=_("performed by"),
        help_text=_("User who performed the operation (null for automatic)"),
    )

    details = models.JSONField(
        _("details"),
        default=dict,
        help_text=_(
            "Operation details: student_id, source_group_id, target_group_id, "
            "similarity_score, etc."
        ),
    )

    is_automatic = models.BooleanField(
        _("automatic"),
        default=False,
        help_text=_("True if performed by the balancing algorithm"),
    )

    reason = models.TextField(
        _("reason"),
        blank=True,
        help_text=_("Explanation for the operation"),
    )

    class Meta:
        verbose_name = _("balancing operation")
        verbose_name_plural = _("balancing operations")
        ordering = ["-created"]

    def __str__(self) -> str:
        performer = "Automatique" if self.is_automatic else (
            self.performed_by.email if self.performed_by else "Inconnu"
        )
        return f"{self.get_operation_type_display()} - {self.ter_period.name} ({performer})"


class DeliverableType(models.TextChoices):
    """Types of TER deliverables."""

    REPORT = "report", _("Rapport")
    CODE = "code", _("Code source")
    PRESENTATION = "presentation", _("Presentation")
    OTHER = "other", _("Autre")


class UploadStatus(models.TextChoices):
    """Status for async file uploads."""

    PENDING = "pending", _("En attente")
    PROCESSING = "processing", _("En cours")
    COMPLETED = "completed", _("Termine")
    FAILED = "failed", _("Echec")


def deliverable_upload_path(instance: "TERDeliverable", filename: str) -> str:
    """Generate upload path for TER deliverables."""
    return f"ter/{instance.ter_period_id}/groups/{instance.group_id}/{uuid.uuid4()}/{filename}"


class TERDeliverable(BaseModel):
    """
    File deliverable uploaded by a group for their TER project.

    Links a file to a specific group within a TER period.
    Supports async uploads for large files via Celery.
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="deliverables",
        verbose_name=_("TER period"),
    )
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.CASCADE,
        related_name="ter_deliverables",
        verbose_name=_("group"),
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ter_deliverables_uploaded",
        verbose_name=_("uploaded by"),
    )

    # File info
    file = models.FileField(
        _("file"),
        upload_to=deliverable_upload_path,
        max_length=500,  # Long paths with UUIDs
        blank=True,  # Blank during async upload
    )
    original_filename = models.CharField(
        _("original filename"),
        max_length=255,
    )
    content_type = models.CharField(
        _("content type"),
        max_length=100,
        default="application/octet-stream",
    )
    size = models.PositiveIntegerField(
        _("file size"),
        help_text=_("Size in bytes"),
        default=0,
    )

    # Metadata
    deliverable_type = models.CharField(
        _("type"),
        max_length=20,
        choices=DeliverableType.choices,
        default=DeliverableType.OTHER,
    )
    description = models.TextField(
        _("description"),
        blank=True,
    )
    is_confidential = models.BooleanField(
        _("confidential"),
        default=False,
        help_text=_("If true, only group members and encadrant can access"),
    )

    # Async upload tracking
    upload_status = models.CharField(
        _("upload status"),
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.COMPLETED,  # Default for sync uploads
    )
    upload_error = models.TextField(
        _("upload error"),
        blank=True,
        help_text=_("Error message if upload failed"),
    )
    celery_task_id = models.CharField(
        _("Celery task ID"),
        max_length=255,
        blank=True,
        help_text=_("Task ID for async upload tracking"),
    )

    class Meta:
        verbose_name = _("TER deliverable")
        verbose_name_plural = _("TER deliverables")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.original_filename} - {self.group.name}"

    def can_be_viewed_by(self, user) -> bool:
        """Check if user can view/download this deliverable."""
        # Group members can always view
        if self.group.members.filter(id=user.id).exists():
            return True
        # Encadrant (professor/supervisor of assigned subject) can view
        if hasattr(self.group, "assigned_subject") and self.group.assigned_subject:
            subject = self.group.assigned_subject
            if subject.professor_id == user.id or subject.supervisor_id == user.id:
                return True
        # Admin/Respo TER can view all
        if user.is_staff or user.is_superuser:
            return True
        # If not confidential, any authenticated user can view
        if not self.is_confidential:
            return True
        return False

    def can_be_managed_by(self, user) -> bool:
        """Check if user can delete/modify this deliverable."""
        # Only uploader, group leader, or admin can manage
        if self.uploaded_by_id == user.id:
            return True
        if self.group.leader_id == user.id:
            return True
        if user.is_staff or user.is_superuser:
            return True
        return False


class DeliverableAccessType(models.TextChoices):
    """Types of deliverable access operations."""

    UPLOAD = "upload", _("Telechargement")
    DOWNLOAD = "download", _("Telechargement")
    UPDATE = "update", _("Modification")
    DELETE = "delete", _("Suppression")
    VIEW = "view", _("Consultation")


class DeliverableAccessLog(BaseModel):
    """
    Audit log for deliverable access operations.

    Tracks all access to deliverables for security and compliance purposes.
    """

    deliverable = models.ForeignKey(
        TERDeliverable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
        verbose_name=_("deliverable"),
        help_text=_("The deliverable that was accessed (null if deleted)"),
    )
    deliverable_filename = models.CharField(
        _("filename"),
        max_length=255,
        help_text=_("Preserved filename for audit after deliverable deletion"),
    )
    deliverable_group_name = models.CharField(
        _("group name"),
        max_length=200,
        blank=True,
        help_text=_("Preserved group name for audit"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="deliverable_access_logs",
        verbose_name=_("user"),
    )
    user_email = models.EmailField(
        _("user email"),
        help_text=_("Preserved email for audit after user deletion"),
    )

    access_type = models.CharField(
        _("access type"),
        max_length=20,
        choices=DeliverableAccessType.choices,
    )

    ip_address = models.GenericIPAddressField(
        _("IP address"),
        null=True,
        blank=True,
    )
    user_agent = models.TextField(
        _("user agent"),
        blank=True,
    )

    details = models.JSONField(
        _("details"),
        default=dict,
        blank=True,
        help_text=_("Additional context about the operation"),
    )

    class Meta:
        verbose_name = _("deliverable access log")
        verbose_name_plural = _("deliverable access logs")
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["deliverable", "-created"]),
            models.Index(fields=["user", "-created"]),
            models.Index(fields=["access_type", "-created"]),
        ]

    def __str__(self) -> str:
        return f"{self.access_type} - {self.deliverable_filename} by {self.user_email}"

    @classmethod
    def log_access(
        cls,
        deliverable: TERDeliverable,
        user,
        access_type: str,
        request=None,
        details: Optional[dict] = None,
    ) -> "DeliverableAccessLog":
        """
        Create an audit log entry for deliverable access.

        Args:
            deliverable: The deliverable being accessed
            user: The user performing the action
            access_type: Type of access (upload, download, update, delete, view)
            request: HTTP request object (for IP and user agent)
            details: Additional context dictionary
        """
        ip_address = None
        user_agent = ""

        if request:
            # Get IP address
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")

            user_agent = request.META.get("HTTP_USER_AGENT", "")

        return cls.objects.create(
            deliverable=deliverable if access_type != DeliverableAccessType.DELETE else None,
            deliverable_filename=deliverable.original_filename,
            deliverable_group_name=deliverable.group.name if deliverable.group else "",
            user=user,
            user_email=user.email,
            access_type=access_type,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else "",  # Truncate long user agents
            details=details or {},
        )


class GradeStatus(models.TextChoices):
    """Status choices for TER grades."""

    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Soumis")
    FINALIZED = "finalized", _("Finalise")


class TERGrade(BaseModel):
    """
    TER group grade entered by encadrant.

    Supports optional individual grading where students can opt-in
    to receive a different grade from the group grade.
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="grades",
        verbose_name=_("TER period"),
    )
    group = models.OneToOneField(
        "groups.Group",
        on_delete=models.CASCADE,
        related_name="ter_grade",
        verbose_name=_("group"),
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ter_grades_given",
        verbose_name=_("graded by"),
        help_text=_("Encadrant who entered the grade"),
    )

    # Group grade (0-20 scale)
    group_grade = models.DecimalField(
        _("group grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Grade on 0-20 scale"),
    )
    group_grade_comment = models.TextField(
        _("grade comment"),
        blank=True,
        help_text=_("Comment explaining the grade"),
    )

    # Individual grading option
    individual_grading_enabled = models.BooleanField(
        _("individual grading enabled"),
        default=False,
        help_text=_("If true, students can opt-in for individual grades"),
    )

    # Finalization
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=GradeStatus.choices,
        default=GradeStatus.DRAFT,
    )
    finalized_at = models.DateTimeField(
        _("finalized at"),
        null=True,
        blank=True,
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ter_grades_finalized",
        verbose_name=_("finalized by"),
    )

    class Meta:
        verbose_name = _("TER grade")
        verbose_name_plural = _("TER grades")
        ordering = ["-created"]

    def __str__(self) -> str:
        grade_str = f"{self.group_grade}/20" if self.group_grade else "Non noté"
        return f"{self.group.name} - {grade_str}"

    def can_be_graded_by(self, user) -> bool:
        """Check if user can enter/modify grades for this group."""
        # Encadrant assigned to the group's subject can grade
        if hasattr(self.group, "assigned_subject") and self.group.assigned_subject:
            subject = self.group.assigned_subject
            if subject.professor_id == user.id or subject.supervisor_id == user.id:
                return True
        # Admin can grade
        if user.is_staff or user.is_superuser:
            return True
        return False

    def is_modifiable(self) -> bool:
        """Check if grade can still be modified."""
        return self.status != GradeStatus.FINALIZED


class TERIndividualGrade(BaseModel):
    """
    Individual grade for a student who opted-in.

    Students can opt-in to receive an individual grade different
    from the group grade. The final grade is computed based on opt-in status.
    """

    grade = models.ForeignKey(
        TERGrade,
        on_delete=models.CASCADE,
        related_name="individual_grades",
        verbose_name=_("TER grade"),
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ter_individual_grades",
        verbose_name=_("student"),
    )

    # Opt-in tracking
    opted_in = models.BooleanField(
        _("opted in"),
        default=False,
    )
    opted_in_at = models.DateTimeField(
        _("opted in at"),
        null=True,
        blank=True,
    )

    # Individual grade (only used if opted_in=True)
    individual_grade = models.DecimalField(
        _("individual grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Individual grade on 0-20 scale"),
    )
    individual_grade_comment = models.TextField(
        _("individual grade comment"),
        blank=True,
    )

    # Final computed grade
    final_grade = models.DecimalField(
        _("final grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Computed final grade (individual if opted-in, otherwise group)"),
    )

    class Meta:
        verbose_name = _("TER individual grade")
        verbose_name_plural = _("TER individual grades")
        constraints = [
            models.UniqueConstraint(
                fields=["grade", "student"],
                name="unique_ter_individual_grade_per_student",
            ),
        ]

    def __str__(self) -> str:
        grade_str = f"{self.final_grade}/20" if self.final_grade else "Non calculé"
        return f"{self.student.email} - {grade_str}"

    def compute_final_grade(self) -> None:
        """Compute final grade based on opt-in status."""
        if self.opted_in and self.individual_grade is not None:
            self.final_grade = self.individual_grade
        elif self.grade.group_grade is not None:
            self.final_grade = self.grade.group_grade
        else:
            self.final_grade = None


class PeerReviewSession(BaseModel):
    """
    Ephemeral token mapping for anonymous peer review.

    This table is DESTROYED after the peer review deadline to ensure
    true anonymity (ARCH-15). Before destruction, it enables:
    - Tracking who has/hasn't submitted for reminders
    - Preventing duplicate submissions
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="peer_review_sessions",
        verbose_name=_("TER period"),
    )
    ephemeral_token = models.UUIDField(
        _("ephemeral token"),
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="peer_review_sessions",
        verbose_name=_("student"),
    )
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.CASCADE,
        related_name="peer_review_sessions",
        verbose_name=_("group"),
    )
    expires_at = models.DateTimeField(
        _("expires at"),
        help_text=_("When this session (and the mapping) will be destroyed"),
    )

    class Meta:
        verbose_name = _("peer review session")
        verbose_name_plural = _("peer review sessions")
        constraints = [
            models.UniqueConstraint(
                fields=["ter_period", "student"],
                name="unique_peer_review_session_per_student",
            ),
        ]

    def __str__(self) -> str:
        return f"Session {self.ephemeral_token} - {self.student.email}"


class PeerReview(BaseModel):
    """
    Anonymous peer review submitted by a student.

    Uses ephemeral_token instead of direct user link. After the
    PeerReviewSession is destroyed, it becomes impossible to trace
    who submitted which review (NFR-S7).
    """

    ter_period = models.ForeignKey(
        TERPeriod,
        on_delete=models.CASCADE,
        related_name="peer_reviews",
        verbose_name=_("TER period"),
    )
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.CASCADE,
        related_name="peer_reviews",
        verbose_name=_("group"),
    )

    # Token-based anonymity (no FK to User for reviewer)
    reviewer_token = models.CharField(
        _("reviewer token"),
        max_length=36,
        help_text=_("Ephemeral token of the reviewer (session may be deleted)"),
    )

    # Who is being reviewed
    reviewed_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="peer_reviews_received",
        verbose_name=_("reviewed student"),
    )

    # Review scores (1-5 scale)
    contribution_score = models.PositiveSmallIntegerField(
        _("contribution score"),
        help_text=_("1-5 scale for project contribution"),
    )
    collaboration_score = models.PositiveSmallIntegerField(
        _("collaboration score"),
        help_text=_("1-5 scale for teamwork and communication"),
    )
    technical_skill_score = models.PositiveSmallIntegerField(
        _("technical skill score"),
        help_text=_("1-5 scale for technical abilities"),
    )

    comment = models.TextField(
        _("comment"),
        blank=True,
        help_text=_("Optional qualitative feedback"),
    )

    class Meta:
        verbose_name = _("peer review")
        verbose_name_plural = _("peer reviews")
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "reviewer_token", "reviewed_student"],
                name="unique_peer_review_per_reviewer_reviewed",
            ),
        ]

    def __str__(self) -> str:
        return f"Review for {self.reviewed_student.email} (token: {self.reviewer_token[:8]}...)"

    @property
    def average_score(self) -> float:
        """Calculate average of the three scores."""
        return (self.contribution_score + self.collaboration_score + self.technical_skill_score) / 3
