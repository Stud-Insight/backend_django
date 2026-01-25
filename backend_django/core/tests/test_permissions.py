"""
Tests for the permission classes.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import Group
from django.test import RequestFactory

from backend_django.core.api.permissions import IsAcademic
from backend_django.core.api.permissions import IsAdmin
from backend_django.core.api.permissions import IsAuthenticated
from backend_django.core.api.permissions import IsEncadrant
from backend_django.core.api.permissions import IsEtudiant
from backend_django.core.api.permissions import IsExterne
from backend_django.core.api.permissions import IsRespo
from backend_django.core.api.permissions import IsRespoStage
from backend_django.core.api.permissions import IsRespoTER
from backend_django.core.api.permissions import IsStaff
from backend_django.core.api.permissions import IsStaffOrRespo
from backend_django.core.api.permissions import IsSuperuser
from backend_django.core.roles import Role
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def request_factory():
    """Return a Django RequestFactory."""
    return RequestFactory()


@pytest.fixture
def role_groups(db):
    """Create all role groups."""
    groups = {}
    for role in Role:
        groups[role] = Group.objects.get_or_create(name=role.value)[0]
    return groups


def make_request(request_factory, user=None):
    """Create a request with the given user."""
    request = request_factory.get("/")
    request.user = user if user else AnonymousUser()
    return request


@pytest.mark.django_db
class TestIsAuthenticated:
    """Tests for IsAuthenticated permission."""

    def test_anonymous_user_denied(self, request_factory):
        """Test anonymous user is denied."""
        request = make_request(request_factory)
        perm = IsAuthenticated()
        assert perm.has_permission(request, None) is False

    def test_authenticated_user_allowed(self, request_factory):
        """Test authenticated user is allowed."""
        user = UserFactory()
        request = make_request(request_factory, user)
        perm = IsAuthenticated()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsStaff:
    """Tests for IsStaff permission."""

    def test_anonymous_user_denied(self, request_factory):
        """Test anonymous user is denied."""
        request = make_request(request_factory)
        perm = IsStaff()
        assert perm.has_permission(request, None) is False

    def test_non_staff_user_denied(self, request_factory):
        """Test non-staff user is denied."""
        user = UserFactory(is_staff=False)
        request = make_request(request_factory, user)
        perm = IsStaff()
        assert perm.has_permission(request, None) is False

    def test_staff_user_allowed(self, request_factory):
        """Test staff user is allowed."""
        user = UserFactory(is_staff=True)
        request = make_request(request_factory, user)
        perm = IsStaff()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsSuperuser:
    """Tests for IsSuperuser permission."""

    def test_anonymous_user_denied(self, request_factory):
        """Test anonymous user is denied."""
        request = make_request(request_factory)
        perm = IsSuperuser()
        assert perm.has_permission(request, None) is False

    def test_non_superuser_denied(self, request_factory):
        """Test non-superuser is denied."""
        user = UserFactory(is_superuser=False)
        request = make_request(request_factory, user)
        perm = IsSuperuser()
        assert perm.has_permission(request, None) is False

    def test_superuser_allowed(self, request_factory):
        """Test superuser is allowed."""
        user = UserFactory(is_superuser=True)
        request = make_request(request_factory, user)
        perm = IsSuperuser()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsEtudiant:
    """Tests for IsEtudiant permission."""

    def test_anonymous_user_denied(self, request_factory):
        """Test anonymous user is denied."""
        request = make_request(request_factory)
        perm = IsEtudiant()
        assert perm.has_permission(request, None) is False

    def test_user_without_role_denied(self, request_factory, role_groups):
        """Test user without Étudiant role is denied."""
        user = UserFactory()
        request = make_request(request_factory, user)
        perm = IsEtudiant()
        assert perm.has_permission(request, None) is False

    def test_user_with_role_allowed(self, request_factory, role_groups):
        """Test user with Étudiant role is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])
        request = make_request(request_factory, user)
        perm = IsEtudiant()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsRespoTER:
    """Tests for IsRespoTER permission."""

    def test_user_with_role_allowed(self, request_factory, role_groups):
        """Test user with Respo TER role is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.RESPO_TER])
        request = make_request(request_factory, user)
        perm = IsRespoTER()
        assert perm.has_permission(request, None) is True

    def test_user_without_role_denied(self, request_factory, role_groups):
        """Test user without Respo TER role is denied."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])
        request = make_request(request_factory, user)
        perm = IsRespoTER()
        assert perm.has_permission(request, None) is False


@pytest.mark.django_db
class TestIsRespoStage:
    """Tests for IsRespoStage permission."""

    def test_user_with_role_allowed(self, request_factory, role_groups):
        """Test user with Respo Stage role is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.RESPO_STAGE])
        request = make_request(request_factory, user)
        perm = IsRespoStage()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsEncadrant:
    """Tests for IsEncadrant permission."""

    def test_user_with_role_allowed(self, request_factory, role_groups):
        """Test user with Encadrant role is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ENCADRANT])
        request = make_request(request_factory, user)
        perm = IsEncadrant()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsExterne:
    """Tests for IsExterne permission."""

    def test_user_with_role_allowed(self, request_factory, role_groups):
        """Test user with Externe role is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.EXTERNE])
        request = make_request(request_factory, user)
        perm = IsExterne()
        assert perm.has_permission(request, None) is True


@pytest.mark.django_db
class TestIsAdmin:
    """Tests for IsAdmin permission."""

    def test_superuser_allowed(self, request_factory, role_groups):
        """Test superuser is allowed even without Admin group."""
        user = UserFactory(is_superuser=True)
        request = make_request(request_factory, user)
        perm = IsAdmin()
        assert perm.has_permission(request, None) is True

    def test_user_with_admin_role_allowed(self, request_factory, role_groups):
        """Test user with Admin role is allowed."""
        user = UserFactory(is_superuser=False)
        user.groups.add(role_groups[Role.ADMIN])
        request = make_request(request_factory, user)
        perm = IsAdmin()
        assert perm.has_permission(request, None) is True

    def test_regular_user_denied(self, request_factory, role_groups):
        """Test regular user is denied."""
        user = UserFactory(is_superuser=False)
        request = make_request(request_factory, user)
        perm = IsAdmin()
        assert perm.has_permission(request, None) is False


@pytest.mark.django_db
class TestIsRespo:
    """Tests for IsRespo (composite) permission."""

    def test_respo_ter_allowed(self, request_factory, role_groups):
        """Test Respo TER is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.RESPO_TER])
        request = make_request(request_factory, user)
        perm = IsRespo()
        assert perm.has_permission(request, None) is True

    def test_respo_stage_allowed(self, request_factory, role_groups):
        """Test Respo Stage is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.RESPO_STAGE])
        request = make_request(request_factory, user)
        perm = IsRespo()
        assert perm.has_permission(request, None) is True

    def test_etudiant_denied(self, request_factory, role_groups):
        """Test Étudiant is denied."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ETUDIANT])
        request = make_request(request_factory, user)
        perm = IsRespo()
        assert perm.has_permission(request, None) is False


@pytest.mark.django_db
class TestIsAcademic:
    """Tests for IsAcademic (composite) permission."""

    def test_encadrant_allowed(self, request_factory, role_groups):
        """Test Encadrant is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.ENCADRANT])
        request = make_request(request_factory, user)
        perm = IsAcademic()
        assert perm.has_permission(request, None) is True

    def test_respo_ter_allowed(self, request_factory, role_groups):
        """Test Respo TER is allowed."""
        user = UserFactory()
        user.groups.add(role_groups[Role.RESPO_TER])
        request = make_request(request_factory, user)
        perm = IsAcademic()
        assert perm.has_permission(request, None) is True

    def test_externe_denied(self, request_factory, role_groups):
        """Test Externe is denied."""
        user = UserFactory()
        user.groups.add(role_groups[Role.EXTERNE])
        request = make_request(request_factory, user)
        perm = IsAcademic()
        assert perm.has_permission(request, None) is False


@pytest.mark.django_db
class TestIsStaffOrRespo:
    """Tests for IsStaffOrRespo (composite) permission."""

    def test_staff_allowed(self, request_factory, role_groups):
        """Test staff user is allowed."""
        user = UserFactory(is_staff=True)
        request = make_request(request_factory, user)
        perm = IsStaffOrRespo()
        assert perm.has_permission(request, None) is True

    def test_respo_ter_allowed(self, request_factory, role_groups):
        """Test Respo TER is allowed."""
        user = UserFactory(is_staff=False)
        user.groups.add(role_groups[Role.RESPO_TER])
        request = make_request(request_factory, user)
        perm = IsStaffOrRespo()
        assert perm.has_permission(request, None) is True

    def test_regular_user_denied(self, request_factory, role_groups):
        """Test regular user is denied."""
        user = UserFactory(is_staff=False)
        request = make_request(request_factory, user)
        perm = IsStaffOrRespo()
        assert perm.has_permission(request, None) is False
