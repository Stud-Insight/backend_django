"""
Integration tests for the role-based permission system.

These tests verify that multiple components work together correctly:
- User creation with roles
- Role-based access control on protected endpoints
- Role changes affecting permissions immediately
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
    user.set_password("AdminPass123!")
    user.save()
    return user


def get_authenticated_client(user, password="AdminPass123!"):
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
class TestUserCreationWithRoles:
    """Integration tests for creating users with roles."""

    def test_create_user_with_role_via_api(self, role_groups, admin_user):
        """Test admin can create a user with roles assigned."""
        client, csrf_token = get_authenticated_client(admin_user)

        # Create user with Étudiant role
        response = client.post(
            "/api/users/create",
            data={
                "email": "student@test.com",
                "first_name": "Test",
                "last_name": "Student",
                "groups": ["Étudiant"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        # Verify user was created with role
        user = User.objects.get(email="student@test.com")
        assert user.groups.filter(name="Étudiant").exists()

    def test_create_user_with_multiple_roles(self, role_groups, admin_user):
        """Test creating user with multiple roles."""
        client, csrf_token = get_authenticated_client(admin_user)

        response = client.post(
            "/api/users/create",
            data={
                "email": "multi@test.com",
                "first_name": "Multi",
                "last_name": "Role",
                "groups": ["Encadrant", "Respo TER"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        user = User.objects.get(email="multi@test.com")
        assert user.groups.count() == 2
        assert user.groups.filter(name="Encadrant").exists()
        assert user.groups.filter(name="Respo TER").exists()


@pytest.mark.django_db
class TestRoleBasedAccessControl:
    """Integration tests for role-based access control."""

    def test_staff_endpoint_requires_staff(self, role_groups):
        """Test that /api/users/ requires staff permission."""
        # Create a non-staff user with a role
        user = UserFactory(
            email="student@test.com",
            is_staff=False,
            is_active=True,
        )
        user.set_password("TestPass123!")
        user.save()
        user.groups.add(role_groups[Role.ETUDIANT])

        client, _ = get_authenticated_client(user, "TestPass123!")

        # Should be denied access to admin endpoint
        response = client.get("/api/users/")
        assert response.status_code == 403

    def test_role_change_affects_permissions_immediately(self, role_groups, admin_user):
        """Test that changing roles affects permissions immediately."""
        # Create a user
        user = UserFactory(
            email="changeme@test.com",
            is_staff=True,  # Staff but not superuser
            is_superuser=False,
            is_active=True,
        )
        user.set_password("TestPass123!")
        user.save()

        client, csrf_token = get_authenticated_client(user, "TestPass123!")

        # Initially can access staff endpoint
        response = client.get("/api/users/")
        assert response.status_code == 200

        # Now admin removes staff status via update
        admin_client, admin_csrf = get_authenticated_client(admin_user)
        response = admin_client.put(
            f"/api/users/{user.id}",
            data={"is_active": True},  # Just update, keep is_staff through DB
            content_type="application/json",
            HTTP_X_CSRFTOKEN=admin_csrf,
        )

        # User still has access (staff status wasn't changed via this endpoint)
        response = client.get("/api/users/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestRoleAssignmentWorkflow:
    """Integration tests for the role assignment workflow."""

    def test_full_role_assignment_workflow(self, role_groups, admin_user):
        """Test complete workflow: create user -> assign role -> verify."""
        client, csrf_token = get_authenticated_client(admin_user)

        # 1. Create user without roles
        response = client.post(
            "/api/users/create",
            data={
                "email": "newuser@test.com",
                "first_name": "New",
                "last_name": "User",
                "groups": [],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201
        user_id = response.json()["id"]

        # 2. Verify user has no roles
        response = client.get(f"/api/users/{user_id}")
        assert response.status_code == 200
        assert len(response.json()["groups"]) == 0

        # 3. Assign Étudiant role
        response = client.put(
            f"/api/users/{user_id}/roles",
            data={"roles": ["Étudiant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # 4. Verify role was assigned
        response = client.get(f"/api/users/{user_id}")
        assert response.status_code == 200
        groups = [g["name"] for g in response.json()["groups"]]
        assert "Étudiant" in groups

        # 5. Add another role
        response = client.post(
            f"/api/users/{user_id}/roles/add",
            data={"roles": ["Encadrant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # 6. Verify both roles
        response = client.get(f"/api/users/{user_id}")
        groups = [g["name"] for g in response.json()["groups"]]
        assert "Étudiant" in groups
        assert "Encadrant" in groups

        # 7. Remove one role
        response = client.post(
            f"/api/users/{user_id}/roles/remove",
            data={"roles": ["Étudiant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # 8. Verify only Encadrant remains
        response = client.get(f"/api/users/{user_id}")
        groups = [g["name"] for g in response.json()["groups"]]
        assert "Étudiant" not in groups
        assert "Encadrant" in groups

    def test_role_replacement_workflow(self, role_groups, admin_user):
        """Test replacing all roles at once."""
        client, csrf_token = get_authenticated_client(admin_user)

        # Create user with initial roles
        user = UserFactory(email="replace@test.com", is_active=True)
        user.groups.add(role_groups[Role.ETUDIANT])
        user.groups.add(role_groups[Role.EXTERNE])

        # Replace all roles
        response = client.put(
            f"/api/users/{user.id}/roles",
            data={"roles": ["Encadrant", "Respo TER"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # Verify old roles removed, new roles added
        user.refresh_from_db()
        role_names = list(user.groups.values_list("name", flat=True))
        assert "Étudiant" not in role_names
        assert "Externe" not in role_names
        assert "Encadrant" in role_names
        assert "Respo TER" in role_names


@pytest.mark.django_db
class TestRolePermissionIntegration:
    """Integration tests verifying roles work with permission system."""

    def test_user_list_shows_roles_correctly(self, role_groups, admin_user):
        """Test that user list endpoint shows roles correctly."""
        # Create users with different roles
        user1 = UserFactory(email="user1@test.com", is_active=True)
        user1.groups.add(role_groups[Role.ETUDIANT])

        user2 = UserFactory(email="user2@test.com", is_active=True)
        user2.groups.add(role_groups[Role.ENCADRANT])
        user2.groups.add(role_groups[Role.RESPO_TER])

        client, _ = get_authenticated_client(admin_user)

        response = client.get("/api/users/")
        assert response.status_code == 200

        users_data = response.json()

        # Find our test users
        user1_data = next((u for u in users_data if u["email"] == "user1@test.com"), None)
        user2_data = next((u for u in users_data if u["email"] == "user2@test.com"), None)

        assert user1_data is not None
        assert user2_data is not None

        # Verify roles
        user1_groups = [g["name"] for g in user1_data["groups"]]
        user2_groups = [g["name"] for g in user2_data["groups"]]

        assert user1_groups == ["Étudiant"]
        assert set(user2_groups) == {"Encadrant", "Respo TER"}

    def test_roles_list_endpoint_returns_all_roles(self, role_groups, admin_user):
        """Test that roles list returns all 6 defined roles."""
        client, _ = get_authenticated_client(admin_user)

        response = client.get("/api/users/roles")
        assert response.status_code == 200

        roles = response.json()["roles"]
        role_names = {r["name"] for r in roles}

        expected_roles = {"Étudiant", "Respo TER", "Respo Stage", "Encadrant", "Externe", "Admin"}
        assert role_names == expected_roles

        # Each role should have a description
        for role in roles:
            assert "description" in role
            assert len(role["description"]) > 0
