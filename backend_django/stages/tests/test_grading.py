"""
Tests for Stage Grading API (Epic 10) and CSV Export (12-7).

Tests:
- 10-1: Academic grading by encadrant
- 10-2: Company grading by externe
- 10-3: Grade finalization by admin
- 10-4: Student grade visibility
- 12-7: CSV export
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group as DjangoGroup
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
def student_user(db):
    user = User.objects.create_user(
        email="student@example.com",
        password="password123",
        first_name="Alice",
        last_name="Martin",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def externe_user(db):
    user = User.objects.create_user(
        email="externe@company.com",
        password="password123",
        first_name="Bob",
        last_name="Dupont",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def encadrant_user(db):
    user = User.objects.create_user(
        email="encadrant@university.com",
        password="password123",
        first_name="Claire",
        last_name="Prof",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email="admin@example.com",
        password="password123",
        first_name="Admin",
        last_name="Respo",
        is_staff=True,
    )
    respo_group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(respo_group)
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


@pytest.fixture
def validated_offer(db, stage_period, externe_user):
    return StageOffer.objects.create(
        stage_period=stage_period,
        title="Stage IA",
        description="Stage en intelligence artificielle",
        company_name="TechCorp",
        location="Paris",
        domain="IA/ML",
        supervisor=externe_user,
        max_students=1,
        status=OfferStatus.VALIDATED,
    )


@pytest.fixture
def confirmed_application(db, student_user, validated_offer, encadrant_user):
    return StageApplication.objects.create(
        student=student_user,
        offer=validated_offer,
        status=ApplicationStatus.CONFIRMED,
        motivation="Tres motive",
        academic_supervisor=encadrant_user,
    )


class TestGetGrade:
    """Tests for getting a grade (10-1)."""

    def test_encadrant_can_view_grade(self, client: Client, encadrant_user, confirmed_application):
        client.force_login(encadrant_user)
        response = client.get(f"/api/stages/grades/{confirmed_application.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["application_id"] == str(confirmed_application.id)
        assert data["status"] == "draft"

    def test_externe_can_view_grade(self, client: Client, externe_user, confirmed_application):
        client.force_login(externe_user)
        response = client.get(f"/api/stages/grades/{confirmed_application.id}")
        assert response.status_code == 200

    def test_student_can_view_own_grade(self, client: Client, student_user, confirmed_application):
        client.force_login(student_user)
        response = client.get(f"/api/stages/grades/{confirmed_application.id}")
        assert response.status_code == 200

    def test_other_student_cannot_view_grade(self, client: Client, confirmed_application, db):
        other = User.objects.create_user(email="other@test.com", password="password123")
        group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
        other.groups.add(group)
        client.force_login(other)
        response = client.get(f"/api/stages/grades/{confirmed_application.id}")
        assert response.status_code == 403

    def test_admin_can_view_any_grade(self, client: Client, admin_user, confirmed_application):
        client.force_login(admin_user)
        response = client.get(f"/api/stages/grades/{confirmed_application.id}")
        assert response.status_code == 200


class TestAcademicGrading:
    """Tests for academic grading (10-1)."""

    def test_encadrant_can_set_academic_grade(self, client: Client, encadrant_user, confirmed_application):
        client.force_login(encadrant_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/academic",
            data={"academic_grade": "15.50", "academic_grade_comment": "Bon travail"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["academic_grade"]) == Decimal("15.50")
        assert data["academic_grade_comment"] == "Bon travail"
        assert data["status"] == "submitted"

    def test_externe_cannot_set_academic_grade(self, client: Client, externe_user, confirmed_application):
        client.force_login(externe_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/academic",
            data={"academic_grade": "15.00"},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_invalid_grade_rejected(self, client: Client, encadrant_user, confirmed_application):
        client.force_login(encadrant_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/academic",
            data={"academic_grade": "21.00"},
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_admin_can_set_academic_grade(self, client: Client, admin_user, confirmed_application):
        client.force_login(admin_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/academic",
            data={"academic_grade": "14.00"},
            content_type="application/json",
        )
        assert response.status_code == 200


class TestCompanyGrading:
    """Tests for company grading (10-2)."""

    def test_externe_can_set_company_grade(self, client: Client, externe_user, confirmed_application):
        client.force_login(externe_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/company",
            data={"company_grade": "16.00", "company_grade_comment": "Excellent stagiaire"},
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["company_grade"]) == Decimal("16.00")
        assert data["company_grade_comment"] == "Excellent stagiaire"

    def test_encadrant_cannot_set_company_grade(self, client: Client, encadrant_user, confirmed_application):
        client.force_login(encadrant_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/company",
            data={"company_grade": "15.00"},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_invalid_company_grade_rejected(self, client: Client, externe_user, confirmed_application):
        client.force_login(externe_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/company",
            data={"company_grade": "-1.00"},
            content_type="application/json",
        )
        assert response.status_code == 422


class TestGradeFinalization:
    """Tests for grade finalization (10-3)."""

    def test_admin_can_finalize_with_both_grades(
        self, client: Client, admin_user, confirmed_application
    ):
        grade = StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.post(
            f"/api/stages/grades/{confirmed_application.id}/finalize",
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        grade.refresh_from_db()
        assert grade.status == StageGradeStatus.FINALIZED
        assert grade.final_grade == Decimal("16.00")

    def test_cannot_finalize_without_academic_grade(
        self, client: Client, admin_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            company_grade=Decimal("17.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.post(
            f"/api/stages/grades/{confirmed_application.id}/finalize",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_cannot_finalize_without_company_grade(
        self, client: Client, admin_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(admin_user)
        response = client.post(
            f"/api/stages/grades/{confirmed_application.id}/finalize",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_non_admin_cannot_finalize(
        self, client: Client, encadrant_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(encadrant_user)
        response = client.post(
            f"/api/stages/grades/{confirmed_application.id}/finalize",
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_cannot_modify_after_finalization(
        self, client: Client, encadrant_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            status=StageGradeStatus.FINALIZED,
        )
        client.force_login(encadrant_user)
        response = client.put(
            f"/api/stages/grades/{confirmed_application.id}/academic",
            data={"academic_grade": "18.00"},
            content_type="application/json",
        )
        assert response.status_code == 400


class TestStudentGradeVisibility:
    """Tests for student grade visibility (10-4)."""

    def test_student_sees_no_grades_before_finalization(
        self, client: Client, student_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            status=StageGradeStatus.SUBMITTED,
        )
        client.force_login(student_user)
        response = client.get("/api/stages/grades/my-grades")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["academic_grade"] is None
        assert data[0]["company_grade"] is None
        assert data[0]["final_grade"] is None
        assert data[0]["status"] == "submitted"

    def test_student_sees_grades_after_finalization(
        self, client: Client, student_user, confirmed_application
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=confirmed_application.offer.stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            final_grade=Decimal("16.00"),
            status=StageGradeStatus.FINALIZED,
        )
        client.force_login(student_user)
        response = client.get("/api/stages/grades/my-grades")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert Decimal(data[0]["academic_grade"]) == Decimal("15.00")
        assert Decimal(data[0]["company_grade"]) == Decimal("17.00")
        assert Decimal(data[0]["final_grade"]) == Decimal("16.00")


class TestGradesByPeriod:
    """Tests for listing grades by period."""

    def test_admin_sees_all_grades(
        self, client: Client, admin_user, confirmed_application, stage_period
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=stage_period,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/grades/period/{stage_period.id}")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_encadrant_sees_own_supervised(
        self, client: Client, encadrant_user, confirmed_application, stage_period
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=stage_period,
        )
        client.force_login(encadrant_user)
        response = client.get(f"/api/stages/grades/period/{stage_period.id}")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_student_cannot_list_period_grades(
        self, client: Client, student_user, stage_period
    ):
        client.force_login(student_user)
        response = client.get(f"/api/stages/grades/period/{stage_period.id}")
        assert response.status_code == 403


class TestCSVExport:
    """Tests for CSV export (12-7)."""

    def test_admin_can_export_csv(
        self, client: Client, admin_user, confirmed_application, stage_period
    ):
        StageGrade.objects.create(
            application=confirmed_application,
            stage_period=stage_period,
            academic_grade=Decimal("15.00"),
            company_grade=Decimal("17.00"),
            final_grade=Decimal("16.00"),
            status=StageGradeStatus.FINALIZED,
        )
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/export/{stage_period.id}/csv")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8"
        assert "attachment" in response["Content-Disposition"]
        content = response.content.decode("utf-8")
        assert "Etudiant Email" in content
        assert "student@example.com" in content
        assert "15.00" in content
        assert "17.00" in content

    def test_non_admin_cannot_export(
        self, client: Client, encadrant_user, stage_period
    ):
        client.force_login(encadrant_user)
        response = client.get(f"/api/stages/dashboard/export/{stage_period.id}/csv")
        assert response.status_code == 403

    def test_csv_has_correct_columns(
        self, client: Client, admin_user, confirmed_application, stage_period
    ):
        client.force_login(admin_user)
        response = client.get(f"/api/stages/dashboard/export/{stage_period.id}/csv")
        content = response.content.decode("utf-8")
        header = content.split("\n")[0].strip()
        expected_cols = [
            "Etudiant Email", "Nom", "Prenom", "Offre", "Entreprise",
            "Superviseur Entreprise", "Superviseur Academique",
            "Note Academique", "Note Entreprise", "Note Finale", "Statut",
        ]
        for col in expected_cols:
            assert col in header


class TestComputeFinalGrade:
    """Tests for the compute_final_grade model method."""

    def test_computes_average(self, confirmed_application, stage_period):
        grade = StageGrade.objects.create(
            application=confirmed_application,
            stage_period=stage_period,
            academic_grade=Decimal("14.00"),
            company_grade=Decimal("18.00"),
        )
        grade.compute_final_grade()
        assert grade.final_grade == Decimal("16.00")

    def test_none_when_missing_grade(self, confirmed_application, stage_period):
        grade = StageGrade.objects.create(
            application=confirmed_application,
            stage_period=stage_period,
            academic_grade=Decimal("14.00"),
        )
        grade.compute_final_grade()
        assert grade.final_grade is None
