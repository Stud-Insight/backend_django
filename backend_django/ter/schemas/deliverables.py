"""
TER Deliverables schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.ter.models import MAX_DELIVERABLE_SIZE_BYTES


class TERDeliverableSchema(Schema):
    """Schema for TER deliverable responses."""

    id: UUID
    ter_period_id: UUID
    group_id: UUID
    uploaded_by_id: UUID | None
    original_filename: str
    content_type: str
    size: int
    deliverable_type: str
    description: str
    is_confidential: bool
    upload_status: str
    upload_error: str
    created: datetime
    modified: datetime


class TERDeliverableListSchema(Schema):
    """Schema for TER deliverable list responses."""

    id: UUID
    original_filename: str
    content_type: str
    size: int
    deliverable_type: str
    is_confidential: bool
    upload_status: str
    created: datetime


class TERDeliverableUploadSchema(Schema):
    """Schema for uploading a deliverable."""

    deliverable_type: str = "other"
    description: str = ""
    is_confidential: bool = False

    @field_validator("deliverable_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = ["report", "code", "presentation", "other"]
        if v not in valid_types:
            raise ValueError(f"Type invalide. Valeurs acceptees: {', '.join(valid_types)}")
        return v


class TERDeliverableUploadResponse(Schema):
    """Response schema for deliverable upload."""

    success: bool
    message: str
    deliverable_id: UUID
    upload_status: str
    is_async: bool = False


class TERDeliverableUpdateSchema(Schema):
    """Schema for updating deliverable metadata."""

    deliverable_type: str | None = None
    description: str | None = None
    is_confidential: bool | None = None


class UploadStatusResponse(Schema):
    """Response schema for checking upload status."""

    deliverable_id: UUID
    upload_status: str
    upload_error: str
    original_filename: str
    size: int
    is_complete: bool


# Constants exposed for API documentation
FILE_SIZE_LIMIT_MB = MAX_DELIVERABLE_SIZE_BYTES // (1024 * 1024)
FILE_SIZE_LIMIT_BYTES = MAX_DELIVERABLE_SIZE_BYTES
