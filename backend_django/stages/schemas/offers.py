"""
Stage Offer schemas for API requests and responses.
"""

from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class UserMinimalSchema(Schema):
    """Minimal user information for display."""

    id: UUID
    email: str
    first_name: str
    last_name: str


class StageOfferListSchema(Schema):
    """Schema for Stage offer list responses."""

    id: UUID
    title: str
    company_name: str
    location: str
    domain: str
    supervisor: UserMinimalSchema | None
    status: str
    max_students: int
    stage_period_id: UUID
    created: str


class StageOfferDetailSchema(Schema):
    """Detailed schema for Stage offer responses."""

    id: UUID
    title: str
    description: str
    company_name: str
    location: str
    domain: str
    prerequisites: str
    supervisor: UserMinimalSchema | None
    max_students: int
    status: str
    rejection_reason: str
    stage_period_id: UUID
    created: str
    modified: str
    is_favorite: bool = False


class StageOfferCreateSchema(Schema):
    """Schema for creating a Stage offer."""

    stage_period_id: UUID
    title: str
    description: str
    company_name: str
    location: str = ""
    domain: str
    prerequisites: str = ""
    max_students: int = 1

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

    @field_validator("company_name")
    @classmethod
    def company_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le nom de l'entreprise est requis.")
        return v.strip()

    @field_validator("domain")
    @classmethod
    def domain_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le domaine est requis.")
        return v.strip()

    @field_validator("max_students")
    @classmethod
    def validate_max_students(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Le nombre d'etudiants doit etre au moins 1.")
        if v > 10:
            raise ValueError("Le nombre d'etudiants ne peut pas depasser 10.")
        return v


class StageOfferUpdateSchema(Schema):
    """Schema for updating a Stage offer."""

    title: str | None = None
    description: str | None = None
    company_name: str | None = None
    location: str | None = None
    domain: str | None = None
    prerequisites: str | None = None
    max_students: int | None = None

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


class StageOfferRejectSchema(Schema):
    """Schema for rejecting a Stage offer."""

    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La raison du rejet est requise.")
        if len(v.strip()) < 10:
            raise ValueError("La raison doit faire au moins 10 caracteres.")
        return v.strip()


class StageFavoriteSchema(Schema):
    """Schema for favorite responses."""

    id: UUID
    student_id: UUID
    offer_id: UUID
    created: str
