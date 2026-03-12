"""Tests for notification service functions."""

import pytest

from backend_django.notifications.models import Notification
from backend_django.notifications.services import send_bulk_notifications, send_notification
from backend_django.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="svc-user@example.com",
        password="password123",
        first_name="Svc",
        last_name="User",
    )


@pytest.fixture
def users(db):
    return [
        User.objects.create_user(
            email=f"bulk-{i}@example.com",
            password="password123",
            first_name=f"Bulk{i}",
            last_name="User",
        )
        for i in range(3)
    ]


@pytest.mark.django_db
class TestSendNotification:
    def test_creates_notification(self, user):
        notif = send_notification(
            recipient=user,
            notification_type="ter.assignment_complete",
            title="Assignment done",
            message="Your TER assignment is complete.",
        )
        assert isinstance(notif, Notification)
        assert notif.recipient == user
        assert notif.notification_type == "ter.assignment_complete"
        assert notif.is_read is False
        assert Notification.objects.count() == 1

    def test_creates_notification_with_data(self, user):
        notif = send_notification(
            recipient=user,
            notification_type="group.invitation",
            title="Group invite",
            message="You got invited.",
            data={"group_id": "xyz"},
        )
        assert notif.data == {"group_id": "xyz"}


@pytest.mark.django_db
class TestSendBulkNotifications:
    def test_creates_multiple_notifications(self, users):
        notifs = send_bulk_notifications(
            recipients=users,
            notification_type="ter.deadline",
            title="Deadline approaching",
            message="Submit your ranking by Friday.",
        )
        assert len(notifs) == 3
        assert Notification.objects.count() == 3
        for notif in notifs:
            assert notif.notification_type == "ter.deadline"
            assert notif.is_read is False

    def test_empty_recipients_creates_nothing(self):
        notifs = send_bulk_notifications(
            recipients=[],
            notification_type="test.empty",
            title="Nobody",
            message="No recipients.",
        )
        assert len(notifs) == 0
        assert Notification.objects.count() == 0
