"""
Academic project schemas for API requests and responses.
"""

from datetime import date
from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.projects.models import AcademicProjectStatus
from backend_django.projects.models import AcademicProjectType


class UserMinimalSchema(Schema):
    """Minimal user information for references."""

    id: UUID
    first_name: str
    last_name: str
    email: str

    @staticmethod
    def from_user(user) -> "UserMinimalSchema":
        """Create schema from User model."""
        return UserMinimalSchema(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
        )


class AttachmentMinimalSchema(Schema):
    """Minimal attachment information."""

    id: UUID
    original_filename: str
    content_type: str
    size: int
    created: datetime


class AcademicProjectListSchema(Schema):
    """Schema for project list view."""

    id: UUID
    subject: str
    project_type: str
    status: str
    student: UserMinimalSchema
    referent: UserMinimalSchema | None
    supervisor: UserMinimalSchema | None
    start_date: date
    end_date: date
    academic_year: str
    admin_validated: bool
    created: datetime
    modified: datetime


class AcademicProjectDetailSchema(AcademicProjectListSchema):
    """Detailed project schema with all fields."""

    description: str
    files: list[AttachmentMinimalSchema]
    # Internship-specific fields
    company_name: str
    company_address: str
    company_tutor_name: str
    company_tutor_email: str
    company_tutor_phone: str
    admin_validated_at: datetime | None
    admin_validated_by: UserMinimalSchema | None


class AcademicProjectCreateSchema(Schema):
    """Schema for creating a project."""

    subject: str
    project_type: str
    description: str = ""
    start_date: date
    end_date: date
    academic_year: str = ""  # Auto-calculated if empty
    student_id: UUID | None = None  # For admin creating for a student
    referent_id: UUID | None = None
    supervisor_id: UUID | None = None
    # Internship fields
    company_name: str = ""
    company_address: str = ""
    company_tutor_name: str = ""
    company_tutor_email: str = ""
    company_tutor_phone: str = ""

    @field_validator("subject")
    @classmethod
    def subject_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le sujet est requis.")
        return v.strip()

    @field_validator("project_type")
    @classmethod
    def valid_project_type(cls, v: str) -> str:
        valid_types = [choice.value for choice in AcademicProjectType]
        if v not in valid_types:
            raise ValueError(f"Type de projet invalide. Choix: {', '.join(valid_types)}")
        return v

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info) -> date:
        if "start_date" in info.data and info.data["start_date"] and v < info.data["start_date"]:
            raise ValueError("La date de fin doit être après la date de début.")
        return v


class AcademicProjectUpdateSchema(Schema):
    """Schema for updating a project."""

    subject: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    referent_id: UUID | None = None
    supervisor_id: UUID | None = None
    company_name: str | None = None
    company_address: str | None = None
    company_tutor_name: str | None = None
    company_tutor_email: str | None = None
    company_tutor_phone: str | None = None


class ProjectStatusUpdateSchema(Schema):
    """Schema for status transition."""

    status: str
    reason: str | None = None  # For rejection reason

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        valid_statuses = [choice.value for choice in AcademicProjectStatus]
        if v not in valid_statuses:
            raise ValueError(f"Statut invalide. Choix: {', '.join(valid_statuses)}")
        return v


class MessageSchema(Schema):
    """Generic message response."""

    success: bool
    message: str
