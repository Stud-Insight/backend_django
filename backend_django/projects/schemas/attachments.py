"""
Attachment schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema


class AttachmentSchema(Schema):
    """Attachment response schema."""

    id: UUID
    original_filename: str
    content_type: str
    size: int
    created: datetime


class AttachmentUploadResponse(Schema):
    """Response after successful upload."""

    success: bool
    message: str
    file_id: UUID
