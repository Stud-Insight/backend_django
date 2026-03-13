"""Tests for Stage period archiving (Stories 11-2, 11-5)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    StageApplication,
    StageOffer,
    StagePeriod,
)
from backend_django.stages.models import PeriodStatus as StagePeriodStatus
from backend_django.users.models import User


@pytest.fixture
def respo_stage(db):
    user = User.objects.create_user(
        email="respo-stage-archive@example.com",
        password="password123",
        first_name="Respo",
        last_name="Stage",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def externe(db):
    user = User.objects.create_user(
        email="externe-archive@example.com",
        password="password123",
        first_name="Externe",
        last_name="Archive",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student(db):
    user = User.objects.create_user(
        email="student-stage-archive@example.com",
        password="password123",
        first_name="Student",
        last_name="Archive",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def stage_period(db):
    today = date.today()
    return StagePeriod.objects.create(
        name="Stage Archive Test",
        academic_year="2025-2026",
        status=StagePeriodStatus.CLOSED,
        offer_submission_start=today - timedelta(days=120),
        offer_submission_end=today - timedelta(days=90),
        application_start=today - timedelta(days=90),
        application_end=today - timedelta(days=60),
        internship_start=today - timedelta(days=30),
        internship_end=today - timedelta(days=1),
    )


@pytest.fixture
def archived_stage_period(stage_period):
    stage_period.status = StagePeriodStatus.ARCHIVED
    stage_period.save()
    return stage_period


@pytest.fixture
def respo_client(respo_stage):
    client = Client()
    client.login(email=respo_stage.email, password="password123")
    return client


@pytest.fixture
def externe_client(externe):
    client = Client()
    client.login(email=externe.email, password="password123")
    return client


# =============================================================================
# Story 11-2: Archive Stage Period
# =============================================================================


@pytest.mark.django_db
class TestArchiveStagePeriod:
    def test_archive_closed_period(self, respo_client, stage_period):
        response = respo_client.post(f"/api/stages/periods/{stage_period.id}/archive")
        assert response.status_code == 200
        stage_period.refresh_from_db()
        assert stage_period.status == StagePeriodStatus.ARCHIVED

    def test_cannot_archive_open_period(self, respo_client, stage_period):
        stage_period.status = StagePeriodStatus.OPEN
        stage_period.save()
        response = respo_client.post(f"/api/stages/periods/{stage_period.id}/archive")
        assert response.status_code == 400

    def test_cannot_archive_draft_period(self, respo_client, stage_period):
        stage_period.status = StagePeriodStatus.DRAFT
        stage_period.save()
        response = respo_client.post(f"/api/stages/periods/{stage_period.id}/archive")
        assert response.status_code == 400

    def test_student_cannot_archive(self, student, stage_period):
        client = Client()
        client.login(email=student.email, password="password123")
        response = client.post(f"/api/stages/periods/{stage_period.id}/archive")
        assert response.status_code == 403


# =============================================================================
# Story 11-5: Read-Only Archives (Stage)
# =============================================================================


@pytest.mark.django_db
class TestReadOnlyStageArchives:
    def test_cannot_validate_offer_in_archived_period(
        self, respo_client, archived_stage_period, externe
    ):
        offer = StageOffer.objects.create(
            stage_period=archived_stage_period,
            supervisor=externe,
            title="Archived Offer",
            description="Should not be validatable",
            company_name="Corp",
            status=OfferStatus.SUBMITTED,
        )
        response = respo_client.post(f"/api/stages/offers/{offer.id}/validate")
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "ARCHIVED"

    def test_cannot_reject_offer_in_archived_period(
        self, respo_client, archived_stage_period, externe
    ):
        offer = StageOffer.objects.create(
            stage_period=archived_stage_period,
            supervisor=externe,
            title="Archived Offer 2",
            description="Should not be rejectable",
            company_name="Corp",
            status=OfferStatus.SUBMITTED,
        )
        response = respo_client.post(
            f"/api/stages/offers/{offer.id}/reject",
            data={"reason": "Offre incompatible avec le programme academique"},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_cannot_accept_application_in_archived_period(
        self, externe_client, archived_stage_period, externe, student
    ):
        offer = StageOffer.objects.create(
            stage_period=archived_stage_period,
            supervisor=externe,
            title="Archived Offer 3",
            description="Test",
            company_name="Corp",
            status=OfferStatus.VALIDATED,
        )
        application = StageApplication.objects.create(
            offer=offer,
            student=student,
            motivation="Test",
            status=ApplicationStatus.PENDING,
        )
        response = externe_client.post(
            f"/api/stages/offers/{offer.id}/applications/{application.id}/accept"
        )
        assert response.status_code == 403
