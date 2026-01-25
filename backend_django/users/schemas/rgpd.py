"""
RGPD (GDPR) related schemas for data export and account deletion.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Schema


class RGPDExportResponseSchema(Schema):
    """Response schema for RGPD data export."""

    success: bool
    message: str
    export_date: datetime
    data: dict[str, Any]


class RGPDDeleteRequestSchema(Schema):
    """Request schema for RGPD account deletion."""

    reason: str = "RGPD deletion"  # Reason for deletion (for audit)
    confirm: bool = False  # Must be True to proceed


class RGPDDeleteResponseSchema(Schema):
    """Response schema for RGPD account deletion."""

    success: bool
    message: str
    user_id: UUID
    anonymized_email: str
    actions: list[str]


class RGPDExportRequestResponseSchema(Schema):
    """Response for requesting an export (async)."""

    success: bool
    message: str
    request_id: str | None = None
