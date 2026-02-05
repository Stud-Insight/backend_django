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
    page: int
    page_size: int
    results: list


def paginate_queryset(queryset, page: int = 1, page_size: int = 20, max_page_size: int = 100):
    """
    Paginate a queryset and return (paginated_qs, total_count, page, page_size).

    Usage in endpoint:
        items, count, pg, ps = paginate_queryset(qs, page, page_size)
        return 200, PaginatedResponseSchema(
            count=count, page=pg, page_size=ps,
            results=[to_schema(i) for i in items],
        )
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    if page_size > max_page_size:
        page_size = max_page_size

    total = queryset.count()
    offset = (page - 1) * page_size
    items = queryset[offset:offset + page_size]

    return items, total, page, page_size
