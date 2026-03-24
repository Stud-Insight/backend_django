"""
TER Grading Criteria schemas for API requests and responses.

Maps to the frontend Grade interface:
  - max_score -> max
  - children -> sub_grades
"""

from __future__ import annotations

from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class GradingCriterionSchema(Schema):
    """Recursive response schema matching frontend Grade interface."""

    id: UUID
    ter_period_id: UUID | None = None
    name: str
    coefficient: float
    max: float | None = None
    sub_grades: list[GradingCriterionSchema] = []


class GradingCriterionCreateSchema(Schema):
    """Create a root criterion."""

    name: str
    coefficient: float
    max_score: float | None = 20

    @field_validator("coefficient")
    @classmethod
    def validate_coefficient(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Le coefficient doit être entre 0.0 et 1.0")
        return v


class GradingCriterionAddSubSchema(Schema):
    """Create a sub-criterion under a parent."""

    name: str
    coefficient: float
    max_score: float | None = 20

    @field_validator("coefficient")
    @classmethod
    def validate_coefficient(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Le coefficient doit être entre 0.0 et 1.0")
        return v


class GradingCriterionUpdateSchema(Schema):
    """Update a criterion (all fields optional).

    parent_id: set to a UUID to move under a parent, set to "null" to move to root.
    remove_parent: set to true to explicitly detach from parent (move to root).
    """

    name: str | None = None
    coefficient: float | None = None
    max_score: float | None = None
    order: int | None = None
    parent_id: UUID | None = None
    remove_parent: bool = False

    @field_validator("coefficient")
    @classmethod
    def validate_coefficient(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("Le coefficient doit être entre 0.0 et 1.0")
        return v


class BulkReorderItemSchema(Schema):
    """Single item in a bulk reorder request."""

    id: UUID
    order: int
    parent_id: UUID | None = None


class BulkReorderSchema(Schema):
    """Bulk reorder criteria (drag & drop)."""

    items: list[BulkReorderItemSchema]
