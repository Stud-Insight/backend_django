"""Tests for Notification model."""

import pytest

from backend_django.notifications.models import Notification
from backend_django.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="notif-user@example.com",
        password="password123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="other-user@example.com",
        password="password123",
        first_name="Other",
        last_name="User",
    )


@pytest.mark.django_db
class TestNotificationModel:
    def test_create_notification(self, user):
        notif = Notification.objects.create(
            recipient=user,
            notification_type="test.event",
            title="Test title",
            message="Test message",
        )
        assert notif.id is not None
        assert notif.recipient == user
        assert notif.notification_type == "test.event"
        assert notif.title == "Test title"
        assert notif.message == "Test message"
        assert notif.is_read is False
        assert notif.read_at is None
        assert notif.data is None
        assert notif.created is not None
        assert notif.modified is not None

    def test_create_notification_with_data(self, user):
        notif = Notification.objects.create(
            recipient=user,
            notification_type="ter.assignment_complete",
            title="Assignment done",
            message="Your TER assignment is complete.",
            data={"period_id": "abc-123", "result": "success"},
        )
        assert notif.data == {"period_id": "abc-123", "result": "success"}

    def test_ordering_most_recent_first(self, user):
        n1 = Notification.objects.create(
            recipient=user,
            notification_type="test.first",
            title="First",
            message="First notification",
        )
        n2 = Notification.objects.create(
            recipient=user,
            notification_type="test.second",
            title="Second",
            message="Second notification",
        )
        notifications = list(Notification.objects.filter(recipient=user))
        assert notifications[0].id == n2.id
        assert notifications[1].id == n1.id

    def test_str_representation(self, user):
        notif = Notification.objects.create(
            recipient=user,
            notification_type="chat.new_message",
            title="New message",
            message="You have a new message.",
        )
        assert "chat.new_message" in str(notif)
        assert "New message" in str(notif)

    def test_notifications_scoped_to_user(self, user, other_user):
        Notification.objects.create(
            recipient=user,
            notification_type="test.mine",
            title="My notif",
            message="For me",
        )
        Notification.objects.create(
            recipient=other_user,
            notification_type="test.theirs",
            title="Their notif",
            message="For them",
        )
        my_notifs = Notification.objects.filter(recipient=user)
        assert my_notifs.count() == 1
        assert my_notifs.first().notification_type == "test.mine"

    def test_cascade_delete_with_user(self, user):
        Notification.objects.create(
            recipient=user,
            notification_type="test.cascade",
            title="Will be deleted",
            message="Cascade test",
        )
        assert Notification.objects.count() == 1
        user.delete()
        assert Notification.objects.count() == 0
