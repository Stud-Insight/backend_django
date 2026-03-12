"""Tests for SSE notification stream endpoint."""

import pytest
from django.test import Client

from backend_django.notifications.models import Notification
from backend_django.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sse-user@example.com",
        password="password123",
        first_name="SSE",
        last_name="User",
    )


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(email="sse-user@example.com", password="password123")
    return client


@pytest.fixture
def anon_client():
    return Client()


@pytest.mark.django_db
class TestSSEStream:
    def test_unauthenticated_returns_error(self, anon_client):
        response = anon_client.get("/api/notifications/stream")
        assert response.status_code in (401, 403)

    def test_authenticated_returns_event_stream(self, auth_client):
        response = auth_client.get("/api/notifications/stream")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/event-stream"
        assert response["Cache-Control"] == "no-cache"
        assert response["X-Accel-Buffering"] == "no"
        # Close the streaming response
        response.close()

    def test_stream_delivers_existing_notifications(self, auth_client, user):
        Notification.objects.create(
            recipient=user,
            notification_type="test.sse",
            title="SSE test",
            message="Should appear in stream",
        )
        response = auth_client.get("/api/notifications/stream")
        assert response.status_code == 200

        # Read first chunk from the streaming response
        content = b""
        for chunk in response.streaming_content:
            content += chunk
            # Stop after first data event
            if b"data:" in content:
                break

        response.close()
        decoded = content.decode("utf-8")
        assert "data:" in decoded
        assert "test.sse" in decoded
        assert "SSE test" in decoded
