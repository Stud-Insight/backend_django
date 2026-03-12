from uuid import UUID

from django.http import HttpRequest
from django.utils import timezone
from ninja import Body
from ninja_extra import api_controller, http_get, http_patch, http_post
from ninja_extra.permissions import IsAuthenticated

from backend_django.core.api.base import BaseAPI
from backend_django.core.exceptions import ErrorSchema, NotFoundError
from backend_django.notifications.models import Notification, NotificationPreference
from backend_django.notifications.schemas import (
    NotificationPreferenceSchema,
    NotificationPreferenceUpdateSchema,
    NotificationSchema,
    UnreadCountSchema,
)


@api_controller(
    "/notifications",
    tags=["Notifications"],
    permissions=[IsAuthenticated],
)
class NotificationController(BaseAPI):

    @http_get(
        "/",
        response={200: list[NotificationSchema], 401: ErrorSchema},
    )
    def list_notifications(self, request: HttpRequest, limit: int = 50, offset: int = 0):
        """List the authenticated user's notifications, most recent first."""
        notifications = Notification.objects.filter(
            recipient=request.user,
        )[offset : offset + limit]
        return 200, list(notifications)

    @http_get(
        "/unread-count",
        response={200: UnreadCountSchema, 401: ErrorSchema},
    )
    def unread_count(self, request: HttpRequest):
        """Return count of unread notifications for the authenticated user."""
        count = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).count()
        return 200, UnreadCountSchema(count=count)

    @http_post(
        "/{notification_id}/mark-read",
        response={200: NotificationSchema, 401: ErrorSchema, 404: ErrorSchema},
    )
    def mark_read(self, request: HttpRequest, notification_id: UUID):
        """Mark a single notification as read."""
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=request.user,
            )
        except Notification.DoesNotExist:
            return NotFoundError("Notification introuvable.").to_response()

        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=["is_read", "read_at", "modified"])
        return 200, notification

    @http_post(
        "/mark-all-read",
        response={200: UnreadCountSchema, 401: ErrorSchema},
    )
    def mark_all_read(self, request: HttpRequest):
        """Mark all unread notifications as read for the authenticated user."""
        Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return 200, UnreadCountSchema(count=0)

    @http_get(
        "/preferences",
        response={200: NotificationPreferenceSchema, 401: ErrorSchema},
    )
    def get_preferences(self, request: HttpRequest):
        """Get the authenticated user's notification preferences."""
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return 200, prefs

    @http_patch(
        "/preferences",
        response={200: NotificationPreferenceSchema, 401: ErrorSchema},
    )
    def update_preferences(self, request: HttpRequest, payload: NotificationPreferenceUpdateSchema = Body(...)):
        """Update the authenticated user's notification preferences (partial update)."""
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        update_fields = []
        for field_name in ("email_messages", "email_assignments", "email_stages", "email_groups"):
            value = getattr(payload, field_name, None)
            if value is not None:
                setattr(prefs, field_name, value)
                update_fields.append(field_name)
        if update_fields:
            update_fields.append("modified")
            prefs.save(update_fields=update_fields)
        return 200, prefs
