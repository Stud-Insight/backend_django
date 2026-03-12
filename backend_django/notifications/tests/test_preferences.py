"""Tests for notification preferences (Story 7-5)."""

from unittest.mock import patch

import pytest
from django.test import Client

from backend_django.notifications.models import (
    NOTIFICATION_CATEGORIES,
    NotificationPreference,
    get_category_for_type,
)
from backend_django.notifications.services import send_notification
from backend_django.users.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="pref-user@example.com",
        password="password123",
        first_name="Pref",
        last_name="User",
    )


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(email=user.email, password="password123")
    return client


# =============================================================================
# Model Tests
# =============================================================================


@pytest.mark.django_db
class TestNotificationPreferenceModel:
    def test_default_all_enabled(self, user):
        prefs = NotificationPreference.objects.create(user=user)
        assert prefs.email_messages is True
        assert prefs.email_assignments is True
        assert prefs.email_stages is True
        assert prefs.email_groups is True

    def test_is_email_enabled(self, user):
        prefs = NotificationPreference.objects.create(user=user, email_messages=False)
        assert prefs.is_email_enabled("messages") is False
        assert prefs.is_email_enabled("assignments") is True

    def test_is_email_enabled_unknown_category(self, user):
        prefs = NotificationPreference.objects.create(user=user)
        assert prefs.is_email_enabled("unknown_cat") is True

    def test_str(self, user):
        prefs = NotificationPreference.objects.create(user=user)
        assert "NotificationPreference" in str(prefs)


@pytest.mark.django_db
class TestGetCategoryForType:
    def test_chat_maps_to_messages(self):
        assert get_category_for_type("chat.new_message") == "messages"

    def test_ter_maps_to_assignments(self):
        assert get_category_for_type("ter.subject_validated") == "assignments"

    def test_stage_maps_to_stages(self):
        assert get_category_for_type("stage.application_accepted") == "stages"

    def test_group_maps_to_groups(self):
        assert get_category_for_type("group.invitation_received") == "groups"

    def test_unknown_prefix_returns_none(self):
        assert get_category_for_type("unknown.something") is None


# =============================================================================
# API Tests
# =============================================================================


@pytest.mark.django_db
class TestPreferencesAPI:
    def test_get_preferences_creates_default(self, auth_client, user):
        response = auth_client.get("/api/notifications/preferences")
        assert response.status_code == 200
        data = response.json()
        assert data["email_messages"] is True
        assert data["email_assignments"] is True
        assert data["email_stages"] is True
        assert data["email_groups"] is True

    def test_update_preferences_partial(self, auth_client, user):
        response = auth_client.patch(
            "/api/notifications/preferences",
            data={"email_messages": False},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email_messages"] is False
        assert data["email_assignments"] is True

        prefs = NotificationPreference.objects.get(user=user)
        assert prefs.email_messages is False

    def test_update_preferences_multiple(self, auth_client, user):
        response = auth_client.patch(
            "/api/notifications/preferences",
            data={"email_messages": False, "email_groups": False},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email_messages"] is False
        assert data["email_groups"] is False
        assert data["email_assignments"] is True

    def test_unauthenticated_rejected(self):
        client = Client()
        response = client.get("/api/notifications/preferences")
        assert response.status_code in (401, 403)


# =============================================================================
# Email Queueing Integration
# =============================================================================


@pytest.mark.django_db
class TestPreferenceEmailIntegration:
    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_email_sent_when_enabled(self, mock_delay, user):
        """Default preferences: email should be queued."""
        notif = send_notification(
            recipient=user,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )
        mock_delay.assert_called_once_with(str(notif.id))

    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_email_blocked_when_disabled(self, mock_delay, user):
        """When user disables email for assignments, TER emails should not be queued."""
        NotificationPreference.objects.create(user=user, email_assignments=False)
        send_notification(
            recipient=user,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )
        mock_delay.assert_not_called()

    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_other_categories_still_sent(self, mock_delay, user):
        """Disabling one category should not affect others."""
        NotificationPreference.objects.create(user=user, email_assignments=False)
        notif = send_notification(
            recipient=user,
            notification_type="group.invitation_received",
            title="Invitation",
            message="Vous avez reçu une invitation.",
        )
        mock_delay.assert_called_once_with(str(notif.id))

    @patch("backend_django.notifications.tasks.send_email_notification_async.delay")
    def test_in_app_notification_still_created_when_email_disabled(self, mock_delay, user):
        """Even with email disabled, the in-app notification must still be created."""
        NotificationPreference.objects.create(user=user, email_assignments=False)
        from backend_django.notifications.models import Notification

        notif = send_notification(
            recipient=user,
            notification_type="ter.subject_validated",
            title="Sujet validé",
            message="Votre sujet a été validé.",
        )
        assert Notification.objects.filter(id=notif.id).exists()
        mock_delay.assert_not_called()
