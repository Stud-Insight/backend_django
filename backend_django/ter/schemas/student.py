"""
TER Student schemas for API requests and responses.
"""

from uuid import UUID

from ninja import Schema

from backend_django.ter.schemas.periods import TERPeriodDetailSchema
from backend_django.ter.schemas.subjects import TERSubjectListSchema


class MyTERSchema(Schema):
    """
    Schema for student's TER context response.

    Returns the complete TER context for a connected student:
    - Their active TER period (if enrolled)
    - Their group (if they have one)
    - The assigned subject (if their group has one)
    - A status summarizing their current state
    """

    ter_period: TERPeriodDetailSchema | None
    group: "backend_django.groups.schemas.groups.GroupDetailSchema"
    subject: TERSubjectListSchema | None
    status: str  # "no_period", "no_group", "group_forming", "group_formed", "subject_assigned"
