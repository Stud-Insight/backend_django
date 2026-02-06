"""
Stage Application schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.users.schemas import UserMinimalSchema


class StageApplicationCreateSchema(Schema):
    """Schema for creating a stage application."""

    motivation: str
    cv_url: str = ""

    @field_validator("motivation")
    @classmethod
    def motivation_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La lettre de motivation est requise.")
        if len(v.strip()) < 50:
            raise ValueError("La lettre de motivation doit faire au moins 50 caracteres.")
        return v.strip()


class StageApplicationListSchema(Schema):
    """Schema for application list responses."""

    id: UUID
    student: UserMinimalSchema
    offer_id: UUID
    offer_title: str
    company_name: str
    status: str
    created: str


class StageApplicationDetailSchema(Schema):
    """Detailed schema for application responses."""

    id: UUID
    student: UserMinimalSchema
    offer_id: UUID
    offer_title: str
    company_name: str
    status: str
    motivation: str
    cv_url: str
    decision_date: datetime | None
    decision_by: UserMinimalSchema | None
    rejection_reason: str
    confirmed_at: datetime | None
    academic_supervisor: UserMinimalSchema | None
    created: str
    modified: str


class StageApplicationRejectSchema(Schema):
    """Schema for rejecting an application."""

    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La raison du rejet est requise.")
        if len(v.strip()) < 10:
            raise ValueError("La raison doit faire au moins 10 caracteres.")
        return v.strip()


class StageApplicationConfirmSchema(Schema):
    """Schema for confirming an application (optional academic supervisor)."""

    academic_supervisor_id: UUID | None = None


class ApplicationCountSchema(Schema):
    """Schema for application count per offer."""

    offer_id: UUID
    total: int
    pending: int
    accepted: int
    rejected: int
    confirmed: int


class SuccessSchema(Schema):
    """Generic success response."""

    success: bool
    message: str
