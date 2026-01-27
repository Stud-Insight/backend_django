"""
Group schemas for API requests and responses.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema
from pydantic import field_validator

from backend_django.projects.schemas.projects import UserMinimalSchema
from backend_django.stages.schemas.periods import StagePeriodSchema
from backend_django.ter.schemas.periods import TERPeriodSchema

# Re-export for backward compatibility
__all__ = ["TERPeriodSchema", "StagePeriodSchema"]


class GroupListSchema(Schema):
    """Schema for group list view."""

    id: UUID
    name: str
    leader: UserMinimalSchema
    member_count: int
    status: str
    project_type: str
    created: datetime


class GroupDetailSchema(GroupListSchema):
    """Detailed group schema with members."""

    members: list[UserMinimalSchema]
    ter_period: TERPeriodSchema | None
    stage_period: StagePeriodSchema | None
    assigned_subject_id: UUID | None


class GroupCreateSchema(Schema):
    """Schema for creating a group."""

    name: str
    ter_period_id: UUID | None = None
    stage_period_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le nom du groupe est requis.")
        if len(v.strip()) < 3:
            raise ValueError("Le nom du groupe doit faire au moins 3 caractères.")
        return v.strip()


class GroupUpdateSchema(Schema):
    """Schema for updating a group."""

    name: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Le nom du groupe ne peut pas être vide.")
            if len(v.strip()) < 3:
                raise ValueError("Le nom du groupe doit faire au moins 3 caractères.")
            return v.strip()
        return v


class InvitationSchema(Schema):
    """Schema for group invitation responses."""

    id: UUID
    group_id: UUID
    group_name: str
    invitee: UserMinimalSchema
    invited_by: UserMinimalSchema
    status: str
    message: str
    created: datetime
    responded_at: datetime | None


class InvitationCreateSchema(Schema):
    """Schema for creating an invitation."""

    invitee_email: str
    message: str = ""

    @field_validator("invitee_email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("L'email est requis.")
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Email invalide.")
        return v


class InvitationResponseSchema(Schema):
    """Schema for responding to an invitation."""

    accept: bool


class TransferLeadershipSchema(Schema):
    """Schema for transferring group leadership."""

    new_leader_id: UUID


class SolitaireSchema(Schema):
    """Schema for students without a group (solitaires)."""

    id: UUID
    email: str
    first_name: str
    last_name: str
    pending_invitations: int


class DashboardStatsSchema(Schema):
    """Schema for TER period dashboard statistics."""

    total_groups: int
    total_students_in_groups: int
    total_solitaires: int
    groups_by_status: dict[str, int]
    incomplete_groups_count: int
