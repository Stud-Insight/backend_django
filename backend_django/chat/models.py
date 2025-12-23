"""
Chat models for conversations and messages.
"""

from django.conf import settings
from django.db import models

from backend_django.core.models import BaseModel


class Conversation(BaseModel):
    """
    A conversation between two or more users.
    """

    name = models.CharField(max_length=255, blank=True, default="")
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="conversations",
    )
    is_group = models.BooleanField(default=False)

    class Meta:
        ordering = ["-modified"]

    def __str__(self):
        if self.name:
            return self.name
        # For 1-on-1 conversations, show participant names
        participants = self.participants.all()[:3]
        names = [p.get_full_name() or p.email for p in participants]
        return ", ".join(names)

    def get_other_participant(self, user):
        """Get the other participant in a 1-on-1 conversation."""
        if self.is_group:
            return None
        return self.participants.exclude(id=user.id).first()

    def get_last_message(self):
        """Get the most recent message in this conversation."""
        return self.messages.order_by("-created").first()

    def get_unread_count(self, user):
        """Get count of unread messages for a user."""
        return self.messages.exclude(sender=user).filter(read_by__isnull=True).count()


class Message(BaseModel):
    """
    A message in a conversation.
    """

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    content = models.TextField()
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="read_messages",
        blank=True,
    )

    class Meta:
        ordering = ["created"]

    def __str__(self):
        return f"{self.sender}: {self.content[:50]}"

    def mark_as_read(self, user):
        """Mark this message as read by a user."""
        if user != self.sender:
            self.read_by.add(user)
