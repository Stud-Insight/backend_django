import uuid

from django.db import models
from model_utils.models import TimeStampedModel


class BaseModel(TimeStampedModel):
    """
    Base model with UUID primary key and created/modified timestamps.

    All models should inherit from this class for consistency.
    Provides:
        - id: UUIDField as primary key
        - created: DateTimeField auto-set on creation
        - modified: DateTimeField auto-updated on save
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
