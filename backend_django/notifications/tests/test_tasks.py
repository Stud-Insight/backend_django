"""Tests for Celery email notification tasks."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from backend_django.notifications.models import Notification
from backend_django.notifications.services import send_notification
from backend_django.notifications.tasks import (
    EMAIL_NOTIFICATION_TYPES,
    send_email_notification_async,
)
from backend_django.users.models import User


@pytest.fixture
def user_with_email(db):
    return User.objects.create_user(
        email="task-test@example.com",
        password="password123",
        first_name="Task",
        last_name="Tester",
    )


@pytest.fixture
def user_without_email(db):
    user = User.objects.create_user(
        email="temp-noemail@example.com",
        password="password123",
        first_name="NoEmail",
        last_name="User",
    )
    # Clear email after creation to simulate a user with no email
    User.objects.filter(pk=user.pk).update(email="")
    user.refresh_from_db()
    return user


@pytest.mark.django_db
class TestSendEmailNotificationAsync:
    @patch("backend_django.notifications.tasks.send_mail")
    def test_sends_email_for_valid_notification(self, mock_send_mail, user_with_email):
        notif = Notification.objects.create(
            recipient=user_with_email,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )

        send_email_notification_async(str(notif.id))

        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]
        assert "[Stud'Insight]" in call_kwargs["subject"]
        assert "Sujet validé" in call_kwargs["subject"]
        assert call_kwargs["recipient_list"] == ["task-test@example.com"]

    @patch("backend_django.notifications.tasks.send_mail")
    def test_skips_nonexistent_notification(self, mock_send_mail):
        fake_id = str(uuid4())
        send_email_notification_async(fake_id)

        mock_send_mail.assert_not_called()

    @patch("backend_django.notifications.tasks.send_mail")
    def test_skips_recipient_without_email(self, mock_send_mail, user_without_email):
        notif = Notification.objects.create(
            recipient=user_without_email,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )

        send_email_notification_async(str(notif.id))

        mock_send_mail.assert_not_called()

    @patch("backend_django.notifications.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_retries_on_send_failure(self, mock_send_mail, user_with_email):
        notif = Notification.objects.create(
            recipient=user_with_email,
            notification_type="group.invitation_received",
            title="Invitation",
            message="Vous avez reçu une invitation.",
        )

        with pytest.raises(Exception, match="SMTP error"):
            send_email_notification_async(str(notif.id))


@pytest.mark.django_db
class TestEmailQueueingIntegration:
    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_email_queued_for_email_notification_type(self, mock_delay, user_with_email):
        notif = send_notification(
            recipient=user_with_email,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )

        mock_delay.assert_called_once_with(str(notif.id))

    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_email_not_queued_for_non_email_type(self, mock_delay, user_with_email):
        send_notification(
            recipient=user_with_email,
            notification_type="chat.new_message",
            title="Nouveau message",
            message="Vous avez un nouveau message.",
        )

        mock_delay.assert_not_called()

    def test_email_notification_types_is_non_empty(self):
        assert len(EMAIL_NOTIFICATION_TYPES) > 0
        for key in EMAIL_NOTIFICATION_TYPES:
            assert "." in key, f"Type '{key}' should follow app.event convention"
