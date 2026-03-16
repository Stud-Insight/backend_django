"""
Stage Grading schemas for API requests and responses.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class StageGradeSchema(Schema):
    """Schema for stage grade responses."""

    id: UUID
    application_id: UUID
    stage_period_id: UUID
    student_email: str
    student_name: str
    offer_title: str
    company_name: str
    academic_grade: Decimal | None
    academic_grade_comment: str
    academic_graded_by_id: UUID | None
    academic_graded_at: datetime | None
    company_grade: Decimal | None
    company_grade_comment: str
    company_graded_by_id: UUID | None
    company_graded_at: datetime | None
    final_grade: Decimal | None
    status: str
    finalized_at: datetime | None
    finalized_by_id: UUID | None
    created: datetime
    modified: datetime


class StageGradeAcademicUpdateSchema(Schema):
    """Schema for updating academic grade."""

    academic_grade: Decimal
    academic_grade_comment: str = ""

    @field_validator("academic_grade")
    @classmethod
    def validate_grade(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 20:
            raise ValueError("La note doit être entre 0 et 20")
        return v


class StageGradeCompanyUpdateSchema(Schema):
    """Schema for updating company grade."""

    company_grade: Decimal
    company_grade_comment: str = ""

    @field_validator("company_grade")
    @classmethod
    def validate_grade(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 20:
            raise ValueError("La note doit être entre 0 et 20")
        return v


class StageGradeFinalizeSchema(Schema):
    """Schema for finalize grade response."""

    success: bool
    message: str
    finalized_at: datetime


class StudentStageGradeSchema(Schema):
    """Schema for student viewing their own grade (only visible if finalized)."""

    id: UUID
    application_id: UUID
    offer_title: str
    company_name: str
    academic_grade: Decimal | None
    academic_grade_comment: str
    company_grade: Decimal | None
    company_grade_comment: str
    final_grade: Decimal | None
    status: str
