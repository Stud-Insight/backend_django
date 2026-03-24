"""
TER Criterion Score schemas for grade assignment.
"""

from __future__ import annotations

from uuid import UUID

from ninja import Schema


class CriterionScoreInputSchema(Schema):
    """Single score input for a criterion."""

    criterion_id: UUID
    score: float
    comment: str = ""


class BulkScoreSchema(Schema):
    """Bulk save scores for a group."""

    scores: list[CriterionScoreInputSchema]


class CriterionScoreSchema(Schema):
    """Response: a criterion with its score (if any)."""

    id: UUID
    name: str
    coefficient: float
    max: float | None = None
    score: float | None = None
    comment: str = ""
    sub_grades: list[CriterionScoreSchema] = []


class GroupGradeSummarySchema(Schema):
    """Computed total grade for a group."""

    group_id: UUID
    group_name: str
    total_grade: float | None = None
    max_grade: float = 20
    criteria: list[CriterionScoreSchema] = []
