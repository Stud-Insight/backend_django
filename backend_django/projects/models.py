"""
Models for file attachments.

Note: Legacy AcademicProject, Proposal, and ProposalApplication models have been removed.
For TER workflow, use: backend_django.ter.models
For Stage workflow, use: backend_django.stages.models
For Groups, use: backend_django.groups.models
"""

import logging
import uuid
from datetime import date

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from backend_django.core.models import BaseModel
from backend_django.core.roles import is_admin_or_respo

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
        # Admin/Respo can view all
        if is_admin_or_respo(user):
            return True
        return False


# =============================================================================
# Backward Compatibility Re-exports from new apps
# These allow existing code to import from projects.models while we transition
# =============================================================================

# Re-export PeriodStatus from ter (canonical location)
from backend_django.ter.models import PeriodStatus  # noqa: F401, E402

# Re-export TERPeriod and related models
from backend_django.ter.models import (  # noqa: F401, E402
    SubjectStatus as TERSubjectStatus,
    TERFavorite,
    TERPeriod,
    TERRanking,
    TERSubject,
)

# Re-export StagePeriod and related models
from backend_django.stages.models import (  # noqa: F401, E402
    OfferStatus as StageOfferStatus,
    StageFavorite,
    StageOffer,
    StagePeriod,
    StageRanking,
)

# NOTE: Group models are NOT re-exported here to avoid Django model conflicts.
# Import directly from backend_django.groups.models instead:
#   from backend_django.groups.models import (
#       Group, GroupStatus, GroupInvitation, InvitationStatus
#   )
# The alias StudentGroup = Group is also available in groups.models.
