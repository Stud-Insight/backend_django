"""
Base schemas for the API.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema


class BaseSchema(Schema):
    """
    Base schema with common fields.

    Provides standard fields for models inheriting from BaseModel.
    """

    id: UUID
    created: datetime
    modified: datetime


class MessageSchema(Schema):
    """Schema for simple message responses."""

    message: str


class SuccessSchema(Schema):
    """Schema for success responses."""

    success: bool
    message: str | None = None


class PaginatedResponseSchema(Schema):
    """Base schema for paginated responses."""

    count: int
    next: str | None = None
    previous: str | None = None
