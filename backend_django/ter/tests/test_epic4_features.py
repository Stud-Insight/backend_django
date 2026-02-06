"""
Tests for Epic 4 features:
- 4.3: Prevent Ranking After Deadline
- 4.8: View Assignment Statistics
- 4.9: Prevent Manual Assignment Modification (reason required)
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    BalancingOperation,
    PeriodStatus,
    SubjectStatus,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.users.models import User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def respo_ter_role(db):
    """Create the Respo TER role."""
    role, _ = DjangoGroup.objects.get_or_create(name="Respo TER")
    return role


@pytest.fixture
def etudiant_role(db):
    """Create the Étudiant role."""
    role, _ = DjangoGroup.objects.get_or_create(name="Étudiant")
    return role


@pytest.fixture
def respo_ter(db, respo_ter_role):
    """Create a Respo TER user."""
    user = User.objects.create_user(
        email="respo@example.com",
        password="testpass123",
        first_name="Respo",
        last_name="TER",
    )
    user.groups.add(respo_ter_role)
    return user


@pytest.fixture
def student(db, etudiant_role):
    """Create a student user."""
    user = User.objects.create_user(
        email="student@example.com",
        password="testpass123",
        first_name="Student",
        last_name="One",
    )
    user.groups.add(etudiant_role)
    return user


@pytest.fixture
def student2(db, etudiant_role):
    """Create a second student user."""
    user = User.objects.create_user(
        email="student2@example.com",
        password="testpass123",
        first_name="Student",
        last_name="Two",
    )
    user.groups.add(etudiant_role)
    return user


@pytest.fixture
def open_period(db):
    """Create an open TER period with future deadlines."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Open Period",
        academic_year="2025-2026",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=30),
        group_formation_end=today - timedelta(days=10),
        subject_selection_start=today - timedelta(days=9),
        subject_selection_end=today + timedelta(days=30),  # Future deadline
        assignment_date=today + timedelta(days=35),
        project_start=today + timedelta(days=40),
        project_end=today + timedelta(days=120),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def expired_period(db):
    """Create a TER period with expired ranking deadline."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Expired Period",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=90),
        group_formation_end=today - timedelta(days=60),
        subject_selection_start=today - timedelta(days=59),
        subject_selection_end=today - timedelta(days=1),  # Past deadline
        assignment_date=today + timedelta(days=5),
        project_start=today + timedelta(days=10),
        project_end=today + timedelta(days=90),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def formed_group(db, open_period, student):
    """Create a formed group with a leader."""
    group = Group.objects.create(
        name="Test Group",
        leader=student,
        project_type="TER",
        ter_period=open_period,
        status=GroupStatus.FORME,
    )
    group.members.add(student)
    return group


@pytest.fixture
def formed_group_expired(db, expired_period, student):
    """Create a formed group in an expired period."""
    group = Group.objects.create(
        name="Expired Group",
        leader=student,
        project_type="TER",
        ter_period=expired_period,
        status=GroupStatus.FORME,
    )
    group.members.add(student)
    return group


@pytest.fixture
def validated_subjects(db, open_period, respo_ter):
    """Create multiple validated subjects."""
    subjects = []
    for i in range(5):
        subject = TERSubject.objects.create(
            ter_period=open_period,
            title=f"Subject {i+1}",
            description=f"Description for subject {i+1}",
            domain="IA/ML",
            professor=respo_ter,
            status=SubjectStatus.VALIDATED,
            max_groups=2,
        )
        subjects.append(subject)
    return subjects


@pytest.fixture
def validated_subjects_expired(db, expired_period, respo_ter):
    """Create validated subjects for expired period."""
    subjects = []
    for i in range(3):
        subject = TERSubject.objects.create(
            ter_period=expired_period,
            title=f"Expired Subject {i+1}",
            description=f"Description for expired subject {i+1}",
            domain="Web",
            professor=respo_ter,
            status=SubjectStatus.VALIDATED,
            max_groups=1,
        )
        subjects.append(subject)
    return subjects


# ============================================================================
# 4.3: Prevent Ranking After Deadline Tests
# ============================================================================


class TestPreventRankingAfterDeadline:
    """Tests for story 4.3: Prevent ranking submission after deadline."""

    def test_submit_ranking_before_deadline_succeeds(
        self, client, student, formed_group, validated_subjects
    ):
        """Groups can submit rankings before the deadline."""
        client.login(email=student.email, password="testpass123")

        rankings_data = {
            "rankings": [
                {"subject_id": str(s.id), "rank": i + 1}
                for i, s in enumerate(validated_subjects)
            ]
        }

        response = client.post(
            f"/api/ter/rankings/{formed_group.id}",
            data=rankings_data,
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["rankings"]) == len(validated_subjects)

    def test_submit_ranking_after_deadline_fails(
        self, client, student, formed_group_expired, validated_subjects_expired
    ):
        """Groups cannot submit rankings after the deadline."""
        client.login(email=student.email, password="testpass123")

        rankings_data = {
            "rankings": [
                {"subject_id": str(s.id), "rank": i + 1}
                for i, s in enumerate(validated_subjects_expired)
            ]
        }

        response = client.post(
            f"/api/ter/rankings/{formed_group_expired.id}",
            data=rankings_data,
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.json()
        assert "terminee" in data["message"].lower()

    def test_update_ranking_after_deadline_fails(
        self, client, student, formed_group_expired, validated_subjects_expired
    ):
        """Groups cannot update rankings after the deadline."""
        # First, create rankings before the deadline (bypass validation)
        for i, subject in enumerate(validated_subjects_expired):
            TERRanking.objects.create(
                group=formed_group_expired,
                subject=subject,
                rank=i + 1,
            )

        client.login(email=student.email, password="testpass123")

        # Try to update rankings - should fail
        rankings_data = {
            "rankings": [
                {"subject_id": str(s.id), "rank": len(validated_subjects_expired) - i}
                for i, s in enumerate(validated_subjects_expired)
            ]
        }

        response = client.post(
            f"/api/ter/rankings/{formed_group_expired.id}",
            data=rankings_data,
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "terminee" in response.json()["message"].lower()

    def test_deadline_message_includes_date(
        self, client, student, formed_group_expired, validated_subjects_expired
    ):
        """Error message includes the deadline date."""
        client.login(email=student.email, password="testpass123")

        rankings_data = {
            "rankings": [
                {"subject_id": str(s.id), "rank": i + 1}
                for i, s in enumerate(validated_subjects_expired)
            ]
        }

        response = client.post(
            f"/api/ter/rankings/{formed_group_expired.id}",
            data=rankings_data,
            content_type="application/json",
        )

        assert response.status_code == 400
        message = response.json()["message"]
        # Should contain date format DD/MM/YYYY
        assert "/" in message


# ============================================================================
# 4.8: View Assignment Statistics Tests
# ============================================================================


class TestAssignmentStatistics:
    """Tests for story 4.8: View assignment statistics."""

    def test_assignment_stats_requires_auth(self, client, open_period):
        """Endpoint requires authentication."""
        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")
        # Django Ninja returns 403 for unauthenticated requests with IsAuthenticated permission
        assert response.status_code in [401, 403]

    def test_assignment_stats_requires_ter_admin(self, client, student, open_period):
        """Only Respo TER can view assignment statistics."""
        client.login(email=student.email, password="testpass123")

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")
        assert response.status_code == 403

    def test_assignment_stats_empty_period(self, client, respo_ter, open_period):
        """Statistics for period with no assignments."""
        client.login(email=respo_ter.email, password="testpass123")

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] == 0
        assert data["assigned_groups"] == 0
        assert data["unassigned_groups"] == 0
        assert data["choice_distribution"] == []
        assert data["average_choice_rank"] is None

    def test_assignment_stats_with_assignments(
        self, client, respo_ter, open_period, validated_subjects, student, student2
    ):
        """Statistics with actual assignments."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create groups with different assignment qualities
        group1 = Group.objects.create(
            name="Group 1",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.CLOTURE,
            assigned_subject=validated_subjects[0],
        )
        group1.members.add(student)

        group2 = Group.objects.create(
            name="Group 2",
            leader=student2,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.CLOTURE,
            assigned_subject=validated_subjects[1],
        )
        group2.members.add(student2)

        # Create rankings (group1 got their 1st choice, group2 got their 3rd)
        for i, subject in enumerate(validated_subjects):
            TERRanking.objects.create(group=group1, subject=subject, rank=i + 1)
            # Group 2's ranking is reversed
            TERRanking.objects.create(
                group=group2, subject=subject, rank=len(validated_subjects) - i
            )

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")

        assert response.status_code == 200
        data = response.json()

        assert data["total_groups"] == 2
        assert data["assigned_groups"] == 2
        assert data["unassigned_groups"] == 0
        assert data["groups_with_first_choice"] == 1
        assert len(data["choice_distribution"]) > 0
        assert data["average_choice_rank"] is not None

    def test_assignment_stats_shows_unassigned(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Statistics show unassigned groups and subjects."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create a group without assignment
        group = Group.objects.create(
            name="Unassigned Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")

        assert response.status_code == 200
        data = response.json()

        assert data["total_groups"] == 1
        assert data["unassigned_groups"] == 1
        assert data["total_subjects"] == len(validated_subjects)
        assert data["unassigned_subjects"] == len(validated_subjects)
        assert len(data["unassigned_groups_list"]) == 1
        assert len(data["unassigned_subjects_list"]) == len(validated_subjects)

    def test_assignment_stats_satisfaction_metrics(
        self, client, respo_ter, open_period, validated_subjects
    ):
        """Test satisfaction percentage calculations."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create 10 groups with varying assignment quality
        users = []
        groups = []
        for i in range(10):
            user = User.objects.create_user(
                email=f"testuser{i}@example.com",
                password="testpass123",
                first_name=f"User{i}",
            )
            users.append(user)

            assigned_idx = min(i % 5, len(validated_subjects) - 1)
            group = Group.objects.create(
                name=f"Test Group {i}",
                leader=user,
                project_type="TER",
                ter_period=open_period,
                status=GroupStatus.CLOTURE,
                assigned_subject=validated_subjects[assigned_idx],
            )
            group.members.add(user)
            groups.append(group)

            # Create rankings where each group gets different choice rank
            for j, subject in enumerate(validated_subjects):
                rank = ((j + i) % len(validated_subjects)) + 1
                TERRanking.objects.create(group=group, subject=subject, rank=rank)

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")

        assert response.status_code == 200
        data = response.json()

        assert data["assigned_groups"] == 10
        assert 0 <= data["groups_with_first_choice_percentage"] <= 100
        assert 0 <= data["groups_with_top_3_choice_percentage"] <= 100
        assert data["average_choice_rank"] >= 1


# ============================================================================
# 4.9: Prevent Manual Assignment Modification Tests
# ============================================================================


class TestPreventManualAssignmentModification:
    """Tests for story 4.9: Require justification for admin overrides."""

    def test_force_assign_requires_reason(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Force assign must include a justification."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create a formed group
        group = Group.objects.create(
            name="Test Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        # Try to force assign without reason
        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(validated_subjects[0].id),
                "close_group": True,
                "reason": "",  # Empty reason
            },
            content_type="application/json",
        )

        assert response.status_code == 422  # Validation error
        errors = response.json()
        assert "detail" in errors or "message" in errors

    def test_force_assign_with_reason_succeeds(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Force assign with justification succeeds."""
        client.login(email=respo_ter.email, password="testpass123")

        group = Group.objects.create(
            name="Test Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(validated_subjects[0].id),
                "close_group": True,
                "reason": "Cas exceptionnel: etudiant RQTH necessitant ce sujet specifique",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify audit log was created
        operation = BalancingOperation.objects.filter(
            ter_period=open_period,
            operation_type="force_assign",
        ).first()
        assert operation is not None
        assert "RQTH" in operation.reason

    def test_revert_assignment_requires_reason(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Revert assignment must include a justification."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create an assigned group
        group = Group.objects.create(
            name="Assigned Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.CLOTURE,
            assigned_subject=validated_subjects[0],
        )
        group.members.add(student)

        # Try to revert without reason
        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/{group.id}/revert-assignment",
            data={
                "reopen_group": True,
                "reason": "",  # Empty reason
            },
            content_type="application/json",
        )

        assert response.status_code == 422  # Validation error

    def test_revert_assignment_with_reason_succeeds(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Revert assignment with justification succeeds."""
        client.login(email=respo_ter.email, password="testpass123")

        group = Group.objects.create(
            name="Assigned Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.CLOTURE,
            assigned_subject=validated_subjects[0],
        )
        group.members.add(student)

        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/{group.id}/revert-assignment",
            data={
                "reopen_group": True,
                "reason": "Erreur d'affectation detectee: le groupe avait mal compris le sujet",
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify audit log
        operation = BalancingOperation.objects.filter(
            ter_period=open_period,
            operation_type="revert_assignment",
        ).first()
        assert operation is not None
        assert "Erreur" in operation.reason

    def test_force_assign_only_for_ter_admin(
        self, client, student, open_period, validated_subjects
    ):
        """Regular students cannot use force assign."""
        client.login(email=student.email, password="testpass123")

        group = Group.objects.create(
            name="Test Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(validated_subjects[0].id),
                "reason": "Je veux ce sujet",
            },
            content_type="application/json",
        )

        assert response.status_code == 403

    def test_audit_log_contains_user_info(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Audit log records who performed the operation."""
        client.login(email=respo_ter.email, password="testpass123")

        group = Group.objects.create(
            name="Test Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        client.post(
            f"/api/ter/periods/{open_period.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(validated_subjects[0].id),
                "reason": "Test audit log",
            },
            content_type="application/json",
        )

        operation = BalancingOperation.objects.filter(
            ter_period=open_period,
            operation_type="force_assign",
        ).first()

        assert operation.performed_by == respo_ter
        assert operation.is_automatic is False


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestEdgeCases:
    """Edge case tests for Epic 4 features."""

    def test_ranking_on_exact_deadline_date(self, client, student, respo_ter):
        """Test ranking submission on the exact deadline date."""
        today = date.today()
        period = TERPeriod.objects.create(
            name="Deadline Today Period",
            academic_year="2025-2026",
            status=PeriodStatus.OPEN,
            group_formation_start=today - timedelta(days=30),
            group_formation_end=today - timedelta(days=10),
            subject_selection_start=today - timedelta(days=9),
            subject_selection_end=today,  # Exactly today
            assignment_date=today + timedelta(days=5),
            project_start=today + timedelta(days=10),
            project_end=today + timedelta(days=90),
        )

        subject = TERSubject.objects.create(
            ter_period=period,
            title="Test Subject",
            description="Test",
            domain="Test",
            professor=respo_ter,
            status=SubjectStatus.VALIDATED,
        )

        group = Group.objects.create(
            name="Test Group",
            leader=student,
            project_type="TER",
            ter_period=period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        client.login(email=student.email, password="testpass123")

        # On the deadline date, should still work (deadline is end of day)
        response = client.post(
            f"/api/ter/rankings/{group.id}",
            data={
                "rankings": [{"subject_id": str(subject.id), "rank": 1}]
            },
            content_type="application/json",
        )

        assert response.status_code == 200

    def test_assignment_stats_with_no_rankings(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Statistics when groups have assignments but no rankings recorded."""
        client.login(email=respo_ter.email, password="testpass123")

        # Create assigned group without rankings
        group = Group.objects.create(
            name="No Rankings Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.CLOTURE,
            assigned_subject=validated_subjects[0],
        )
        group.members.add(student)

        response = client.get(f"/api/ter/periods/{open_period.id}/assignment-statistics")

        assert response.status_code == 200
        data = response.json()

        # Group is assigned but has no rankings to calculate satisfaction
        assert data["assigned_groups"] == 1
        # Average should be None or based only on groups with rankings
        assert data["choice_distribution"] == []

    def test_force_assign_logs_all_details(
        self, client, respo_ter, open_period, validated_subjects, student
    ):
        """Force assign creates comprehensive audit log."""
        client.login(email=respo_ter.email, password="testpass123")

        group = Group.objects.create(
            name="Detailed Log Group",
            leader=student,
            project_type="TER",
            ter_period=open_period,
            status=GroupStatus.FORME,
        )
        group.members.add(student)

        response = client.post(
            f"/api/ter/periods/{open_period.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(validated_subjects[0].id),
                "close_group": True,
                "reason": "Detailed test reason",
            },
            content_type="application/json",
        )

        assert response.status_code == 200

        operation = BalancingOperation.objects.get(
            ter_period=open_period,
            operation_type="force_assign",
        )

        # Check all details are logged
        assert "group_id" in operation.details
        assert "group_name" in operation.details
        assert "subject_id" in operation.details
        assert "subject_title" in operation.details
        assert operation.details["closed_group"] is True

    def test_assignment_stats_period_not_found(self, client, respo_ter):
        """Statistics endpoint returns 404 for non-existent period."""
        client.login(email=respo_ter.email, password="testpass123")

        fake_id = uuid4()
        response = client.get(f"/api/ter/periods/{fake_id}/assignment-statistics")

        assert response.status_code == 404
