"""
Tests for Stage Applications API.

Tests the full application workflow:
- Apply to offer (5.5)
- Multiple applications (5.6)
- View applications as externe/supervisor (5.7)
- Accept/reject applications (5.8)
- Confirm assignment (5.9)
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    PeriodStatus,
    StageApplication,
    StageOffer,
    StagePeriod,
)
from backend_django.users.models import User


@pytest.fixture
def student_user(db):
    """Create a student user."""
    user = User.objects.create_user(
        email="student@example.com",
        password="password123",
        first_name="Student",
        last_name="Test",
    )
    student_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(student_group)
    return user


@pytest.fixture
def student_user_2(db):
    """Create a second student user."""
    user = User.objects.create_user(
        email="student2@example.com",
        password="password123",
        first_name="Student2",
        last_name="Test",
    )
    student_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(student_group)
    return user


@pytest.fixture
def externe_user(db):
    """Create an externe (company supervisor) user."""
    user = User.objects.create_user(
        email="externe@company.com",
        password="password123",
        first_name="Externe",
        last_name="Supervisor",
    )
    externe_group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(externe_group)
    return user


@pytest.fixture
def encadrant_user(db):
    """Create an academic supervisor (encadrant) user."""
    user = User.objects.create_user(
        email="encadrant@university.com",
        password="password123",
        first_name="Encadrant",
        last_name="Academic",
    )
    encadrant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(encadrant_group)
    return user


@pytest.fixture
def admin_user(db):
    """Create an admin user (Respo Stage)."""
    user = User.objects.create_user(
        email="admin@example.com",
        password="password123",
        first_name="Admin",
        last_name="Respo",
        is_staff=True,
    )
    respo_stage_group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(respo_stage_group)
    return user


@pytest.fixture
def stage_period(db):
    """Create an open stage period."""
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
    """Create a validated stage offer."""
    return StageOffer.objects.create(
        stage_period=stage_period,
        title="Stage en Intelligence Artificielle",
        description="Un stage passionnant en IA avec de nombreuses opportunites d'apprentissage sur des projets concrets.",
        company_name="TechCorp",
        location="Paris",
        domain="IA/ML",
        prerequisites="Python, Machine Learning basics",
        supervisor=externe_user,
        max_students=2,
        status=OfferStatus.VALIDATED,
    )


@pytest.fixture
def validated_offer_2(db, stage_period, externe_user):
    """Create a second validated stage offer."""
    return StageOffer.objects.create(
        stage_period=stage_period,
        title="Stage en Developpement Web Full-Stack",
        description="Rejoignez notre equipe pour un stage en developpement web avec React et Django.",
        company_name="WebAgency",
        location="Lyon",
        domain="Web",
        prerequisites="JavaScript, React",
        supervisor=externe_user,
        max_students=1,
        status=OfferStatus.VALIDATED,
    )


class TestApplyToOffer:
    """Tests for applying to stage offers (5.5)."""

    def test_student_can_apply(self, client: Client, student_user, validated_offer):
        """Student can apply to a validated offer."""
        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences et aspirations professionnelles.",
                "cv_url": "https://example.com/cv.pdf",
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["student"]["email"] == student_user.email
        assert data["offer_id"] == str(validated_offer.id)

    def test_non_student_cannot_apply(self, client: Client, externe_user, validated_offer):
        """Non-student cannot apply to an offer."""
        client.force_login(externe_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences.",
            },
            content_type="application/json",
        )

        assert response.status_code == 403

    def test_cannot_apply_to_non_validated_offer(
        self, client: Client, student_user, stage_period, externe_user
    ):
        """Cannot apply to non-validated offer."""
        draft_offer = StageOffer.objects.create(
            stage_period=stage_period,
            title="Stage en cours de validation",
            description="Description du stage en cours de validation pour les equipes.",
            company_name="DraftCorp",
            domain="Test",
            supervisor=externe_user,
            status=OfferStatus.DRAFT,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{draft_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences.",
            },
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_cannot_apply_twice(self, client: Client, student_user, validated_offer):
        """Cannot apply to the same offer twice."""
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="First application",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences.",
            },
            content_type="application/json",
        )

        assert response.status_code == 409
        assert "deja postule" in response.json()["message"]

    def test_motivation_validation(self, client: Client, student_user, validated_offer):
        """Motivation must be at least 50 characters."""
        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Short motivation",
            },
            content_type="application/json",
        )

        assert response.status_code == 422


class TestMultipleApplications:
    """Tests for applying to multiple offers (5.6)."""

    def test_can_apply_to_multiple_offers(
        self, client: Client, student_user, validated_offer, validated_offer_2
    ):
        """Student can apply to multiple offers."""
        client.force_login(student_user)

        # Apply to first offer
        response1 = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences.",
            },
            content_type="application/json",
        )
        assert response1.status_code == 201

        # Apply to second offer
        response2 = client.post(
            f"/api/stages/offers/{validated_offer_2.id}/apply",
            data={
                "motivation": "Ce stage web correspond aussi a mes ambitions professionnelles et competences techniques.",
            },
            content_type="application/json",
        )
        assert response2.status_code == 201

        # Check both applications exist
        applications = StageApplication.objects.filter(student=student_user)
        assert applications.count() == 2

    def test_cannot_apply_after_confirmation(
        self, client: Client, student_user, validated_offer, validated_offer_2
    ):
        """Cannot apply to new offers after confirming one."""
        # Create a confirmed application
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Confirmed application",
            status=ApplicationStatus.CONFIRMED,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer_2.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce stage car il correspond parfaitement a mes competences.",
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "confirme" in response.json()["message"]


class TestViewApplications:
    """Tests for viewing applications (5.7)."""

    def test_supervisor_can_view_applications(
        self, client: Client, externe_user, student_user, validated_offer
    ):
        """Offer supervisor can view applications."""
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(externe_user)

        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["student"]["email"] == student_user.email

    def test_admin_can_view_applications(
        self, client: Client, admin_user, student_user, validated_offer
    ):
        """Admin can view any offer's applications."""
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(admin_user)

        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications")

        assert response.status_code == 200

    def test_student_cannot_view_other_applications(
        self, client: Client, student_user, student_user_2, validated_offer
    ):
        """Student cannot view other students' applications."""
        StageApplication.objects.create(
            student=student_user_2,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications")

        assert response.status_code == 403

    def test_student_can_view_own_applications(
        self, client: Client, student_user, validated_offer
    ):
        """Student can view their own applications."""
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.get("/api/stages/applications/my-applications")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1


class TestAcceptRejectApplications:
    """Tests for accepting/rejecting applications (5.8)."""

    def test_supervisor_can_accept_application(
        self, client: Client, externe_user, student_user, validated_offer
    ):
        """Supervisor can accept an application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(externe_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/accept"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["decision_by"]["email"] == externe_user.email

    def test_supervisor_can_reject_application(
        self, client: Client, externe_user, student_user, validated_offer
    ):
        """Supervisor can reject an application with reason."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(externe_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/reject",
            data={
                "reason": "Le profil ne correspond pas aux competences recherchees pour ce stage.",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert "competences" in data["rejection_reason"]

    def test_cannot_accept_more_than_max_students(
        self, client: Client, externe_user, student_user, student_user_2, validated_offer_2
    ):
        """Cannot accept more applications than max_students."""
        # max_students is 1 for validated_offer_2
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer_2,
            motivation="First application",
            status=ApplicationStatus.ACCEPTED,
        )
        application2 = StageApplication.objects.create(
            student=student_user_2,
            offer=validated_offer_2,
            motivation="Second application",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(externe_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer_2.id}/applications/{application2.id}/accept"
        )

        assert response.status_code == 400
        assert "maximum" in response.json()["message"]

    def test_student_cannot_accept_application(
        self, client: Client, student_user, validated_offer
    ):
        """Student cannot accept their own application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/accept"
        )

        assert response.status_code == 403


class TestConfirmApplication:
    """Tests for confirming applications (5.9)."""

    def test_student_can_confirm_accepted_application(
        self, client: Client, student_user, validated_offer
    ):
        """Student can confirm an accepted application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.ACCEPTED,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/confirm",
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_cannot_confirm_pending_application(
        self, client: Client, student_user, validated_offer
    ):
        """Cannot confirm a pending application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/confirm",
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_confirmation_withdraws_other_applications(
        self, client: Client, student_user, validated_offer, validated_offer_2
    ):
        """Confirming an application auto-withdraws other pending applications."""
        # Create two pending applications
        app1 = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="First application",
            status=ApplicationStatus.ACCEPTED,
        )
        app2 = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer_2,
            motivation="Second application",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{app1.id}/confirm",
            content_type="application/json",
        )

        assert response.status_code == 200

        # Check other application was withdrawn
        app2.refresh_from_db()
        assert app2.status == ApplicationStatus.WITHDRAWN

    def test_confirm_with_academic_supervisor(
        self, client: Client, student_user, encadrant_user, validated_offer
    ):
        """Can assign academic supervisor during confirmation."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.ACCEPTED,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{application.id}/confirm",
            data={
                "academic_supervisor_id": str(encadrant_user.id),
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["academic_supervisor"]["email"] == encadrant_user.email


class TestWithdrawApplication:
    """Tests for withdrawing applications."""

    def test_student_can_withdraw_pending_application(
        self, client: Client, student_user, validated_offer
    ):
        """Student can withdraw a pending application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/applications/{application.id}/withdraw"
        )

        assert response.status_code == 200
        application.refresh_from_db()
        assert application.status == ApplicationStatus.WITHDRAWN

    def test_cannot_withdraw_accepted_application(
        self, client: Client, student_user, validated_offer
    ):
        """Cannot withdraw an accepted application."""
        application = StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Test motivation",
            status=ApplicationStatus.ACCEPTED,
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/stages/applications/{application.id}/withdraw"
        )

        assert response.status_code == 400


class TestApplicationCounts:
    """Tests for application count endpoint."""

    def test_supervisor_can_get_counts(
        self, client: Client, externe_user, student_user, student_user_2, validated_offer
    ):
        """Supervisor can get application counts."""
        StageApplication.objects.create(
            student=student_user,
            offer=validated_offer,
            motivation="Pending application",
            status=ApplicationStatus.PENDING,
        )
        StageApplication.objects.create(
            student=student_user_2,
            offer=validated_offer,
            motivation="Accepted application",
            status=ApplicationStatus.ACCEPTED,
        )

        client.force_login(externe_user)

        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications/count")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["pending"] == 1
        assert data["accepted"] == 1
        assert data["rejected"] == 0
        assert data["confirmed"] == 0


class TestFullWorkflowE2E:
    """End-to-end test of the complete application workflow."""

    def test_complete_application_workflow(
        self,
        client: Client,
        student_user,
        externe_user,
        validated_offer,
        validated_offer_2,
    ):
        """
        E2E test: Complete workflow from application to confirmation.

        Steps:
        1. Student applies to two offers
        2. Supervisor views applications
        3. Supervisor accepts one application
        4. Student confirms the accepted application
        5. Other pending application is auto-withdrawn
        """
        # Step 1: Student applies to both offers
        client.force_login(student_user)

        response1 = client.post(
            f"/api/stages/offers/{validated_offer.id}/apply",
            data={
                "motivation": "Je suis tres motive pour ce premier stage car il correspond a mes competences.",
                "cv_url": "https://example.com/cv.pdf",
            },
            content_type="application/json",
        )
        assert response1.status_code == 201
        app1_id = response1.json()["id"]
        assert response1.json()["status"] == "pending"

        response2 = client.post(
            f"/api/stages/offers/{validated_offer_2.id}/apply",
            data={
                "motivation": "Ce deuxieme stage correspond egalement a mes aspirations professionnelles.",
            },
            content_type="application/json",
        )
        assert response2.status_code == 201
        app2_id = response2.json()["id"]

        # Step 2: Supervisor views applications
        client.force_login(externe_user)

        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["student"]["email"] == student_user.email

        # Check counts
        response = client.get(f"/api/stages/offers/{validated_offer.id}/applications/count")
        assert response.status_code == 200
        assert response.json()["pending"] == 1

        # Step 3: Supervisor accepts the first application
        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{app1_id}/accept"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        assert response.json()["decision_by"]["email"] == externe_user.email

        # Step 4: Student confirms the accepted application
        client.force_login(student_user)

        response = client.post(
            f"/api/stages/offers/{validated_offer.id}/applications/{app1_id}/confirm",
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["confirmed_at"] is not None

        # Step 5: Verify the other application was auto-withdrawn
        app2 = StageApplication.objects.get(id=app2_id)
        assert app2.status == ApplicationStatus.WITHDRAWN

        # Verify final state
        app1 = StageApplication.objects.get(id=app1_id)
        assert app1.status == ApplicationStatus.CONFIRMED

        # Student cannot apply to new offers in same period (already confirmed)
        # Create a third offer to test this
        from backend_django.stages.models import StageOffer, OfferStatus
        offer3 = StageOffer.objects.create(
            stage_period=validated_offer.stage_period,
            title="Third Stage Offer for Testing Application Block",
            description="Cette offre sert a tester le blocage des candidatures apres confirmation.",
            company_name="ThirdCorp",
            domain="Test",
            supervisor=externe_user,
            status=OfferStatus.VALIDATED,
        )

        response = client.post(
            f"/api/stages/offers/{offer3.id}/apply",
            data={
                "motivation": "Je voudrais postuler a cette offre meme si j'ai deja confirme.",
            },
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "confirme" in response.json()["message"]
