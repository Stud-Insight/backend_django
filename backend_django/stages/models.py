"""
Models for Stage (Internship) management.

Contains:
- StagePeriod: Academic period for internships
- StageOffer: Internship offers from companies/supervisors
- StageRanking: Student rankings of offers
- StageFavorite: Individual student favorites
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


class OfferStatus(models.TextChoices):
    """Status choices for stage offers."""

    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Soumis")
    VALIDATED = "validated", _("Valide")
    REJECTED = "rejected", _("Rejete")


class ApplicationStatus(models.TextChoices):
    """Status choices for stage applications."""

    PENDING = "pending", _("En attente")
    ACCEPTED = "accepted", _("Acceptee")
    REJECTED = "rejected", _("Rejetee")
    WITHDRAWN = "withdrawn", _("Retiree")
    CONFIRMED = "confirmed", _("Confirmee")


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


class StageOffer(BaseModel):
    """
    Internship offer proposed by a company or external supervisor.

    Replaces the Proposal model specifically for internships.
    Links to a StagePeriod and can be assigned to students.
    """

    stage_period = models.ForeignKey(
        StagePeriod,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name=_("internship period"),
    )
    title = models.CharField(
        _("title"),
        max_length=500,
    )
    description = models.TextField(
        _("description"),
    )
    company_name = models.CharField(
        _("company name"),
        max_length=255,
    )
    location = models.CharField(
        _("location"),
        max_length=255,
        blank=True,
        help_text=_("City or remote"),
    )
    domain = models.CharField(
        _("domain"),
        max_length=100,
        help_text=_("e.g., 'IA/ML', 'Securite', 'Web', 'DevOps'"),
    )
    prerequisites = models.TextField(
        _("prerequisites"),
        blank=True,
        help_text=_("Required skills or knowledge"),
    )

    # External supervisor who submitted the offer
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stage_offers_created",
        verbose_name=_("supervisor"),
    )

    max_students = models.PositiveSmallIntegerField(
        _("maximum students"),
        default=1,
        help_text=_("Number of students that can be assigned"),
    )

    status = FSMField(
        _("status"),
        default=OfferStatus.DRAFT,
        choices=OfferStatus.choices,
    )

    rejection_reason = models.TextField(
        _("rejection reason"),
        blank=True,
    )

    class Meta:
        verbose_name = _("internship offer")
        verbose_name_plural = _("internship offers")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.title} @ {self.company_name}"

    def can_be_managed_by(self, user) -> bool:
        """Check if user can manage this offer (edit, delete)."""
        return (
            self.supervisor_id == user.id
            or user.is_staff
        )


class StageRanking(BaseModel):
    """
    Student ranking of stage offers.

    Each student ranks offers in order of preference.
    Used by the assignment algorithm to match students to offers.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_rankings",
        verbose_name=_("student"),
    )
    offer = models.ForeignKey(
        StageOffer,
        on_delete=models.CASCADE,
        related_name="rankings",
        verbose_name=_("offer"),
    )
    rank = models.PositiveSmallIntegerField(
        _("rank"),
        help_text=_("1 = most preferred"),
    )

    class Meta:
        verbose_name = _("internship ranking")
        verbose_name_plural = _("internship rankings")
        ordering = ["student", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "offer"],
                name="unique_stage_student_offer",
            ),
            models.UniqueConstraint(
                fields=["student", "rank"],
                name="unique_stage_student_rank",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student.email} - #{self.rank}: {self.offer.title}"


class StageFavorite(BaseModel):
    """
    Individual student favorite for stage offers.

    Allows students to mark offers as favorites before final ranking.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_favorites",
        verbose_name=_("student"),
    )
    offer = models.ForeignKey(
        StageOffer,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name=_("offer"),
    )

    class Meta:
        verbose_name = _("internship favorite")
        verbose_name_plural = _("internship favorites")
        constraints = [
            models.UniqueConstraint(
                fields=["student", "offer"],
                name="unique_stage_student_favorite",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student.email} - {self.offer.title}"


class StageApplication(BaseModel):
    """
    Student application to a stage offer.

    Tracks the full application lifecycle from submission to confirmation.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stage_applications",
        verbose_name=_("student"),
    )
    offer = models.ForeignKey(
        StageOffer,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("offer"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )

    # Application details
    motivation = models.TextField(
        _("motivation"),
        help_text=_("Student's motivation letter or message"),
    )
    cv_url = models.URLField(
        _("CV URL"),
        blank=True,
        help_text=_("Link to student's CV"),
    )

    # Decision tracking
    decision_date = models.DateTimeField(
        _("decision date"),
        null=True,
        blank=True,
        help_text=_("When the application was accepted/rejected"),
    )
    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_decisions_made",
        verbose_name=_("decision by"),
    )
    rejection_reason = models.TextField(
        _("rejection reason"),
        blank=True,
    )

    # Confirmation tracking (after acceptance)
    confirmed_at = models.DateTimeField(
        _("confirmed at"),
        null=True,
        blank=True,
        help_text=_("When the student confirmed the assignment"),
    )

    # Academic encadrant assignment (after confirmation)
    academic_supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_supervisions",
        verbose_name=_("academic supervisor"),
        help_text=_("Academic supervisor assigned after confirmation"),
    )

    class Meta:
        verbose_name = _("stage application")
        verbose_name_plural = _("stage applications")
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "offer"],
                name="unique_stage_application",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.student.email} -> {self.offer.title} ({self.status})"

    def can_be_decided_by(self, user) -> bool:
        """Check if user can accept/reject this application."""
        # Offer supervisor or staff can decide
        return (
            self.offer.supervisor_id == user.id
            or user.is_staff
        )

    def can_be_withdrawn_by(self, user) -> bool:
        """Check if user can withdraw this application."""
        return self.student_id == user.id and self.status == ApplicationStatus.PENDING

    def can_be_confirmed_by(self, user) -> bool:
        """Check if user can confirm this application."""
        return self.student_id == user.id and self.status == ApplicationStatus.ACCEPTED

    @property
    def is_modifiable(self) -> bool:
        """Check if application can still be modified."""
        return self.status == ApplicationStatus.PENDING


class StageGradeStatus(models.TextChoices):
    """Status choices for stage grades."""

    DRAFT = "draft", _("Brouillon")
    SUBMITTED = "submitted", _("Soumis")
    FINALIZED = "finalized", _("Finalise")


class StageGrade(BaseModel):
    """
    Grade record for a confirmed stage application.

    Contains both academic grade (from encadrant) and company grade (from externe),
    with a final computed average.
    """

    application = models.OneToOneField(
        StageApplication,
        on_delete=models.CASCADE,
        related_name="grade",
        verbose_name=_("application"),
    )
    stage_period = models.ForeignKey(
        StagePeriod,
        on_delete=models.CASCADE,
        related_name="grades",
        verbose_name=_("internship period"),
    )

    # Academic grade (encadrant)
    academic_grade = models.DecimalField(
        _("academic grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Academic grade on 0-20 scale"),
    )
    academic_grade_comment = models.TextField(
        _("academic grade comment"),
        blank=True,
    )
    academic_graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_academic_grades_given",
        verbose_name=_("academic graded by"),
    )
    academic_graded_at = models.DateTimeField(
        _("academic graded at"),
        null=True,
        blank=True,
    )

    # Company grade (externe)
    company_grade = models.DecimalField(
        _("company grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Company grade on 0-20 scale"),
    )
    company_grade_comment = models.TextField(
        _("company grade comment"),
        blank=True,
    )
    company_graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stage_company_grades_given",
        verbose_name=_("company graded by"),
    )
    company_graded_at = models.DateTimeField(
        _("company graded at"),
        null=True,
        blank=True,
    )

    # Final computed grade
    final_grade = models.DecimalField(
        _("final grade"),
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Average of academic and company grades"),
    )

    # Status tracking
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=StageGradeStatus.choices,
        default=StageGradeStatus.DRAFT,
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
        related_name="stage_grades_finalized",
        verbose_name=_("finalized by"),
    )

    class Meta:
        verbose_name = _("stage grade")
        verbose_name_plural = _("stage grades")
        ordering = ["-created"]

    def __str__(self) -> str:
        student = self.application.student
        grade_str = f"{self.final_grade}/20" if self.final_grade else "Non note"
        return f"{student.email} - {grade_str}"

    def compute_final_grade(self):
        """Compute the final grade as the average of academic and company grades."""
        if self.academic_grade is not None and self.company_grade is not None:
            self.final_grade = (self.academic_grade + self.company_grade) / 2
        else:
            self.final_grade = None

    def is_modifiable(self) -> bool:
        """Check if grade can still be modified."""
        return self.status != StageGradeStatus.FINALIZED
