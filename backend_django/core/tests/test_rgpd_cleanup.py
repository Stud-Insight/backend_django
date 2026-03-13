"""Tests for RGPD retention cleanup task (Story 11-6)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from backend_django.core.tasks import RETENTION_YEARS, rgpd_anonymize_expired_archives
from backend_django.notifications.models import Notification
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    StageApplication,
    StageOffer,
    StagePeriod,
)
from backend_django.stages.models import PeriodStatus as StagePeriodStatus
from backend_django.ter.models import PeriodStatus as TERPeriodStatus
from backend_django.ter.models import TERPeriod
from backend_django.users.models import User


@pytest.fixture
def old_ter_period(db):
    today = date.today()
    period = TERPeriod.objects.create(
        name="TER 2022 (expired)",
        academic_year="2022-2023",
        status=TERPeriodStatus.ARCHIVED,
        group_formation_start=today - timedelta(days=1200),
        group_formation_end=today - timedelta(days=1170),
        subject_selection_start=today - timedelta(days=1170),
        subject_selection_end=today - timedelta(days=1140),
        assignment_date=today - timedelta(days=1139),
        project_start=today - timedelta(days=1130),
        project_end=today - timedelta(days=1000),
        min_group_size=2,
        max_group_size=5,
    )
    # Force modified to be old enough
    cutoff = timezone.now() - timedelta(days=RETENTION_YEARS * 365 + 10)
    TERPeriod.objects.filter(id=period.id).update(modified=cutoff)
    period.refresh_from_db()
    return period


@pytest.fixture
def recent_ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2025 (recent)",
        academic_year="2025-2026",
        status=TERPeriodStatus.ARCHIVED,
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
def old_stage_period(db):
    today = date.today()
    period = StagePeriod.objects.create(
        name="Stage 2022 (expired)",
        academic_year="2022-2023",
        status=StagePeriodStatus.ARCHIVED,
        offer_submission_start=today - timedelta(days=1200),
        offer_submission_end=today - timedelta(days=1170),
        application_start=today - timedelta(days=1170),
        application_end=today - timedelta(days=1140),
        internship_start=today - timedelta(days=1100),
        internship_end=today - timedelta(days=1000),
    )
    cutoff = timezone.now() - timedelta(days=RETENTION_YEARS * 365 + 10)
    StagePeriod.objects.filter(id=period.id).update(modified=cutoff)
    period.refresh_from_db()
    return period


@pytest.fixture
def student(db):
    return User.objects.create_user(
        email="rgpd-student@example.com",
        password="password123",
        first_name="RGPD",
        last_name="Student",
    )


@pytest.fixture
def externe(db):
    return User.objects.create_user(
        email="rgpd-externe@example.com",
        password="password123",
        first_name="RGPD",
        last_name="Externe",
    )


@pytest.mark.django_db
class TestRGPDAnonymizeExpiredArchives:
    def test_anonymizes_old_ter_period(self, old_ter_period, student):
        old_ter_period.enrolled_students.add(student)
        assert old_ter_period.enrolled_students.count() == 1

        result = rgpd_anonymize_expired_archives()

        assert result > 0
        old_ter_period.refresh_from_db()
        assert old_ter_period.enrolled_students.count() == 0

    def test_does_not_touch_recent_archived_period(self, recent_ter_period, student):
        recent_ter_period.enrolled_students.add(student)

        rgpd_anonymize_expired_archives()

        recent_ter_period.refresh_from_db()
        assert recent_ter_period.enrolled_students.count() == 1

    def test_anonymizes_stage_applications(self, old_stage_period, externe, student):
        offer = StageOffer.objects.create(
            stage_period=old_stage_period,
            supervisor=externe,
            title="Old Offer",
            description="Test",
            company_name="Corp",
            status=OfferStatus.VALIDATED,
        )
        StageApplication.objects.create(
            offer=offer,
            student=student,
            motivation="Ma motivation personnelle detaillee",
            status=ApplicationStatus.PENDING,
        )

        result = rgpd_anonymize_expired_archives()

        assert result > 0
        app = StageApplication.objects.first()
        assert app.motivation == "[Anonymisé]"

    def test_no_work_when_no_expired_archives(self, recent_ter_period):
        result = rgpd_anonymize_expired_archives()
        assert result == 0

    def test_preserves_academic_records(self, old_ter_period, student):
        """Academic data (period name, subjects) should be preserved."""
        old_ter_period.enrolled_students.add(student)

        rgpd_anonymize_expired_archives()

        old_ter_period.refresh_from_db()
        assert old_ter_period.name == "TER 2022 (expired)"
        assert old_ter_period.status == TERPeriodStatus.ARCHIVED
