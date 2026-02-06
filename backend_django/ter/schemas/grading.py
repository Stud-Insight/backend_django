"""
TER Grading schemas for API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class TERGradeSchema(Schema):
    """Schema for TER grade responses."""

    id: UUID
    ter_period_id: UUID
    group_id: UUID
    graded_by_id: UUID | None
    group_grade: Decimal | None
    group_grade_comment: str
    individual_grading_enabled: bool
    status: str
    finalized_at: datetime | None
    finalized_by_id: UUID | None
    created: datetime
    modified: datetime


class TERGradeCreateSchema(Schema):
    """Schema for creating/updating a group grade."""

    group_grade: Decimal | None = None
    group_grade_comment: str = ""
    individual_grading_enabled: bool = False

    @field_validator("group_grade")
    @classmethod
    def validate_grade(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < 0 or v > 20:
                raise ValueError("La note doit être entre 0 et 20")
        return v


class TERGradeUpdateSchema(Schema):
    """Schema for updating a group grade."""

    group_grade: Decimal | None = None
    group_grade_comment: str | None = None
    individual_grading_enabled: bool | None = None

    @field_validator("group_grade")
    @classmethod
    def validate_grade(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < 0 or v > 20:
                raise ValueError("La note doit être entre 0 et 20")
        return v


class TERIndividualGradeSchema(Schema):
    """Schema for individual grade responses."""

    id: UUID
    grade_id: UUID
    student_id: UUID
    student_email: str
    student_name: str
    opted_in: bool
    opted_in_at: datetime | None
    individual_grade: Decimal | None
    individual_grade_comment: str
    final_grade: Decimal | None


class TERIndividualGradeUpdateSchema(Schema):
    """Schema for updating an individual grade."""

    individual_grade: Decimal | None = None
    individual_grade_comment: str | None = None

    @field_validator("individual_grade")
    @classmethod
    def validate_grade(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < 0 or v > 20:
                raise ValueError("La note doit être entre 0 et 20")
        return v


class StudentOptInSchema(Schema):
    """Schema for student opt-in response."""

    success: bool
    message: str
    opted_in: bool
    opted_in_at: datetime | None


class PeerReviewSessionSchema(Schema):
    """Schema for peer review session (student's view)."""

    ephemeral_token: UUID
    group_id: UUID
    group_name: str
    expires_at: datetime
    members_to_review: list[dict]  # [{id, email, name}]
    already_reviewed: list[UUID]  # IDs of members already reviewed


class PeerReviewCreateSchema(Schema):
    """Schema for submitting a peer review."""

    reviewed_student_id: UUID
    contribution_score: int
    collaboration_score: int
    technical_skill_score: int
    comment: str = ""

    @field_validator("contribution_score", "collaboration_score", "technical_skill_score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Le score doit être entre 1 et 5")
        return v


class PeerReviewSchema(Schema):
    """Schema for peer review (anonymous view for encadrant)."""

    id: UUID
    reviewed_student_id: UUID
    reviewed_student_name: str
    contribution_score: int
    collaboration_score: int
    technical_skill_score: int
    average_score: float
    comment: str
    created: datetime


class PeerReviewAggregateSchema(Schema):
    """Schema for aggregated peer review scores for a student."""

    student_id: UUID
    student_email: str
    student_name: str
    review_count: int
    avg_contribution: float
    avg_collaboration: float
    avg_technical_skill: float
    overall_average: float
    comments: list[str]


class GradeFinalizeSchema(Schema):
    """Schema for finalize grade response."""

    success: bool
    message: str
    finalized_at: datetime


class GradeExportSchema(Schema):
    """Schema for grade export (Respo TER)."""

    group_name: str
    student_email: str
    student_name: str
    group_grade: Decimal | None
    opted_in: bool
    individual_grade: Decimal | None
    final_grade: Decimal | None
    status: str
