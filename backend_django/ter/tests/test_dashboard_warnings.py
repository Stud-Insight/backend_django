"""
Tests for TER Dashboard Workflow Gating Warnings (12-8) and caching (12-10).
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.core.cache import cache
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group
from backend_django.ter.models import (
    GradeStatus,
    PeriodStatus,
    SubjectStatus,
    TERGrade,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.users.models import User


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email="respoter@example.com",
        password="password123",
        first_name="Respo",
        last_name="TER",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(
        email="student@example.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def encadrant_user(db):
    user = User.objects.create_user(
        email="prof@example.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=60),
        group_formation_end=today - timedelta(days=30),
        subject_selection_start=today - timedelta(days=25),
        subject_selection_end=today - timedelta(days=10),
        assignment_date=today - timedelta(days=5),
        project_start=today - timedelta(days=3),
        project_end=today + timedelta(days=90),
        min_group_size=2,
        max_group_size=4,
    )


class TestTERWarningsAccess:
    def test_admin_can_access(self, client: Client, admin_user, ter_period):
        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        assert response.status_code == 200

    def test_student_cannot_access(self, client: Client, student_user, ter_period):
        client.force_login(student_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        assert response.status_code == 403


class TestTERWarningsContent:
    def test_empty_period_shows_errors(self, client: Client, admin_user, ter_period):
        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        data = response.json()
        assert data["period_id"] == str(ter_period.id)
        messages = [w["message"] for w in data["warnings"]]
        assert any("Aucun sujet" in m for m in messages)
        assert any("Aucun etudiant" in m for m in messages)

    def test_pending_subjects_warning(self, client: Client, admin_user, ter_period, encadrant_user):
        TERSubject.objects.create(
            ter_period=ter_period, title="Sujet 1", description="desc",
            domain="IA", professor=encadrant_user, status=SubjectStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("attente de validation" in m for m in messages)

    def test_solitaires_warning(self, client: Client, admin_user, ter_period, student_user):
        ter_period.enrolled_students.add(student_user)
        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("sans groupe" in m for m in messages)

    def test_no_validated_subjects_error(self, client: Client, admin_user, ter_period, encadrant_user):
        TERSubject.objects.create(
            ter_period=ter_period, title="Sujet 1", description="desc",
            domain="IA", professor=encadrant_user, status=SubjectStatus.DRAFT,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        warnings = response.json()["warnings"]
        error_msgs = [w["message"] for w in warnings if w["level"] == "error"]
        assert any("classement est impossible" in m for m in error_msgs)

    def test_missing_rankings_warning(
        self, client: Client, admin_user, ter_period, student_user, encadrant_user
    ):
        ter_period.enrolled_students.add(student_user)
        student2 = User.objects.create_user(email="s2@test.com", password="p")
        ter_period.enrolled_students.add(student2)

        group = Group.objects.create(
            name="G1", ter_period=ter_period, leader=student_user, status="forme",
        )
        group.members.add(student_user, student2)

        subject = TERSubject.objects.create(
            ter_period=ter_period, title="S1", description="d",
            domain="IA", professor=encadrant_user, status=SubjectStatus.VALIDATED,
        )

        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("classement" in m for m in messages)

    def test_unfinalized_grades_warning(
        self, client: Client, admin_user, ter_period, student_user, encadrant_user
    ):
        ter_period.enrolled_students.add(student_user)
        group = Group.objects.create(
            name="G1", ter_period=ter_period, leader=student_user, status="forme",
        )
        group.members.add(student_user)

        subject = TERSubject.objects.create(
            ter_period=ter_period, title="S1", description="d",
            domain="IA", professor=encadrant_user, status=SubjectStatus.VALIDATED,
        )
        group.assigned_subject = subject
        group.save()

        TERGrade.objects.create(
            ter_period=ter_period, group=group,
            group_grade=Decimal("15.00"), status=GradeStatus.SUBMITTED,
        )

        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("non finalisee" in m for m in messages)

    def test_clean_period_has_no_errors(
        self, client: Client, admin_user, ter_period, student_user, encadrant_user
    ):
        """A fully configured period with all steps done should have no errors."""
        ter_period.enrolled_students.add(student_user)
        student2 = User.objects.create_user(email="s2@test.com", password="p")
        ter_period.enrolled_students.add(student2)

        group = Group.objects.create(
            name="G1", ter_period=ter_period, leader=student_user, status="forme",
        )
        group.members.add(student_user, student2)

        subject = TERSubject.objects.create(
            ter_period=ter_period, title="S1", description="d",
            domain="IA", professor=encadrant_user, status=SubjectStatus.VALIDATED,
        )
        group.assigned_subject = subject
        group.save()

        TERRanking.objects.create(group=group, subject=subject, rank=1)

        TERGrade.objects.create(
            ter_period=ter_period, group=group,
            group_grade=Decimal("15.00"), status=GradeStatus.FINALIZED,
        )

        client.force_login(admin_user)
        response = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        warnings = response.json()["warnings"]
        errors = [w for w in warnings if w["level"] == "error"]
        assert len(errors) == 0


class TestTERWarningsCaching:
    """Tests for 12-10 — Redis/cache integration on warnings endpoint."""

    def test_second_call_uses_cache(self, client: Client, admin_user, ter_period):
        cache.clear()
        client.force_login(admin_user)

        # First call populates cache
        r1 = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        assert r1.status_code == 200

        # Verify cache key exists
        cache_key = f"ter_warnings_{ter_period.id}"
        assert cache.get(cache_key) is not None

        # Second call should use cache (no DB queries for warnings logic)
        r2 = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_cache_expires(self, client: Client, admin_user, ter_period):
        cache.clear()
        client.force_login(admin_user)

        client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        cache_key = f"ter_warnings_{ter_period.id}"

        # Manually delete cache to simulate expiry
        cache.delete(cache_key)
        assert cache.get(cache_key) is None

        # Next call should repopulate
        r = client.get(f"/api/ter/dashboard/warnings/{ter_period.id}")
        assert r.status_code == 200
        assert cache.get(cache_key) is not None

    def test_admin_stats_uses_cache(self, client: Client, admin_user):
        cache.clear()
        client.force_login(admin_user)

        r1 = client.get("/api/ter/dashboard/admin/stats")
        assert r1.status_code == 200
        assert cache.get("ter_admin_stats") is not None

        r2 = client.get("/api/ter/dashboard/admin/stats")
        assert r2.status_code == 200
        assert r1.json() == r2.json()
