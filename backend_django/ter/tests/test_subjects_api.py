"""
Tests for TER Subjects API - Nullable Period functionality.

Tests the workflow where professors can create draft subjects without a period,
then assign a period when submitting for approval.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.core.roles import Role
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


@pytest.fixture
def encadrant_user(db):
    """Create an encadrant (professor) user."""
    user = User.objects.create_user(
        email="prof@example.com",
        password="password123",
        first_name="Prof",
        last_name="Dupont",
    )
    # Add to Encadrant group (required for permission check)
    encadrant_group, _ = Group.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(encadrant_group)
    return user


@pytest.fixture
def admin_user(db):
    """Create an admin user (Respo TER)."""
    user = User.objects.create_user(
        email="admin@example.com",
        password="password123",
        first_name="Admin",
        last_name="Respo",
        is_staff=True,
    )
    # Add to Respo TER group for TER admin privileges
    respo_ter_group, _ = Group.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(respo_ter_group)
    return user


@pytest.fixture
def ter_period(db):
    """Create an open TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025 S1",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=30),
        group_formation_end=today + timedelta(days=30),
        subject_selection_start=today - timedelta(days=15),
        subject_selection_end=today + timedelta(days=45),
        assignment_date=today + timedelta(days=50),
        project_start=today + timedelta(days=60),
        project_end=today + timedelta(days=150),
        min_group_size=2,
        max_group_size=4,
    )


@pytest.fixture
def draft_period(db):
    """Create a draft TER period (not open yet)."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2025-2026 S1",
        academic_year="2025-2026",
        status=PeriodStatus.DRAFT,
        group_formation_start=today + timedelta(days=100),
        group_formation_end=today + timedelta(days=130),
        subject_selection_start=today + timedelta(days=115),
        subject_selection_end=today + timedelta(days=145),
        assignment_date=today + timedelta(days=150),
        project_start=today + timedelta(days=160),
        project_end=today + timedelta(days=250),
        min_group_size=2,
        max_group_size=4,
    )


class TestCreateSubjectWithoutPeriod:
    """Tests for creating subjects without a period (draft mode)."""

    def test_create_subject_without_period_succeeds(self, client: Client, encadrant_user):
        """Encadrant can create a draft subject without specifying a period."""
        client.force_login(encadrant_user)

        response = client.post(
            "/api/ter/subjects/",
            data={
                "title": "Sujet de recherche sur l'IA",
                "description": "Une description detaillee du sujet de recherche qui fait plus de 50 caracteres.",
                "domain": "IA/ML",
                "prerequisites": "",
                "max_groups": 2,
                # No ter_period_id provided
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Sujet de recherche sur l'IA"
        assert data["status"] == SubjectStatus.DRAFT
        assert data["ter_period_id"] is None  # No period assigned

    def test_create_subject_with_period_succeeds(self, client: Client, encadrant_user, ter_period):
        """Encadrant can create a subject with a period directly."""
        client.force_login(encadrant_user)

        response = client.post(
            "/api/ter/subjects/",
            data={
                "ter_period_id": str(ter_period.id),
                "title": "Sujet avec periode",
                "description": "Une description detaillee du sujet de recherche qui fait plus de 50 caracteres.",
                "domain": "Securite",
                "max_groups": 1,
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["ter_period_id"] == str(ter_period.id)
        assert data["status"] == SubjectStatus.DRAFT


class TestUpdateSubjectPeriod:
    """Tests for updating a subject's period."""

    def test_assign_period_to_subject_without_period(self, client: Client, encadrant_user, ter_period):
        """Encadrant can assign a period to a subject that doesn't have one."""
        client.force_login(encadrant_user)

        # Create subject without period
        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.put(
            f"/api/ter/subjects/{subject.id}",
            data={
                "ter_period_id": str(ter_period.id),
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ter_period_id"] == str(ter_period.id)

        subject.refresh_from_db()
        assert subject.ter_period_id == ter_period.id

    def test_cannot_assign_draft_period_as_non_admin(self, client: Client, encadrant_user, draft_period):
        """Non-admin cannot assign a draft period to a subject."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.put(
            f"/api/ter/subjects/{subject.id}",
            data={
                "ter_period_id": str(draft_period.id),
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "pas ouverte" in response.json()["message"]

    def test_admin_can_assign_draft_period(self, client: Client, admin_user, draft_period):
        """Admin can assign a draft period to a subject."""
        client.force_login(admin_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=admin_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.put(
            f"/api/ter/subjects/{subject.id}",
            data={
                "ter_period_id": str(draft_period.id),
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        assert response.json()["ter_period_id"] == str(draft_period.id)


class TestSubmitSubjectWithoutPeriod:
    """Tests for submitting a subject that doesn't have a period."""

    def test_submit_without_period_fails_if_no_param(self, client: Client, encadrant_user):
        """Submitting a subject without a period fails if no period param is passed."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.post(f"/api/ter/subjects/{subject.id}/submit")

        assert response.status_code == 400
        data = response.json()
        # Check for the key part of the message (handles accents)
        assert "TER est requise" in data["message"]

    def test_submit_with_period_param_succeeds(self, client: Client, encadrant_user, ter_period):
        """Submitting a subject without a period succeeds if period param is passed."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.post(
            f"/api/ter/subjects/{subject.id}/submit",
            QUERY_STRING=f"ter_period_id={ter_period.id}",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == SubjectStatus.SUBMITTED
        assert data["ter_period_id"] == str(ter_period.id)

        subject.refresh_from_db()
        assert subject.status == SubjectStatus.SUBMITTED
        assert subject.ter_period_id == ter_period.id

    def test_submit_with_existing_period_succeeds(self, client: Client, encadrant_user, ter_period):
        """Submitting a subject that already has a period works normally."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=ter_period,
            title="Sujet avec periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="IA/ML",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.post(f"/api/ter/subjects/{subject.id}/submit")

        assert response.status_code == 200
        assert response.json()["status"] == SubjectStatus.SUBMITTED

    def test_submit_to_draft_period_fails_for_non_admin(self, client: Client, encadrant_user, draft_period):
        """Non-admin cannot submit to a draft period."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.post(
            f"/api/ter/subjects/{subject.id}/submit",
            QUERY_STRING=f"ter_period_id={draft_period.id}",
        )

        assert response.status_code == 400
        assert "pas ouverte" in response.json()["message"]


class TestGroupSizeValidationWithNullPeriod:
    """Tests for group size validation when period is nullable."""

    def test_create_without_period_no_group_size_validation(self, client: Client, encadrant_user):
        """When creating without a period, no group size bounds validation occurs."""
        client.force_login(encadrant_user)

        response = client.post(
            "/api/ter/subjects/",
            data={
                "title": "Sujet avec groupe flexible",
                "description": "Description longue pour passer la validation minimale de 50 caracteres.",
                "domain": "Systemes",
                "min_group_size": 1,  # Would be invalid for a period with min=2
                "max_group_size": 10,  # Would be invalid for a period with max=4
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["min_group_size"] == 1
        assert data["max_group_size"] == 10

    def test_submit_validates_group_size_against_period(self, client: Client, encadrant_user, ter_period):
        """When submitting, group size bounds are validated against the period."""
        client.force_login(encadrant_user)

        # Create subject with invalid group sizes for the period
        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet avec groupe trop grand",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
            min_group_size=1,  # Period min is 2
            max_group_size=10,  # Period max is 4
        )

        response = client.post(
            f"/api/ter/subjects/{subject.id}/submit",
            QUERY_STRING=f"ter_period_id={ter_period.id}",
        )

        assert response.status_code == 400
        # Should fail on min_group_size first
        assert "min_group_size" in response.json()["message"]

    def test_update_without_period_no_bounds_check(self, client: Client, encadrant_user):
        """When updating a subject without a period, no bounds check occurs."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.put(
            f"/api/ter/subjects/{subject.id}",
            data={
                "min_group_size": 1,
                "max_group_size": 100,
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["min_group_size"] == 1
        assert data["max_group_size"] == 100


class TestListSubjectsWithNullPeriod:
    """Tests for listing subjects with nullable periods."""

    def test_list_subjects_includes_those_without_period(self, client: Client, encadrant_user):
        """Subjects without a period appear in the list for their owner."""
        client.force_login(encadrant_user)

        subject = TERSubject.objects.create(
            ter_period=None,
            title="Sujet brouillon sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.get("/api/ter/subjects/me")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["id"] == str(subject.id)
        assert data["results"][0]["ter_period_id"] is None

    def test_filter_by_period_excludes_null_period_subjects(self, client: Client, encadrant_user, ter_period):
        """Filtering by period excludes subjects without a period."""
        client.force_login(encadrant_user)

        # Subject without period
        TERSubject.objects.create(
            ter_period=None,
            title="Sujet brouillon sans periode",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="Web",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        # Subject with period
        TERSubject.objects.create(
            ter_period=ter_period,
            title="Sujet avec periode specifique",
            description="Description longue pour passer la validation minimale de 50 caracteres.",
            domain="IA",
            professor=encadrant_user,
            status=SubjectStatus.DRAFT,
        )

        response = client.get(f"/api/ter/subjects/me?ter_period_id={ter_period.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["ter_period_id"] == str(ter_period.id)
