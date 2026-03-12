from django.contrib.auth import get_user_model

from .models import Notification

User = get_user_model()


def _queue_email_if_needed(notification: Notification) -> None:
    """Queue an async email task if the notification type warrants it and user preferences allow."""
    from .models import NotificationPreference, get_category_for_type
    from .tasks import EMAIL_NOTIFICATION_TYPES, send_email_notification_async

    if notification.notification_type not in EMAIL_NOTIFICATION_TYPES:
        return

    # Check user preferences
    category = get_category_for_type(notification.notification_type)
    if category:
        try:
            prefs = NotificationPreference.objects.get(user=notification.recipient)
            if not prefs.is_email_enabled(category):
                return
        except NotificationPreference.DoesNotExist:
            pass  # No preferences → default all enabled

    send_email_notification_async.delay(str(notification.id))


MAX_NOTIFICATION_TYPE_LENGTH = 100


def send_notification(
    recipient: User,
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
) -> Notification:
    """Create a single notification for a user and queue email if needed."""
    if len(notification_type) > MAX_NOTIFICATION_TYPE_LENGTH:
        raise ValueError(
            f"notification_type exceeds {MAX_NOTIFICATION_TYPE_LENGTH} chars: '{notification_type[:50]}...'"
        )
    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        data=data,
    )
    _queue_email_if_needed(notification)
    return notification


def send_bulk_notifications(
    recipients: list[User],
    notification_type: str,
    title: str,
    message: str,
    data: dict | None = None,
) -> list[Notification]:
    """Create notifications for multiple users in a single query and queue emails."""
    notifications = [
        Notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data,
        )
        for recipient in recipients
    ]
    created = Notification.objects.bulk_create(notifications)
    _queue_bulk_emails_if_needed(created, notification_type)
    return created


def _queue_bulk_emails_if_needed(notifications: list[Notification], notification_type: str) -> None:
    """Queue email tasks for a batch of notifications, prefetching preferences in one query."""
    from .models import NotificationPreference, get_category_for_type
    from .tasks import EMAIL_NOTIFICATION_TYPES, send_email_notification_async

    if notification_type not in EMAIL_NOTIFICATION_TYPES:
        return

    category = get_category_for_type(notification_type)
    if not category:
        for notif in notifications:
            send_email_notification_async.delay(str(notif.id))
        return

    # Prefetch all preferences in one query
    recipient_ids = [n.recipient_id for n in notifications]
    prefs_by_user = {
        pref.user_id: pref
        for pref in NotificationPreference.objects.filter(user_id__in=recipient_ids)
    }

    for notif in notifications:
        pref = prefs_by_user.get(notif.recipient_id)
        if pref and not pref.is_email_enabled(category):
            continue
        send_email_notification_async.delay(str(notif.id))
