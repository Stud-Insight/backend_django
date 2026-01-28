"""
API tests for RGPD endpoints.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.chat.models import Conversation
from backend_django.chat.models import Message
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    user = UserFactory(
        email="admin@test.com",
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    user.set_password("AdminPass123!")
    user.save()
    return user


@pytest.fixture
def regular_user(db):
    """Create a regular user with some data."""
    user = UserFactory(
        email="user@test.com",
        first_name="Regular",
        last_name="User",
        is_active=True,
    )
    user.set_password("UserPass123!")
    user.save()

    # Add to a group
    group, _ = Group.objects.get_or_create(name="Étudiant")
    user.groups.add(group)

    return user


@pytest.fixture
def user_with_messages(regular_user):
    """Create a user with conversations and messages."""
    other_user = UserFactory()
    conversation = Conversation.objects.create(name="Test")
    conversation.participants.add(regular_user, other_user)

    Message.objects.create(
        conversation=conversation,
        sender=regular_user,
        content="Test message from user",
    )

    return regular_user


def get_authenticated_client(user, password):
    """Helper to create an authenticated client."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": user.email, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client, csrf_token


@pytest.mark.django_db
class TestRGPDExportOwnData:
    """Tests for GET /api/rgpd/export - User exports own data."""

    def test_unauthenticated_denied(self):
        """Test unauthenticated request is denied."""
        client = Client()
        response = client.get("/api/rgpd/export")
        assert response.status_code == 403

    def test_user_can_export_own_data(self, regular_user):
        """Test user can export their own data."""
        client, _ = get_authenticated_client(regular_user, "UserPass123!")

        response = client.get("/api/rgpd/export")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert data["data"]["profile"]["email"] == "user@test.com"

    def test_export_includes_profile(self, regular_user):
        """Test export includes profile information."""
        client, _ = get_authenticated_client(regular_user, "UserPass123!")

        response = client.get("/api/rgpd/export")
        data = response.json()["data"]

        assert "profile" in data
        assert data["profile"]["first_name"] == "Regular"
        assert data["profile"]["last_name"] == "User"

    def test_export_includes_roles(self, regular_user):
        """Test export includes role membership."""
        client, _ = get_authenticated_client(regular_user, "UserPass123!")

        response = client.get("/api/rgpd/export")
        data = response.json()["data"]

        assert "roles" in data
        assert len(data["roles"]) == 1
        assert data["roles"][0]["name"] == "Étudiant"

    def test_export_includes_conversations(self, user_with_messages):
        """Test export includes conversations and messages."""
        client, _ = get_authenticated_client(user_with_messages, "UserPass123!")

        response = client.get("/api/rgpd/export")
        data = response.json()["data"]

        assert "conversations" in data
        assert len(data["conversations"]) == 1
        assert len(data["conversations"][0]["messages"]) == 1


@pytest.mark.django_db
class TestRGPDAdminExportUserData:
    """Tests for GET /api/users/{id}/rgpd/export - Admin exports user data."""

    def test_unauthenticated_denied(self, regular_user):
        """Test unauthenticated request is denied."""
        client = Client()
        response = client.get(f"/api/users/{regular_user.id}/rgpd/export")
        assert response.status_code == 403

    def test_non_staff_denied(self, regular_user):
        """Test non-staff user is denied."""
        other_user = UserFactory(is_staff=False, is_active=True)
        other_user.set_password("Pass123!")
        other_user.save()

        client, _ = get_authenticated_client(other_user, "Pass123!")
        response = client.get(f"/api/users/{regular_user.id}/rgpd/export")

        assert response.status_code == 403

    def test_admin_can_export_user_data(self, admin_user, regular_user):
        """Test admin can export any user's data."""
        client, _ = get_authenticated_client(admin_user, "AdminPass123!")

        response = client.get(f"/api/users/{regular_user.id}/rgpd/export")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["profile"]["email"] == "user@test.com"

    def test_user_not_found(self, admin_user):
        """Test 404 for non-existent user."""
        client, _ = get_authenticated_client(admin_user, "AdminPass123!")

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/users/{fake_uuid}/rgpd/export")

        assert response.status_code == 404


@pytest.mark.django_db
class TestRGPDAdminDeleteUser:
    """Tests for POST /api/users/{id}/rgpd/delete - Admin deletes user."""

    def test_unauthenticated_denied(self, regular_user):
        """Test unauthenticated request is denied."""
        client = Client()
        response = client.post(
            f"/api/users/{regular_user.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_non_staff_denied(self, regular_user):
        """Test non-staff user is denied."""
        other_user = UserFactory(is_staff=False, is_active=True)
        other_user.set_password("Pass123!")
        other_user.save()

        client, csrf = get_authenticated_client(other_user, "Pass123!")
        response = client.post(
            f"/api/users/{regular_user.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_requires_confirmation(self, admin_user, regular_user):
        """Test deletion requires confirm=true."""
        client, csrf = get_authenticated_client(admin_user, "AdminPass123!")

        response = client.post(
            f"/api/users/{regular_user.id}/rgpd/delete",
            data={"confirm": False},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "confirm" in response.json()["message"].lower()

    def test_admin_can_delete_user(self, admin_user, regular_user):
        """Test admin can delete a user with confirmation."""
        original_email = regular_user.email
        client, csrf = get_authenticated_client(admin_user, "AdminPass123!")

        response = client.post(
            f"/api/users/{regular_user.id}/rgpd/delete",
            data={"confirm": True, "reason": "User requested deletion"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "@deleted.studinsight.local" in data["anonymized_email"]

        # Verify user is anonymized
        regular_user.refresh_from_db()
        assert regular_user.email != original_email
        assert regular_user.is_active is False

    def test_cannot_delete_self(self, admin_user):
        """Test admin cannot delete their own account."""
        client, csrf = get_authenticated_client(admin_user, "AdminPass123!")

        response = client.post(
            f"/api/users/{admin_user.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_non_superuser_cannot_delete_superuser(self, admin_user):
        """Test staff (non-superuser) cannot delete superuser."""
        staff_user = UserFactory(is_staff=True, is_superuser=False, is_active=True)
        staff_user.set_password("StaffPass123!")
        staff_user.save()

        client, csrf = get_authenticated_client(staff_user, "StaffPass123!")

        response = client.post(
            f"/api/users/{admin_user.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_user_not_found(self, admin_user):
        """Test 404 for non-existent user."""
        client, csrf = get_authenticated_client(admin_user, "AdminPass123!")

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = client.post(
            f"/api/users/{fake_uuid}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestRGPDRequestDeletion:
    """Tests for POST /api/rgpd/request-deletion - User requests own deletion."""

    def test_user_can_request_own_deletion(self, regular_user):
        """Test user can request deletion of their own account."""
        client, csrf = get_authenticated_client(regular_user, "UserPass123!")

        response = client.post(
            "/api/rgpd/request-deletion",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "30 jours" in data["message"]

    def test_unauthenticated_denied(self):
        """Test unauthenticated users cannot request deletion."""
        client = Client()
        response = client.post("/api/rgpd/request-deletion")
        assert response.status_code == 403
