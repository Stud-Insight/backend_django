"""
Tests for the roles API endpoints.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.core.roles import Role
from backend_django.users.models import User
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def role_groups(db):
    """Create all role groups."""
    groups = {}
    for role in Role:
        groups[role] = Group.objects.get_or_create(name=role.value)[0]
    return groups


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    user = UserFactory(
        email="admin@test.com",
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def staff_user(db):
    """Create a staff user (non-superuser)."""
    user = UserFactory(
        email="staff@test.com",
        is_staff=True,
        is_superuser=False,
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def regular_user(db):
    """Create a regular user."""
    user = UserFactory(
        email="user@test.com",
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def authenticated_client(admin_user):
    """Return a client authenticated as admin."""
    client = Client()
    # Get CSRF token
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    # Login
    client.post(
        "/api/auth/login",
        data={"email": admin_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.fixture
def staff_client(staff_user):
    """Return a client authenticated as staff (non-superuser)."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": staff_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.mark.django_db
class TestListRolesEndpoint:
    """Tests for GET /api/users/roles."""

    def test_unauthenticated_denied(self, role_groups):
        """Test unauthenticated request is denied."""
        client = Client()
        response = client.get("/api/users/roles")
        assert response.status_code == 403

    def test_non_staff_denied(self, role_groups, regular_user):
        """Test non-staff user is denied."""
        client = Client()
        response = client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]
        client.post(
            "/api/auth/login",
            data={"email": regular_user.email, "password": "testpass123"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        response = client.get("/api/users/roles")
        assert response.status_code == 403

    def test_staff_can_list_roles(self, role_groups, authenticated_client):
        """Test staff can list all roles."""
        response = authenticated_client.get("/api/users/roles")
        assert response.status_code == 200

        data = response.json()
        assert "roles" in data
        assert len(data["roles"]) == 6

        role_names = [r["name"] for r in data["roles"]]
        assert "Étudiant" in role_names
        assert "Respo TER" in role_names
        assert "Respo Stage" in role_names
        assert "Encadrant" in role_names
        assert "Externe" in role_names
        assert "Admin" in role_names


@pytest.mark.django_db
class TestSetUserRolesEndpoint:
    """Tests for PUT /api/users/{id}/roles."""

    def test_can_set_roles(self, role_groups, authenticated_client, regular_user):
        """Test admin can set user roles."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.put(
            f"/api/users/{regular_user.id}/roles",
            data={"roles": ["Étudiant", "Encadrant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        group_names = [g["name"] for g in data["groups"]]
        assert "Étudiant" in group_names
        assert "Encadrant" in group_names

    def test_set_roles_replaces_existing(self, role_groups, authenticated_client, regular_user):
        """Test setting roles replaces existing roles."""
        # First add a role
        regular_user.groups.add(role_groups[Role.EXTERNE])

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # Now set different roles
        response = authenticated_client.put(
            f"/api/users/{regular_user.id}/roles",
            data={"roles": ["Étudiant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        group_names = [g["name"] for g in data["groups"]]
        assert "Étudiant" in group_names
        assert "Externe" not in group_names

    def test_invalid_role_rejected(self, role_groups, authenticated_client, regular_user):
        """Test invalid role names are rejected."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.put(
            f"/api/users/{regular_user.id}/roles",
            data={"roles": ["InvalidRole"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

    def test_non_superuser_cannot_assign_admin(self, role_groups, staff_client, regular_user):
        """Test non-superuser cannot assign Admin role."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.put(
            f"/api/users/{regular_user.id}/roles",
            data={"roles": ["Admin"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403

    def test_superuser_can_assign_admin(self, role_groups, authenticated_client, regular_user):
        """Test superuser can assign Admin role."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.put(
            f"/api/users/{regular_user.id}/roles",
            data={"roles": ["Admin"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        group_names = [g["name"] for g in data["groups"]]
        assert "Admin" in group_names

    def test_user_not_found(self, role_groups, authenticated_client):
        """Test 404 for non-existent user."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.put(
            f"/api/users/{fake_uuid}/roles",
            data={"roles": ["Étudiant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestAddUserRoleEndpoint:
    """Tests for POST /api/users/{id}/roles/add."""

    def test_can_add_role(self, role_groups, authenticated_client, regular_user):
        """Test admin can add roles without removing existing."""
        # First set a role
        regular_user.groups.add(role_groups[Role.ETUDIANT])

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # Add another role
        response = authenticated_client.post(
            f"/api/users/{regular_user.id}/roles/add",
            data={"roles": ["Encadrant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        group_names = [g["name"] for g in data["groups"]]
        assert "Étudiant" in group_names  # Still there
        assert "Encadrant" in group_names  # Added


@pytest.mark.django_db
class TestRemoveUserRoleEndpoint:
    """Tests for POST /api/users/{id}/roles/remove."""

    def test_can_remove_role(self, role_groups, authenticated_client, regular_user):
        """Test admin can remove roles."""
        # First set multiple roles
        regular_user.groups.add(role_groups[Role.ETUDIANT])
        regular_user.groups.add(role_groups[Role.ENCADRANT])

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # Remove one role
        response = authenticated_client.post(
            f"/api/users/{regular_user.id}/roles/remove",
            data={"roles": ["Encadrant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        group_names = [g["name"] for g in data["groups"]]
        assert "Étudiant" in group_names  # Still there
        assert "Encadrant" not in group_names  # Removed
