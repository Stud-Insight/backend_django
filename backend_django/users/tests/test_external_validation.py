"""
Tests for Story 1-6: External account validation by admin.
"""

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.users.models import ExternalValidationStatus, User


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email="admin@example.com", password="password123", is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def pending_externe(db):
    user = User.objects.create_user(
        email="externe@company.com", password="password123",
        first_name="Jean", last_name="Dupont",
        company_name="ACME Corp", is_active=False,
    )
    user.external_validation_status = ExternalValidationStatus.PENDING
    user.save()
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(email="student@test.com", password="p")
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


class TestExternalPendingList:
    def test_admin_sees_pending(self, client: Client, admin_user, pending_externe):
        client.force_login(admin_user)
        r = client.get("/api/users/external-pending")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["email"] == "externe@company.com"
        assert data[0]["company_name"] == "ACME Corp"

    def test_student_cannot_access(self, client: Client, student_user):
        client.force_login(student_user)
        r = client.get("/api/users/external-pending")
        assert r.status_code == 403

    def test_empty_when_no_pending(self, client: Client, admin_user):
        client.force_login(admin_user)
        r = client.get("/api/users/external-pending")
        assert r.status_code == 200
        assert r.json() == []


class TestValidateExternal:
    def test_approve_activates_account(self, client: Client, admin_user, pending_externe):
        client.force_login(admin_user)
        r = client.post(
            f"/api/users/{pending_externe.id}/validate-external",
            content_type="application/json",
        )
        assert r.status_code == 200

        pending_externe.refresh_from_db()
        assert pending_externe.external_validation_status == ExternalValidationStatus.APPROVED
        assert pending_externe.is_active is True

    def test_approve_non_pending_fails(self, client: Client, admin_user, pending_externe):
        pending_externe.external_validation_status = ExternalValidationStatus.APPROVED
        pending_externe.save()

        client.force_login(admin_user)
        r = client.post(
            f"/api/users/{pending_externe.id}/validate-external",
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_approve_unknown_user_404(self, client: Client, admin_user):
        import uuid
        client.force_login(admin_user)
        r = client.post(
            f"/api/users/{uuid.uuid4()}/validate-external",
            content_type="application/json",
        )
        assert r.status_code == 404


class TestRejectExternal:
    def test_reject_with_reason(self, client: Client, admin_user, pending_externe):
        client.force_login(admin_user)
        r = client.post(
            f"/api/users/{pending_externe.id}/reject-external",
            data={"reason": "Entreprise non partenaire"},
            content_type="application/json",
        )
        assert r.status_code == 200

        pending_externe.refresh_from_db()
        assert pending_externe.external_validation_status == ExternalValidationStatus.REJECTED
        assert pending_externe.external_rejection_reason == "Entreprise non partenaire"
        assert pending_externe.is_active is False

    def test_reject_non_pending_fails(self, client: Client, admin_user, pending_externe):
        pending_externe.external_validation_status = ExternalValidationStatus.APPROVED
        pending_externe.save()

        client.force_login(admin_user)
        r = client.post(
            f"/api/users/{pending_externe.id}/reject-external",
            data={"reason": "x"},
            content_type="application/json",
        )
        assert r.status_code == 400


class TestExternalLoginBlocking:
    def test_pending_externe_cannot_login(self, client: Client, pending_externe):
        # Pending externe has is_active=False so authenticate() returns None
        # But if somehow active, the login check should block
        pending_externe.is_active = True
        pending_externe.save()

        r = client.post(
            "/api/auth/login",
            data={"email": "externe@company.com", "password": "password123"},
            content_type="application/json",
        )
        assert r.status_code == 403
        assert r.json()["code"] == "EXTERNAL_PENDING"

    def test_rejected_externe_cannot_login(self, client: Client, pending_externe):
        pending_externe.external_validation_status = ExternalValidationStatus.REJECTED
        pending_externe.is_active = True  # Edge case
        pending_externe.save()

        r = client.post(
            "/api/auth/login",
            data={"email": "externe@company.com", "password": "password123"},
            content_type="application/json",
        )
        assert r.status_code == 403
        assert r.json()["code"] == "EXTERNAL_REJECTED"

    def test_approved_externe_can_login(self, client: Client, pending_externe):
        pending_externe.external_validation_status = ExternalValidationStatus.APPROVED
        pending_externe.is_active = True
        pending_externe.save()

        r = client.post(
            "/api/auth/login",
            data={"email": "externe@company.com", "password": "password123"},
            content_type="application/json",
        )
        assert r.status_code == 200

    def test_normal_user_not_affected(self, client: Client, student_user):
        """Users with status NONE should not be blocked."""
        student_user.is_active = True
        student_user.set_password("testpass")
        student_user.save()

        r = client.post(
            "/api/auth/login",
            data={"email": "student@test.com", "password": "testpass"},
            content_type="application/json",
        )
        assert r.status_code == 200
