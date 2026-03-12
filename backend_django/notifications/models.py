from django.conf import settings
from django.db import models

from backend_django.core.models import BaseModel


class Notification(BaseModel):
    """
    Notification record for real-time SSE delivery and history.

    notification_type follows the convention: app.event
    e.g. "ter.assignment_complete", "chat.new_message", "group.invitation"
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    message = models.TextField()
    data = models.JSONField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(
                fields=["recipient", "is_read", "created"],
                name="notif_recipient_unread_idx",
            ),
            models.Index(
                fields=["recipient", "created"],
                name="notif_recipient_created_idx",
            ),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.recipient}"


# Maps notification_type prefix to a user-facing category key
NOTIFICATION_CATEGORIES = {
    "chat": "messages",
    "ter": "assignments",
    "stage": "stages",
    "group": "groups",
}


def get_category_for_type(notification_type: str) -> str | None:
    """Extract the category from a notification_type (e.g. 'ter.subject_validated' → 'assignments')."""
    prefix = notification_type.split(".")[0] if "." in notification_type else notification_type
    return NOTIFICATION_CATEGORIES.get(prefix)


class NotificationPreference(BaseModel):
    """Per-user email notification preferences, one boolean per category."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    email_messages = models.BooleanField(default=True)
    email_assignments = models.BooleanField(default=True)
    email_stages = models.BooleanField(default=True)
    email_groups = models.BooleanField(default=True)

    def is_email_enabled(self, category: str) -> bool:
        """Check if email is enabled for the given category."""
        field_name = f"email_{category}"
        return getattr(self, field_name, True)

    def __str__(self):
        return f"NotificationPreference({self.user})"
