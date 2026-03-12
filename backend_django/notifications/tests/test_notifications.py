"""Tests for Notification REST API endpoints."""

import pytest
from django.test import Client

from backend_django.notifications.models import Notification
from backend_django.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="rest-user@example.com",
        password="password123",
        first_name="Rest",
        last_name="User",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="rest-other@example.com",
        password="password123",
        first_name="Other",
        last_name="User",
    )


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(email="rest-user@example.com", password="password123")
    return client


@pytest.fixture
def anon_client():
    return Client()


@pytest.fixture
def notifications(user):
    return [
        Notification.objects.create(
            recipient=user,
            notification_type=f"test.event{i}",
            title=f"Notification {i}",
            message=f"Message {i}",
        )
        for i in range(5)
    ]


@pytest.mark.django_db
class TestListNotifications:
    def test_list_own_notifications(self, auth_client, notifications):
        response = auth_client.get("/api/notifications/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_list_respects_limit(self, auth_client, notifications):
        response = auth_client.get("/api/notifications/?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_respects_offset(self, auth_client, notifications):
        response = auth_client.get("/api/notifications/?offset=3&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_cannot_see_other_users_notifications(self, auth_client, other_user):
        Notification.objects.create(
            recipient=other_user,
            notification_type="test.other",
            title="Not mine",
            message="Not mine",
        )
        response = auth_client.get("/api/notifications/")
        assert response.status_code == 200
        assert len(response.json()) == 0

    def test_unauthenticated_returns_401(self, anon_client):
        response = anon_client.get("/api/notifications/")
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestUnreadCount:
    def test_returns_unread_count(self, auth_client, notifications):
        response = auth_client.get("/api/notifications/unread-count")
        assert response.status_code == 200
        assert response.json()["count"] == 5

    def test_read_notifications_not_counted(self, auth_client, user):
        Notification.objects.create(
            recipient=user,
            notification_type="test.read",
            title="Read",
            message="Already read",
            is_read=True,
        )
        Notification.objects.create(
            recipient=user,
            notification_type="test.unread",
            title="Unread",
            message="Not read",
        )
        response = auth_client.get("/api/notifications/unread-count")
        assert response.status_code == 200
        assert response.json()["count"] == 1


@pytest.mark.django_db
class TestMarkRead:
    def test_mark_single_notification_read(self, auth_client, user):
        notif = Notification.objects.create(
            recipient=user,
            notification_type="test.markread",
            title="Mark me",
            message="Read me",
        )
        response = auth_client.post(f"/api/notifications/{notif.id}/mark-read")
        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True
        assert data["read_at"] is not None

        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

    def test_mark_read_404_for_nonexistent(self, auth_client):
        response = auth_client.post(
            "/api/notifications/00000000-0000-0000-0000-000000000000/mark-read"
        )
        assert response.status_code == 404

    def test_cannot_mark_other_users_notification(self, auth_client, other_user):
        notif = Notification.objects.create(
            recipient=other_user,
            notification_type="test.other",
            title="Not mine",
            message="Not mine",
        )
        response = auth_client.post(f"/api/notifications/{notif.id}/mark-read")
        assert response.status_code == 404


@pytest.mark.django_db
class TestMarkAllRead:
    def test_mark_all_read(self, auth_client, notifications):
        response = auth_client.post("/api/notifications/mark-all-read")
        assert response.status_code == 200
        assert response.json()["count"] == 0

        unread = Notification.objects.filter(
            recipient=notifications[0].recipient, is_read=False
        ).count()
        assert unread == 0

    def test_mark_all_read_does_not_affect_other_users(
        self, auth_client, notifications, other_user
    ):
        Notification.objects.create(
            recipient=other_user,
            notification_type="test.other",
            title="Not mine",
            message="Not mine",
        )
        auth_client.post("/api/notifications/mark-all-read")

        other_unread = Notification.objects.filter(
            recipient=other_user, is_read=False
        ).count()
        assert other_unread == 1
