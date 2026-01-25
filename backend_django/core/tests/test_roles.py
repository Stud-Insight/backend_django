"""
Tests for the role system.
"""

import pytest
from django.contrib.auth.models import Group

from backend_django.core.roles import ROLE_DESCRIPTIONS
from backend_django.core.roles import Role
from backend_django.core.roles import get_user_roles
from backend_django.core.roles import user_has_any_role
from backend_django.core.roles import user_has_role
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def role_groups(db):
    """Create all role groups."""
    groups = {}
    for role in Role:
        groups[role] = Group.objects.get_or_create(name=role.value)[0]
    return groups


class TestRoleEnum:
    """Tests for the Role enum."""

    def test_role_values(self):
        """Test that all 6 roles are defined."""
        assert len(Role) == 6
        assert Role.ETUDIANT.value == "Étudiant"
        assert Role.RESPO_TER.value == "Respo TER"
        assert Role.RESPO_STAGE.value == "Respo Stage"
        assert Role.ENCADRANT.value == "Encadrant"
        assert Role.EXTERNE.value == "Externe"
        assert Role.ADMIN.value == "Admin"

    def test_role_choices(self):
        """Test Role.choices() returns correct format."""
        choices = Role.choices()
        assert len(choices) == 6
        assert ("Étudiant", "Étudiant") in choices
        assert ("Admin", "Admin") in choices

    def test_role_values_list(self):
        """Test Role.values() returns all role names."""
        values = Role.values()
        assert len(values) == 6
        assert "Étudiant" in values
        assert "Admin" in values

    def test_role_descriptions(self):
        """Test that all roles have descriptions."""
        for role in Role:
            assert role in ROLE_DESCRIPTIONS
            assert len(ROLE_DESCRIPTIONS[role]) > 0


@pytest.mark.django_db
class TestGetUserRoles:
    """Tests for get_user_roles helper."""

    def test_unauthenticated_user_returns_empty(self):
        """Test that None user returns empty list."""
        assert get_user_roles(None) == []

    def test_user_with_no_roles(self, role_groups):
        """Test user with no groups returns empty list."""
        user = UserFactory()
        assert get_user_roles(user) == []

    def test_user_with_single_role(self, role_groups):
        """Test user with one role."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])

        roles = get_user_roles(user)
        assert roles == ["Étudiant"]

    def test_user_with_multiple_roles(self, role_groups):
        """Test user with multiple roles."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])
        user.groups.add(role_groups[Role.ENCADRANT])

        roles = get_user_roles(user)
        assert len(roles) == 2
        assert "Étudiant" in roles
        assert "Encadrant" in roles


@pytest.mark.django_db
class TestUserHasRole:
    """Tests for user_has_role helper."""

    def test_none_user_returns_false(self):
        """Test that None user returns False."""
        assert user_has_role(None, Role.ETUDIANT) is False

    def test_user_without_role_returns_false(self, role_groups):
        """Test user without the role returns False."""
        user = UserFactory()
        assert user_has_role(user, Role.ETUDIANT) is False

    def test_user_with_role_returns_true(self, role_groups):
        """Test user with the role returns True."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])

        assert user_has_role(user, Role.ETUDIANT) is True

    def test_user_with_different_role_returns_false(self, role_groups):
        """Test user with different role returns False."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ENCADRANT])

        assert user_has_role(user, Role.ETUDIANT) is False

    def test_accepts_string_role_name(self, role_groups):
        """Test that string role names work."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])

        assert user_has_role(user, "Étudiant") is True
        assert user_has_role(user, "Encadrant") is False


@pytest.mark.django_db
class TestUserHasAnyRole:
    """Tests for user_has_any_role helper."""

    def test_none_user_returns_false(self):
        """Test that None user returns False."""
        assert user_has_any_role(None, [Role.ETUDIANT, Role.ENCADRANT]) is False

    def test_user_without_any_role_returns_false(self, role_groups):
        """Test user without any of the roles returns False."""
        user = UserFactory()
        assert user_has_any_role(user, [Role.ETUDIANT, Role.ENCADRANT]) is False

    def test_user_with_one_matching_role_returns_true(self, role_groups):
        """Test user with one matching role returns True."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])

        assert user_has_any_role(user, [Role.ETUDIANT, Role.ENCADRANT]) is True

    def test_user_with_all_matching_roles_returns_true(self, role_groups):
        """Test user with all matching roles returns True."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])
        user.groups.add(role_groups[Role.ENCADRANT])

        assert user_has_any_role(user, [Role.ETUDIANT, Role.ENCADRANT]) is True

    def test_user_with_non_matching_role_returns_false(self, role_groups):
        """Test user with non-matching role returns False."""
        user = UserFactory()
        user.groups.add(role_groups[Role.EXTERNE])

        assert user_has_any_role(user, [Role.ETUDIANT, Role.ENCADRANT]) is False

    def test_accepts_mixed_role_types(self, role_groups):
        """Test that mixed Role enum and string values work."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])

        assert user_has_any_role(user, [Role.ETUDIANT, "Encadrant"]) is True
