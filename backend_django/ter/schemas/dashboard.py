"""
TER Dashboard schemas for API responses.

Covers:
- 12-3: Encadrant dashboard (assigned groups + progress)
- 12-4: Student dashboard (current phase + deadlines)
- 12-5: Admin system-wide statistics
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

from backend_django.users.schemas import UserMinimalSchema


# ==================== 12-3: Encadrant Dashboard ====================


class EncadrantGroupDeliverableSchema(Schema):
    """Summary of deliverables for a group."""

    total: int
    submitted: int


class EncadrantGroupSchema(Schema):
    """A group supervised by the encadrant."""

    id: UUID
    name: str
    members: list[UserMinimalSchema]
    subject_title: str
    subject_id: UUID
    deliverables: EncadrantGroupDeliverableSchema
    grade_status: str | None  # "draft", "submitted", "finalized", or None
    group_grade: Decimal | None


class EncadrantDashboardSchema(Schema):
    """Dashboard data for an encadrant."""

    ter_period_id: UUID
    ter_period_name: str
    groups: list[EncadrantGroupSchema]
    total_groups: int
    graded_groups: int
    finalized_groups: int


# ==================== 12-4: Student Dashboard ====================


class StudentPhaseSchema(Schema):
    """Current phase information for a student."""

    current_phase: str  # "formation", "selection", "assignment", "execution", "finished", "unknown"
    current_phase_label: str  # Human-readable French label
    next_deadline: date | None
    next_deadline_label: str | None
    days_remaining: int | None


class StudentDashboardSchema(Schema):
    """Enriched student dashboard response."""

    ter_period_id: UUID | None
    ter_period_name: str | None
    status: str  # Same as MyTERSchema.status
    phase: StudentPhaseSchema | None
    group_name: str | None
    group_id: UUID | None
    subject_title: str | None
    subject_id: UUID | None


# ==================== 12-5: Admin System-Wide Stats ====================


class AdminSystemStatsSchema(Schema):
    """System-wide statistics for admin dashboard."""

    total_users: int
    active_users: int
    total_students: int
    total_encadrants: int
    total_externes: int
    active_ter_periods: int
    draft_ter_periods: int
    archived_ter_periods: int
    active_stage_periods: int
