"""
Tests for TER Grading and Peer Review API.

Tests group grading, individual grading opt-in, and anonymous peer reviews.
"""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    GradeStatus,
    PeerReview,
    PeerReviewSession,
    PeriodStatus,
    TERGrade,
    TERIndividualGrade,
    TERPeriod,
    TERSubject,
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
def student_user_3(db):
    """Create a third student user."""
    user = User.objects.create_user(
        email="student3@example.com",
        password="password123",
        first_name="Student3",
        last_name="Test",
    )
    student_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(student_group)
    return user


@pytest.fixture
def professor_user(db):
    """Create a professor (encadrant) user."""
    user = User.objects.create_user(
        email="professor@example.com",
        password="password123",
        first_name="Professor",
        last_name="Test",
    )
    encadrant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
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
    respo_ter_group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
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
        project_start=today - timedelta(days=10),  # Project already started
        project_end=today + timedelta(days=60),    # Project ends in the future
        min_group_size=2,
        max_group_size=4,
    )


@pytest.fixture
def subject(db, ter_period, professor_user):
    """Create a TER subject."""
    return TERSubject.objects.create(
        ter_period=ter_period,
        title="Test Subject",
        description="Test description",
        domain="Test",
        professor=professor_user,
        supervisor=professor_user,
    )


@pytest.fixture
def formed_group(db, ter_period, student_user, student_user_2, student_user_3, subject):
    """Create a formed group with members and assigned subject."""
    group = Group.objects.create(
        name="Test Group",
        ter_period=ter_period,
        leader=student_user,
        status=GroupStatus.FORME,
        assigned_subject=subject,
    )
    group.members.add(student_user, student_user_2, student_user_3)
    return group


class TestGetGroupGrade:
    """Tests for getting group grades."""

    def test_encadrant_can_get_grade(self, client: Client, professor_user, formed_group):
        """Encadrant can get the group grade."""
        client.force_login(professor_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["group_id"] == str(formed_group.id)
        assert data["status"] == "draft"

    def test_group_member_can_get_grade(self, client: Client, student_user, formed_group):
        """Group member can view the grade."""
        client.force_login(student_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}")

        assert response.status_code == 200

    def test_non_member_cannot_get_grade(self, client: Client, formed_group):
        """Non-member cannot view the grade."""
        other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
        )
        client.force_login(other_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}")

        assert response.status_code == 403

    def test_admin_can_get_any_grade(self, client: Client, admin_user, formed_group):
        """Admin can view any group's grade."""
        client.force_login(admin_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}")

        assert response.status_code == 200


class TestUpdateGroupGrade:
    """Tests for updating group grades."""

    def test_encadrant_can_enter_grade(self, client: Client, professor_user, formed_group):
        """Encadrant can enter a group grade."""
        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={
                "group_grade": "15.50",
                "group_grade_comment": "Good work!",
                "individual_grading_enabled": True,
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["group_grade"]) == Decimal("15.50")
        assert data["group_grade_comment"] == "Good work!"
        assert data["individual_grading_enabled"] is True
        assert data["status"] == "submitted"

    def test_grade_validation_min_max(self, client: Client, professor_user, formed_group):
        """Grade must be between 0 and 20."""
        client.force_login(professor_user)

        # Test grade > 20
        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={"group_grade": "21.00"},
            content_type="application/json",
        )
        assert response.status_code == 422

        # Test grade < 0
        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={"group_grade": "-1.00"},
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_student_cannot_update_grade(self, client: Client, student_user, formed_group):
        """Students cannot update grades."""
        client.force_login(student_user)

        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={"group_grade": "20.00"},
            content_type="application/json",
        )

        assert response.status_code == 403

    def test_update_creates_individual_grade_records(
        self, client: Client, professor_user, formed_group
    ):
        """Updating grade creates individual grade records for all members."""
        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={"group_grade": "14.00"},
            content_type="application/json",
        )

        assert response.status_code == 200

        # Check individual grade records were created
        grade = TERGrade.objects.get(group=formed_group)
        individual_grades = TERIndividualGrade.objects.filter(grade=grade)
        assert individual_grades.count() == 3  # 3 group members


class TestFinalizeGrade:
    """Tests for grade finalization (9.10)."""

    def test_admin_can_finalize_grade(
        self, client: Client, admin_user, professor_user, formed_group
    ):
        """Admin can finalize grades."""
        # First, enter a grade
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("15.00"),
            status=GradeStatus.SUBMITTED,
        )

        client.force_login(admin_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/finalize")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["finalized_at"] is not None

        # Verify grade is finalized
        grade.refresh_from_db()
        assert grade.status == GradeStatus.FINALIZED
        assert grade.finalized_by == admin_user

    def test_cannot_modify_after_finalization(
        self, client: Client, professor_user, formed_group, admin_user
    ):
        """Grade cannot be modified after finalization."""
        # Create and finalize grade
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("15.00"),
            status=GradeStatus.FINALIZED,
        )

        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/group/{formed_group.id}",
            data={"group_grade": "20.00"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "finalisées" in response.json()["message"]

    def test_cannot_finalize_without_grade(self, client: Client, admin_user, formed_group):
        """Cannot finalize without a group grade entered."""
        TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            status=GradeStatus.DRAFT,
        )

        client.force_login(admin_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/finalize")

        assert response.status_code == 400
        assert "note de groupe" in response.json()["message"]

    def test_encadrant_cannot_finalize(self, client: Client, professor_user, formed_group):
        """Only admin can finalize, not encadrant."""
        TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("15.00"),
            status=GradeStatus.SUBMITTED,
        )

        client.force_login(professor_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/finalize")

        assert response.status_code == 403


class TestIndividualGradingOptIn:
    """Tests for individual grading opt-in (9.2)."""

    def test_student_can_opt_in(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Student can opt-in for individual grading."""
        # Create grade with individual grading enabled
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        TERIndividualGrade.objects.create(grade=grade, student=student_user)

        client.force_login(student_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/opt-in")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["opted_in"] is True
        assert data["opted_in_at"] is not None

    def test_cannot_opt_in_when_disabled(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Cannot opt-in when individual grading is disabled."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=False,
            status=GradeStatus.SUBMITTED,
        )

        client.force_login(student_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/opt-in")

        assert response.status_code == 400
        assert "pas activée" in response.json()["message"]

    def test_cannot_opt_in_after_finalization(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Cannot opt-in after grade finalization."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.FINALIZED,
        )
        TERIndividualGrade.objects.create(grade=grade, student=student_user)

        client.force_login(student_user)

        response = client.post(f"/api/ter/grades/group/{formed_group.id}/opt-in")

        assert response.status_code == 400
        assert "finalisées" in response.json()["message"]


class TestIndividualGradeUpdate:
    """Tests for updating individual grades (9.1)."""

    def test_encadrant_can_update_individual_grade(
        self, client: Client, professor_user, student_user, formed_group
    ):
        """Encadrant can update individual grade for opted-in student."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=True,
        )

        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/individual/{individual_grade.id}",
            data={
                "individual_grade": "16.00",
                "individual_grade_comment": "Excellent participation",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["individual_grade"]) == Decimal("16.00")
        assert Decimal(data["final_grade"]) == Decimal("16.00")  # Individual grade used

    def test_cannot_update_if_not_opted_in(
        self, client: Client, professor_user, student_user, formed_group
    ):
        """Cannot update individual grade if student hasn't opted in."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=False,
        )

        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/individual/{individual_grade.id}",
            data={"individual_grade": "16.00"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "opté" in response.json()["message"]

    def test_cannot_update_if_grading_disabled(
        self, client: Client, professor_user, student_user, formed_group
    ):
        """Cannot update individual grade if individual grading is disabled."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=False,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=True,  # Even if opted_in
        )

        client.force_login(professor_user)

        response = client.put(
            f"/api/ter/grades/individual/{individual_grade.id}",
            data={"individual_grade": "16.00"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "pas activée" in response.json()["message"]


class TestFinalGradeCalculation:
    """Tests for final grade calculation (9.7)."""

    def test_final_grade_uses_group_grade_when_not_opted_in(
        self, professor_user, student_user, formed_group
    ):
        """Final grade equals group grade when student hasn't opted in."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=False,
        )

        individual_grade.compute_final_grade()

        assert individual_grade.final_grade == Decimal("14.00")

    def test_final_grade_uses_individual_grade_when_opted_in(
        self, professor_user, student_user, formed_group
    ):
        """Final grade equals individual grade when student opted in."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=True,
            individual_grade=Decimal("16.50"),
        )

        individual_grade.compute_final_grade()

        assert individual_grade.final_grade == Decimal("16.50")

    def test_final_grade_falls_back_to_group_when_no_individual(
        self, professor_user, student_user, formed_group
    ):
        """Final grade falls back to group grade if opted in but no individual grade set."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            individual_grading_enabled=True,
            status=GradeStatus.SUBMITTED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=True,
            individual_grade=None,  # No individual grade set yet
        )

        individual_grade.compute_final_grade()

        assert individual_grade.final_grade == Decimal("14.00")


class TestPeerReviewSession:
    """Tests for peer review session creation (9.4)."""

    def test_student_can_get_session(self, client: Client, student_user, formed_group):
        """Student can get/create a peer review session."""
        client.force_login(student_user)

        response = client.get(
            f"/api/ter/peer-reviews/session?period_id={formed_group.ter_period.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "ephemeral_token" in data
        assert data["group_id"] == str(formed_group.id)
        assert len(data["members_to_review"]) == 2  # Other 2 group members

    def test_session_excludes_self_from_reviewable(
        self, client: Client, student_user, formed_group
    ):
        """Student cannot see themselves in reviewable members."""
        client.force_login(student_user)

        response = client.get(
            f"/api/ter/peer-reviews/session?period_id={formed_group.ter_period.id}"
        )

        assert response.status_code == 200
        data = response.json()

        member_ids = [m["id"] for m in data["members_to_review"]]
        assert str(student_user.id) not in member_ids

    def test_session_tracks_already_reviewed(
        self, client: Client, student_user, student_user_2, formed_group
    ):
        """Session tracks which members have already been reviewed."""
        # Create session and a review
        session = PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )
        PeerReview.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            reviewer_token=str(session.ephemeral_token),
            reviewed_student=student_user_2,
            contribution_score=4,
            collaboration_score=4,
            technical_skill_score=4,
        )

        client.force_login(student_user)

        response = client.get(
            f"/api/ter/peer-reviews/session?period_id={formed_group.ter_period.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert str(student_user_2.id) in [str(uid) for uid in data["already_reviewed"]]


class TestPeerReviewSubmission:
    """Tests for peer review submission (9.5)."""

    def test_student_can_submit_review(
        self, client: Client, student_user, student_user_2, formed_group
    ):
        """Student can submit a peer review."""
        # Create session
        PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )

        client.force_login(student_user)

        response = client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user_2.id),
                "contribution_score": 4,
                "collaboration_score": 5,
                "technical_skill_score": 4,
                "comment": "Great teammate!",
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        assert response.json()["success"] is True

        # Verify review was created
        review = PeerReview.objects.get(reviewed_student=student_user_2)
        assert review.contribution_score == 4
        assert review.collaboration_score == 5
        assert review.technical_skill_score == 4
        assert review.comment == "Great teammate!"

    def test_cannot_review_self(self, client: Client, student_user, formed_group):
        """Student cannot review themselves."""
        PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )

        client.force_login(student_user)

        response = client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user.id),
                "contribution_score": 5,
                "collaboration_score": 5,
                "technical_skill_score": 5,
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "auto-évaluer" in response.json()["message"]

    def test_cannot_review_twice(
        self, client: Client, student_user, student_user_2, formed_group
    ):
        """Student cannot review the same person twice."""
        session = PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )
        # Create existing review
        PeerReview.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            reviewer_token=str(session.ephemeral_token),
            reviewed_student=student_user_2,
            contribution_score=4,
            collaboration_score=4,
            technical_skill_score=4,
        )

        client.force_login(student_user)

        response = client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user_2.id),
                "contribution_score": 5,
                "collaboration_score": 5,
                "technical_skill_score": 5,
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "déjà évalué" in response.json()["message"]

    def test_score_validation(
        self, client: Client, student_user, student_user_2, formed_group
    ):
        """Scores must be between 1 and 5."""
        PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )

        client.force_login(student_user)

        # Test score > 5
        response = client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user_2.id),
                "contribution_score": 6,
                "collaboration_score": 5,
                "technical_skill_score": 5,
            },
            content_type="application/json",
        )
        assert response.status_code == 422

        # Test score < 1
        response = client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user_2.id),
                "contribution_score": 0,
                "collaboration_score": 5,
                "technical_skill_score": 5,
            },
            content_type="application/json",
        )
        assert response.status_code == 422


class TestPeerReviewAnonymity:
    """Tests for peer review anonymity (ARCH-7, NFR-S7)."""

    def test_review_uses_token_not_user_id(
        self, client: Client, student_user, student_user_2, formed_group
    ):
        """Reviews store ephemeral token, not user ID."""
        session = PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )

        client.force_login(student_user)

        client.post(
            "/api/ter/peer-reviews/submit",
            data={
                "reviewed_student_id": str(student_user_2.id),
                "contribution_score": 4,
                "collaboration_score": 4,
                "technical_skill_score": 4,
            },
            content_type="application/json",
        )

        review = PeerReview.objects.get(reviewed_student=student_user_2)

        # Review should have token, not direct user reference
        assert review.reviewer_token == str(session.ephemeral_token)
        # PeerReview has no 'reviewer' FK, only reviewer_token

    def test_aggregated_reviews_hide_reviewer(
        self, client: Client, professor_user, student_user, student_user_2, student_user_3, formed_group
    ):
        """Aggregated reviews don't reveal who reviewed whom."""
        session1 = PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )
        session2 = PeerReviewSession.objects.create(
            ter_period=formed_group.ter_period,
            student=student_user_3,
            group=formed_group,
            expires_at=formed_group.ter_period.project_end + timedelta(days=7),
        )

        # Two different students review student_user_2
        PeerReview.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            reviewer_token=str(session1.ephemeral_token),
            reviewed_student=student_user_2,
            contribution_score=4,
            collaboration_score=4,
            technical_skill_score=4,
            comment="Good work",
        )
        PeerReview.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            reviewer_token=str(session2.ephemeral_token),
            reviewed_student=student_user_2,
            contribution_score=5,
            collaboration_score=5,
            technical_skill_score=5,
            comment="Excellent",
        )

        client.force_login(professor_user)

        response = client.get(f"/api/ter/peer-reviews/group/{formed_group.id}/aggregate")

        assert response.status_code == 200
        data = response.json()

        # Find student_user_2's aggregate
        student2_data = next(d for d in data if d["student_id"] == str(student_user_2.id))

        # Should have aggregate scores
        assert student2_data["review_count"] == 2
        assert student2_data["avg_contribution"] == 4.5
        assert student2_data["avg_collaboration"] == 4.5
        assert student2_data["avg_technical_skill"] == 4.5

        # Comments are aggregated but anonymous
        assert len(student2_data["comments"]) == 2


class TestPeerReviewAggregateAccess:
    """Tests for accessing aggregated peer reviews."""

    def test_encadrant_can_view_aggregate(
        self, client: Client, professor_user, student_user, formed_group
    ):
        """Encadrant can view aggregated reviews."""
        client.force_login(professor_user)

        response = client.get(f"/api/ter/peer-reviews/group/{formed_group.id}/aggregate")

        assert response.status_code == 200

    def test_student_cannot_view_aggregate(
        self, client: Client, student_user, formed_group
    ):
        """Students cannot view aggregated reviews."""
        client.force_login(student_user)

        response = client.get(f"/api/ter/peer-reviews/group/{formed_group.id}/aggregate")

        assert response.status_code == 403

    def test_admin_can_view_aggregate(
        self, client: Client, admin_user, formed_group
    ):
        """Admin can view aggregated reviews."""
        client.force_login(admin_user)

        response = client.get(f"/api/ter/peer-reviews/group/{formed_group.id}/aggregate")

        assert response.status_code == 200


class TestGetMyGrade:
    """Tests for student viewing their own grade."""

    def test_student_can_view_own_grade_after_finalization(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Student can see their grade after finalization."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.50"),
            status=GradeStatus.FINALIZED,
        )
        individual_grade = TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            final_grade=Decimal("14.50"),
        )

        client.force_login(student_user)

        response = client.get(
            f"/api/ter/grades/my-grade?period_id={formed_group.ter_period.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["final_grade"]) == Decimal("14.50")

    def test_student_cannot_see_grade_before_finalization(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Student cannot see detailed grade before finalization."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.50"),
            status=GradeStatus.SUBMITTED,  # Not finalized
        )
        TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            individual_grade=Decimal("16.00"),
            final_grade=Decimal("16.00"),
        )

        client.force_login(student_user)

        response = client.get(
            f"/api/ter/grades/my-grade?period_id={formed_group.ter_period.id}"
        )

        assert response.status_code == 200
        data = response.json()
        # Individual grade and final grade should be hidden
        assert data["individual_grade"] is None
        assert data["final_grade"] is None


class TestListIndividualGrades:
    """Tests for listing individual grades."""

    def test_encadrant_can_list_individual_grades(
        self, client: Client, professor_user, student_user, student_user_2, formed_group
    ):
        """Encadrant can list all individual grades for a group."""
        grade = TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            status=GradeStatus.SUBMITTED,
        )
        TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user,
            opted_in=True,
            individual_grade=Decimal("15.00"),
        )
        TERIndividualGrade.objects.create(
            grade=grade,
            student=student_user_2,
            opted_in=False,
        )

        client.force_login(professor_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}/individual")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_student_cannot_list_individual_grades(
        self, client: Client, student_user, professor_user, formed_group
    ):
        """Students cannot list all individual grades."""
        TERGrade.objects.create(
            ter_period=formed_group.ter_period,
            group=formed_group,
            graded_by=professor_user,
            group_grade=Decimal("14.00"),
            status=GradeStatus.SUBMITTED,
        )

        client.force_login(student_user)

        response = client.get(f"/api/ter/grades/group/{formed_group.id}/individual")

        assert response.status_code == 403
