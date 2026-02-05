"""
TER Balancing schemas for API requests and responses.

Provides schemas for the group balancing feature that handles
pre-assignment merging of incomplete groups and solo students.
"""

from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class MergeOperationSchema(Schema):
    """Schema for a single merge/balancing operation."""

    operation_type: str
    entity_a_id: UUID
    entity_b_id: UUID
    similarity_score: float
    reason: str = ""


class BalancingPreviewSchema(Schema):
    """Schema for balancing preview response."""

    solo_students_count: int
    incomplete_groups_count: int
    solo_groups_count: int
    potential_matches_sample: list[dict]
    min_group_size: int
    max_group_size: int


class BalanceGroupsRequestSchema(Schema):
    """Schema for balance groups request."""

    dry_run: bool = False
    merge_solo_students: bool = True
    merge_incomplete_groups: bool = True
    auto_form_groups: bool = True


class BalanceGroupsResponseSchema(Schema):
    """Schema for balance groups response."""

    success: bool
    message: str
    operations: list[MergeOperationSchema]
    students_assigned: int
    groups_merged: int
    groups_auto_formed: int
    warnings: list[str]
    remaining_solo_students: list[UUID]
    remaining_incomplete_groups: list[UUID]


class MoveStudentRequestSchema(Schema):
    """Schema for moving a student between groups."""

    student_id: UUID
    source_group_id: UUID | None = None
    target_group_id: UUID
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("La raison ne peut pas depasser 500 caracteres.")
        return v


class MergeGroupsRequestSchema(Schema):
    """Schema for merging two groups."""

    group_a_id: UUID
    group_b_id: UUID
    new_leader_id: UUID | None = None  # Defaults to surviving group's leader
    new_name: str | None = None
    reason: str = ""

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v: str | None) -> str | None:
        if v and len(v) > 200:
            raise ValueError("Le nom du groupe ne peut pas depasser 200 caracteres.")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("La raison ne peut pas depasser 500 caracteres.")
        return v


class ForceAssignRequestSchema(Schema):
    """Schema for force-assigning a subject to a group."""

    group_id: UUID
    subject_id: UUID
    close_group: bool = True
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("La raison ne peut pas depasser 500 caracteres.")
        return v


class ForceFormRequestSchema(Schema):
    """Schema for force-forming a group."""

    reason: str = ""

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("La raison ne peut pas depasser 500 caracteres.")
        return v


class RevertAssignmentRequestSchema(Schema):
    """Schema for reverting a subject assignment."""

    reopen_group: bool = True
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if len(v) > 500:
            raise ValueError("La raison ne peut pas depasser 500 caracteres.")
        return v


class BalancingOperationSchema(Schema):
    """Schema for a balancing operation audit record."""

    id: UUID
    ter_period_id: UUID
    operation_type: str
    performed_by_id: UUID | None
    performed_by_email: str | None
    details: dict
    is_automatic: bool
    reason: str
    created: str


class BalancingOperationListSchema(Schema):
    """Schema for paginated list of balancing operations."""

    count: int
    page: int
    page_size: int
    results: list[BalancingOperationSchema]
