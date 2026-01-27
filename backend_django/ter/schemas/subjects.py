"""
TER Subject schemas for API requests and responses.
"""

from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.projects.schemas.projects import UserMinimalSchema

# Re-export for convenience
__all__ = ["UserMinimalSchema"]


class TERSubjectListSchema(Schema):
    """Schema for TER subject list responses."""

    id: UUID
    title: str
    domain: str
    professor: UserMinimalSchema | None
    status: str
    max_groups: int
    ter_period_id: UUID
    created: str


class TERSubjectDetailSchema(Schema):
    """Detailed schema for TER subject responses."""

    id: UUID
    title: str
    description: str
    domain: str
    prerequisites: str
    professor: UserMinimalSchema | None
    supervisor: UserMinimalSchema | None
    max_groups: int
    status: str
    rejection_reason: str
    ter_period_id: UUID
    created: str
    modified: str
    is_favorite: bool = False


class TERSubjectCreateSchema(Schema):
    """Schema for creating a TER subject."""

    ter_period_id: UUID
    title: str
    description: str
    domain: str
    prerequisites: str = ""
    supervisor_id: UUID | None = None
    max_groups: int = 1

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le titre est requis.")
        if len(v.strip()) < 10:
            raise ValueError("Le titre doit faire au moins 10 caracteres.")
        return v.strip()

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La description est requise.")
        if len(v.strip()) < 50:
            raise ValueError("La description doit faire au moins 50 caracteres.")
        return v.strip()

    @field_validator("domain")
    @classmethod
    def domain_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le domaine est requis.")
        return v.strip()

    @field_validator("max_groups")
    @classmethod
    def validate_max_groups(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Le nombre de groupes doit etre au moins 1.")
        if v > 5:
            raise ValueError("Le nombre de groupes ne peut pas depasser 5.")
        return v


class TERSubjectUpdateSchema(Schema):
    """Schema for updating a TER subject."""

    title: str | None = None
    description: str | None = None
    domain: str | None = None
    prerequisites: str | None = None
    supervisor_id: UUID | None = None
    max_groups: int | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Le titre ne peut pas etre vide.")
            if len(v.strip()) < 10:
                raise ValueError("Le titre doit faire au moins 10 caracteres.")
            return v.strip()
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("La description ne peut pas etre vide.")
            if len(v.strip()) < 50:
                raise ValueError("La description doit faire au moins 50 caracteres.")
            return v.strip()
        return v


class TERFavoriteSchema(Schema):
    """Schema for favorite responses."""

    id: UUID
    student_id: UUID
    subject_id: UUID
    created: str


class TERSubjectRejectSchema(Schema):
    """Schema for rejecting a TER subject."""

    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La raison du rejet est requise.")
        if len(v.strip()) < 10:
            raise ValueError("La raison doit faire au moins 10 caracteres.")
        return v.strip()
