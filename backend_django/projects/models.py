from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from backend_django.ter.models import TER

User = settings.AUTH_USER_MODEL

class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        PUBLISHED = "PUBLISHED", "Published"
        REJECTED = "REJECTED", "Rejected"

    ter = models.ForeignKey(
        TER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )

    author = models.ManyToManyField(
        User,
        related_name="authored_projects",
        blank=True,
    )

    externes = models.ManyToManyField(
        User,
        related_name="external_projects",
        blank=True,
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    tasks = models.JSONField(default=list, blank=True)
    language = models.JSONField(default=list, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    min_person = models.PositiveIntegerField(null=True, blank=True)
    max_person = models.PositiveIntegerField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title
