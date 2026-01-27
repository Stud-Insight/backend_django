"""
Models for TER (Travail d'Etude et de Recherche) management.

Contains:
- TERPeriod: Academic period for TER projects
- TERSubject: Subject proposals for TER (replaces Proposal for TER)
- TERRanking: Group rankings of subjects
- TERFavorite: Individual student favorites
"""

import logging
from datetime import date

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField

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
