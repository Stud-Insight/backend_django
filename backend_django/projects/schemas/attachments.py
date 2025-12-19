"""
Attachment and academic project schemas.
"""

from datetime import date
from datetime import datetime
from uuid import UUID

from ninja import Schema

from backend_django.projects.models import AcademicProjectType


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


class AcademicProjectSchema(Schema):
    """Academic project response schema."""

    id: UUID
    student_id: UUID
    referent_id: UUID | None
    supervisor_id: UUID | None
    subject: str
    project_type: str
    start_date: date
    end_date: date
    files: list[AttachmentSchema]
    created: datetime
    modified: datetime


class AcademicProjectCreateSchema(Schema):
    """Schema for creating academic project."""

    student_id: UUID
    referent_id: UUID | None = None
    supervisor_id: UUID | None = None
    subject: str
    project_type: AcademicProjectType
    start_date: date
    end_date: date
