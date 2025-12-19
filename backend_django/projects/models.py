"""
Models for academic projects and file attachments.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from backend_django.core.models import BaseModel


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
        on_delete=models.CASCADE,
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

    class Meta:
        verbose_name = _("academic project")
        verbose_name_plural = _("academic projects")
        ordering = ["-created"]

    def __str__(self) -> str:
        return f"{self.subject} - {self.student}"
