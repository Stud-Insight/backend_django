"""
Tests for the authentication API endpoints.
"""

import pytest
from django.test import Client

from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def user(db):
    """Create a regular user."""
    user = UserFactory(
        email="user@test.com",
        first_name="John",
        last_name="Doe",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def authenticated_client(user):
    """Return a client authenticated as user."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    # Store CSRF token for later use
    client.csrf_token = csrf_token
    return client


@pytest.fixture
def unauthenticated_client():
    """Return an unauthenticated client."""
    client = Client()
    response = client.get("/api/auth/csrf")
    client.csrf_token = response.json()["csrf_token"]
    return client


@pytest.mark.django_db
class TestGetMeEndpoint:
    """Tests for GET /api/auth/me."""

    def test_authenticated_user_can_get_profile(self, authenticated_client, user):
        """Test that authenticated user can get their profile."""
        response = authenticated_client.get("/api/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(user.id)
        assert data["email"] == user.email
        assert data["first_name"] == user.first_name
        assert data["last_name"] == user.last_name

    def test_unauthenticated_user_cannot_get_profile(self, unauthenticated_client):
        """Test that unauthenticated user cannot get profile."""
        response = unauthenticated_client.get("/api/auth/me")

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "NOT_AUTHENTICATED"


@pytest.mark.django_db
class TestUpdateMeEndpoint:
    """Tests for PUT /api/auth/me."""

    def test_authenticated_user_can_update_first_name(self, authenticated_client, user):
        """Test that authenticated user can update their first name."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": "Jane"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"  # Unchanged

        # Verify in database
        user.refresh_from_db()
        assert user.first_name == "Jane"
        assert user.last_name == "Doe"

    def test_authenticated_user_can_update_last_name(self, authenticated_client, user):
        """Test that authenticated user can update their last name."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"last_name": "Smith"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "John"  # Unchanged
        assert data["last_name"] == "Smith"

        user.refresh_from_db()
        assert user.last_name == "Smith"

    def test_authenticated_user_can_update_both_names(self, authenticated_client, user):
        """Test that authenticated user can update both names at once."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": "Jane", "last_name": "Smith"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"

        user.refresh_from_db()
        assert user.first_name == "Jane"
        assert user.last_name == "Smith"

    def test_first_name_cannot_be_empty(self, authenticated_client, user):
        """Test that first name cannot be set to empty string."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": ""},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 422  # Pydantic validation error
        user.refresh_from_db()
        assert user.first_name == "John"  # Unchanged

    def test_first_name_cannot_be_whitespace(self, authenticated_client, user):
        """Test that first name cannot be set to whitespace."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": "   "},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 422
        user.refresh_from_db()
        assert user.first_name == "John"  # Unchanged

    def test_names_are_trimmed(self, authenticated_client, user):
        """Test that names are trimmed of whitespace."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": "  Jane  ", "last_name": "  Smith  "},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Smith"

    def test_last_name_can_be_empty(self, authenticated_client, user):
        """Test that last name can be set to empty string."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"last_name": ""},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["last_name"] == ""

        user.refresh_from_db()
        assert user.last_name == ""

    def test_unauthenticated_user_cannot_update_profile(self, unauthenticated_client):
        """Test that unauthenticated user cannot update profile."""
        response = unauthenticated_client.put(
            "/api/auth/me",
            data={"first_name": "Hacker"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=unauthenticated_client.csrf_token,
        )

        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "NOT_AUTHENTICATED"

    def test_empty_update_does_not_change_anything(self, authenticated_client, user):
        """Test that empty update body doesn't change user data."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"

    def test_update_returns_full_user_schema(self, authenticated_client, user):
        """Test that update returns the full UserSchema."""
        response = authenticated_client.put(
            "/api/auth/me",
            data={"first_name": "Jane"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=authenticated_client.csrf_token,
        )

        assert response.status_code == 200
        data = response.json()

        # Check all UserSchema fields are present
        assert "id" in data
        assert "email" in data
        assert "first_name" in data
        assert "last_name" in data
        assert "groups" in data
        assert "is_staff" in data
        assert "is_superuser" in data
