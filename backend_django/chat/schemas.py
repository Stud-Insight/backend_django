"""
Chat API schemas.
"""

from datetime import datetime
from uuid import UUID

from ninja import Schema


class ParticipantSchema(Schema):
    """Schema for conversation participant."""

    id: UUID
    email: str
    first_name: str
    last_name: str


class MessageSchema(Schema):
    """Schema for a chat message."""

    id: UUID
    sender: ParticipantSchema
    content: str
    created: datetime
    is_read: bool = False


class ConversationSchema(Schema):
    """Schema for a conversation."""

    id: UUID
    name: str
    is_group: bool
    participants: list[ParticipantSchema]
    last_message: MessageSchema | None = None
    unread_count: int = 0
    created: datetime
    modified: datetime


class ConversationDetailSchema(Schema):
    """Schema for conversation with messages."""

    id: UUID
    name: str
    is_group: bool
    participants: list[ParticipantSchema]
    messages: list[MessageSchema]
    created: datetime
    modified: datetime


class CreateConversationSchema(Schema):
    """Schema for creating a new conversation."""

    participant_ids: list[UUID]
    name: str = ""
    is_group: bool = False


class SendMessageSchema(Schema):
    """Schema for sending a message."""

    content: str


class MessageSentSchema(Schema):
    """Schema for sent message response."""

    success: bool
    message: MessageSchema
