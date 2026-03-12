from datetime import datetime
from uuid import UUID

from ninja import Schema


class NotificationSchema(Schema):
    id: UUID
    notification_type: str
    title: str
    message: str
    data: dict | None = None
    is_read: bool
    read_at: datetime | None = None
    created: datetime


class UnreadCountSchema(Schema):
    count: int


class NotificationPreferenceSchema(Schema):
    email_messages: bool
    email_assignments: bool
    email_stages: bool
    email_groups: bool


class NotificationPreferenceUpdateSchema(Schema):
    email_messages: bool | None = None
    email_assignments: bool | None = None
    email_stages: bool | None = None
    email_groups: bool | None = None
