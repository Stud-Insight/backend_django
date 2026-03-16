"""
Tests for Stage Dashboard Workflow Gating Warnings (12-8) and caching (12-10).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.core.cache import cache
from django.test import Client

from backend_django.core.roles import Role
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    PeriodStatus,
    StageApplication,
    StageGrade,
    StageGradeStatus,
    StageOffer,
    StagePeriod,
)
from backend_django.users.models import User


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email="respostage@example.com",
        password="password123",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(email="student@test.com", password="p")
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def externe_user(db):
    user = User.objects.create_user(email="externe@company.com", password="p")
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def encadrant_user(db):
    user = User.objects.create_user(email="prof@uni.com", password="p")
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def stage_period(db):
    today = date.today()
    return StagePeriod.objects.create(
        name="Stage M2 2024-2025",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        offer_submission_start=today - timedelta(days=60),
        offer_submission_end=today - timedelta(days=30),
        application_start=today - timedelta(days=15),
        application_end=today + timedelta(days=30),
        internship_start=today + timedelta(days=60),
        internship_end=today + timedelta(days=180),
    )


class TestStageWarningsAccess:
    def test_admin_can_access(self, client: Client, admin_user, stage_period):
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        assert response.status_code == 200

    def test_student_cannot_access(self, client: Client, student_user, stage_period):
        client.force_login(student_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        assert response.status_code == 403


class TestStageWarningsContent:
    def test_empty_period_shows_no_offers_error(self, client: Client, admin_user, stage_period):
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("Aucune offre" in m for m in messages)

    def test_pending_offers_warning(self, client: Client, admin_user, stage_period, externe_user):
        StageOffer.objects.create(
            stage_period=stage_period, title="Stage IA", description="d",
            company_name="Corp", domain="IA", supervisor=externe_user,
            status=OfferStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("attente de validation" in m for m in messages)

    def test_pending_applications_warning(
        self, client: Client, admin_user, stage_period, externe_user, student_user
    ):
        offer = StageOffer.objects.create(
            stage_period=stage_period, title="Stage IA", description="d",
            company_name="Corp", domain="IA", supervisor=externe_user,
            status=OfferStatus.VALIDATED,
        )
        StageApplication.objects.create(
            student=student_user, offer=offer,
            status=ApplicationStatus.PENDING, motivation="motive",
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("attente de decision" in m for m in messages)

    def test_no_supervisor_warning(
        self, client: Client, admin_user, stage_period, externe_user, student_user
    ):
        offer = StageOffer.objects.create(
            stage_period=stage_period, title="Stage IA", description="d",
            company_name="Corp", domain="IA", supervisor=externe_user,
            status=OfferStatus.VALIDATED,
        )
        StageApplication.objects.create(
            student=student_user, offer=offer,
            status=ApplicationStatus.CONFIRMED, motivation="motive",
            academic_supervisor=None,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("superviseur academique" in m for m in messages)

    def test_missing_grades_warning(
        self, client: Client, admin_user, stage_period, externe_user,
        student_user, encadrant_user
    ):
        offer = StageOffer.objects.create(
            stage_period=stage_period, title="Stage IA", description="d",
            company_name="Corp", domain="IA", supervisor=externe_user,
            status=OfferStatus.VALIDATED,
        )
        app = StageApplication.objects.create(
            student=student_user, offer=offer,
            status=ApplicationStatus.CONFIRMED, motivation="motive",
            academic_supervisor=encadrant_user,
        )
        StageGrade.objects.create(
            application=app, stage_period=stage_period,
            academic_grade=Decimal("15.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        messages = [w["message"] for w in response.json()["warnings"]]
        assert any("entreprise manquante" in m for m in messages)
        assert any("non finalisee" in m for m in messages)

    def test_response_has_correct_structure(self, client: Client, admin_user, stage_period):
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        data = response.json()
        assert "period_id" in data
        assert "period_name" in data
        assert "current_phase" in data
        assert "warnings" in data
        assert isinstance(data["warnings"], list)


class TestStageWarningsCaching:
    """Tests for 12-10 — cache integration on stage warnings endpoint."""

    def test_second_call_uses_cache(self, client: Client, admin_user, stage_period):
        cache.clear()
        client.force_login(admin_user)

        r1 = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        assert r1.status_code == 200

        cache_key = f"stage_warnings_{stage_period.id}"
        assert cache.get(cache_key) is not None

        r2 = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_cache_expires(self, client: Client, admin_user, stage_period):
        cache.clear()
        client.force_login(admin_user)

        client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        cache_key = f"stage_warnings_{stage_period.id}"

        cache.delete(cache_key)
        assert cache.get(cache_key) is None

        r = client.get(f"/api/stages/dashboard/warnings/{stage_period.id}")
        assert r.status_code == 200
        assert cache.get(cache_key) is not None
