"""
Proposal schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import ProposalStatus
from backend_django.projects.schemas.projects import UserMinimalSchema


class ApplicationSchema(Schema):
    """Schema for proposal application."""

    id: UUID
    applicant: UserMinimalSchema
    motivation: str
    status: str
    created: datetime


class ProposalListSchema(Schema):
    """Schema for proposal list view."""

    id: UUID
    title: str
    description: str
    project_type: str
    status: str
    created_by: UserMinimalSchema
    supervisor: UserMinimalSchema | None
    academic_year: str
    is_professor_proposal: bool
    applications_count: int
    created: datetime
    modified: datetime


class ProposalDetailSchema(ProposalListSchema):
    """Detailed proposal schema with applications."""

    applications: list[ApplicationSchema]
    resulting_project_id: UUID | None


class ProposalCreateSchema(Schema):
    """Schema for creating a proposal."""

    title: str
    description: str
    project_type: str
    academic_year: str = ""  # Auto-calculated if empty
    supervisor_id: UUID | None = None
    is_professor_proposal: bool = True

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le titre est requis.")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La description est requise.")
        return v.strip()

    @field_validator("project_type")
    @classmethod
    def valid_project_type(cls, v: str) -> str:
        valid_types = [choice.value for choice in AcademicProjectType]
        if v not in valid_types:
            raise ValueError(f"Type de projet invalide. Choix: {', '.join(valid_types)}")
        return v


class ProposalUpdateSchema(Schema):
    """Schema for updating a proposal."""

    title: str | None = None
    description: str | None = None
    supervisor_id: UUID | None = None


class ApplicationCreateSchema(Schema):
    """Schema for applying to a proposal."""

    motivation: str = ""


class ProposalStatusUpdateSchema(Schema):
    """Schema for proposal status transition."""

    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        valid_statuses = [choice.value for choice in ProposalStatus]
        if v not in valid_statuses:
            raise ValueError(f"Statut invalide. Choix: {', '.join(valid_statuses)}")
        return v
