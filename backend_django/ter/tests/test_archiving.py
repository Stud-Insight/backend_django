"""Tests for TER period archiving (Stories 11-1, 11-5)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


@pytest.fixture
def respo_ter(db):
    user = User.objects.create_user(
        email="respo-archive@example.com",
        password="password123",
        first_name="Respo",
        last_name="TER",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(group)
    return user


@pytest.fixture
def professor(db):
    user = User.objects.create_user(
        email="prof-archive@example.com",
        password="password123",
        first_name="Prof",
        last_name="Archive",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student(db):
    user = User.objects.create_user(
        email="student-archive@example.com",
        password="password123",
        first_name="Student",
        last_name="Archive",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Archive Test",
        academic_year="2025-2026",
        status=PeriodStatus.CLOSED,
        group_formation_start=today - timedelta(days=120),
        group_formation_end=today - timedelta(days=90),
        subject_selection_start=today - timedelta(days=90),
        subject_selection_end=today - timedelta(days=60),
        assignment_date=today - timedelta(days=59),
        project_start=today - timedelta(days=50),
        project_end=today - timedelta(days=10),
        min_group_size=2,
        max_group_size=5,
    )


@pytest.fixture
def archived_period(ter_period):
    ter_period.status = PeriodStatus.ARCHIVED
    ter_period.save()
    return ter_period


@pytest.fixture
def respo_client(respo_ter):
    client = Client()
    client.login(email=respo_ter.email, password="password123")
    return client


@pytest.fixture
def student_client(student):
    client = Client()
    client.login(email=student.email, password="password123")
    return client


# =============================================================================
# Story 11-1: Archive TER Period
# =============================================================================


@pytest.mark.django_db
class TestArchiveTERPeriod:
    def test_archive_closed_period(self, respo_client, ter_period):
        response = respo_client.post(f"/api/ter/periods/{ter_period.id}/archive")
        assert response.status_code == 200
        ter_period.refresh_from_db()
        assert ter_period.status == PeriodStatus.ARCHIVED

    def test_cannot_archive_open_period(self, respo_client, ter_period):
        ter_period.status = PeriodStatus.OPEN
        ter_period.save()
        response = respo_client.post(f"/api/ter/periods/{ter_period.id}/archive")
        assert response.status_code == 400

    def test_cannot_archive_draft_period(self, respo_client, ter_period):
        ter_period.status = PeriodStatus.DRAFT
        ter_period.save()
        response = respo_client.post(f"/api/ter/periods/{ter_period.id}/archive")
        assert response.status_code == 400

    def test_cannot_archive_already_archived(self, respo_client, archived_period):
        response = respo_client.post(f"/api/ter/periods/{archived_period.id}/archive")
        assert response.status_code == 400

    def test_student_cannot_archive(self, student_client, ter_period):
        response = student_client.post(f"/api/ter/periods/{ter_period.id}/archive")
        assert response.status_code == 403

    def test_unauthenticated_cannot_archive(self, ter_period):
        client = Client()
        response = client.post(f"/api/ter/periods/{ter_period.id}/archive")
        assert response.status_code in (401, 403)


# =============================================================================
# Story 11-5: Enforce Read-Only Archives
# =============================================================================


@pytest.mark.django_db
class TestReadOnlyArchives:
    def test_cannot_add_student_to_archived_period(self, respo_client, archived_period, student):
        response = respo_client.post(
            f"/api/ter/periods/{archived_period.id}/students",
            data={"user_id": str(student.id)},
            content_type="application/json",
        )
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "ARCHIVED"

    def test_cannot_remove_student_from_archived_period(self, respo_client, archived_period, student):
        archived_period.enrolled_students.add(student)
        response = respo_client.delete(
            f"/api/ter/periods/{archived_period.id}/students/{student.id}"
        )
        assert response.status_code == 403

    def test_cannot_add_encadrant_to_archived_period(self, respo_client, archived_period, professor):
        response = respo_client.post(
            f"/api/ter/periods/{archived_period.id}/encadrants/{professor.id}"
        )
        assert response.status_code == 403

    def test_cannot_validate_subject_in_archived_period(
        self, respo_client, archived_period, professor
    ):
        subject = TERSubject.objects.create(
            ter_period=archived_period,
            professor=professor,
            title="Archived Subject",
            description="Should not be validatable",
            status=SubjectStatus.SUBMITTED,
        )
        response = respo_client.post(f"/api/ter/subjects/{subject.id}/validate")
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "ARCHIVED"

    def test_cannot_reject_subject_in_archived_period(
        self, respo_client, archived_period, professor
    ):
        subject = TERSubject.objects.create(
            ter_period=archived_period,
            professor=professor,
            title="Archived Subject 2",
            description="Should not be rejectable",
            status=SubjectStatus.SUBMITTED,
        )
        response = respo_client.post(
            f"/api/ter/subjects/{subject.id}/reject",
            data={"reason": "Sujet hors perimetre pour cette periode"},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_can_still_read_archived_data(self, respo_client, archived_period):
        """Archived periods should still be readable."""
        response = respo_client.get(f"/api/ter/periods/{archived_period.id}")
        assert response.status_code == 200

    def test_can_copy_archived_period(self, respo_client, archived_period):
        """Copying an archived period should work (it creates a new period)."""
        response = respo_client.post(
            f"/api/ter/periods/{archived_period.id}/copy",
            data={
                "name": "TER Copy",
                "academic_year": "2026-2027",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
