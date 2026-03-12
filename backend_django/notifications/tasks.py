"""Celery tasks for async email notifications."""

import logging
from uuid import UUID

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

# Notification types that trigger email notifications
EMAIL_NOTIFICATION_TYPES = {
    "ter.subject_assigned": "Sujet TER assigné",
    "ter.subject_validated": "Sujet TER validé",
    "ter.subject_rejected": "Sujet TER refusé",
    "stage.application_accepted": "Candidature de stage acceptée",
    "stage.application_rejected": "Candidature de stage refusée",
    "stage.application_confirmed": "Stage confirmé",
    "stage.supervisor_assigned": "Encadrement de stage assigné",
    "group.invitation_received": "Invitation à un groupe",
    "group.member_removed": "Retrait du groupe",
}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    ignore_result=True,
)
def send_email_notification_async(self, notification_id: str):
    """
    Send an email for a notification record.

    Retries up to 3 times with 60s delay on failure.
    """
    from backend_django.notifications.models import Notification

    try:
        notification = Notification.objects.select_related("recipient").get(
            id=UUID(notification_id)
        )
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found, skipping email.", notification_id)
        return

    recipient = notification.recipient
    if not recipient.email:
        logger.warning("Recipient %s has no email, skipping.", recipient.id)
        return

    subject = f"[Stud'Insight] {notification.title}"
    body = f"{notification.message}\n\n---\nCet email a été envoyé automatiquement par Stud'Insight."

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.email],
            fail_silently=False,
        )
        logger.info(
            "Email sent for notification %s to %s",
            notification.id,
            recipient.email,
        )
    except Exception as exc:
        logger.error(
            "Failed to send email for notification %s: %s",
            notification.id,
            exc,
        )
        raise self.retry(exc=exc)
