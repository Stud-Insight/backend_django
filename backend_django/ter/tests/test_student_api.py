"""
Tests for TER Student API - GET /ter/my endpoint.

Tests the endpoint that returns the complete TER context for a connected student.
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


@pytest.fixture
def student_user(db):
    """Create a student user."""
    return User.objects.create_user(
        email="student@example.com",
        password="password123",
        first_name="Jean",
        last_name="Etudiant",
    )


@pytest.fixture
def another_student(db):
    """Create another student user."""
    return User.objects.create_user(
        email="student2@example.com",
        password="password123",
        first_name="Marie",
        last_name="Etudiante",
    )


@pytest.fixture
def encadrant_user(db):
    """Create an encadrant (professor) user."""
    user = User.objects.create_user(
        email="prof@example.com",
        password="password123",
        first_name="Prof",
        last_name="Dupont",
    )
    encadrant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(encadrant_group)
    return user


@pytest.fixture
def open_ter_period(db):
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
def closed_ter_period(db):
    """Create a closed TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2023-2024 S2",
        academic_year="2023-2024",
        status=PeriodStatus.CLOSED,
        group_formation_start=today - timedelta(days=200),
        group_formation_end=today - timedelta(days=170),
        subject_selection_start=today - timedelta(days=185),
        subject_selection_end=today - timedelta(days=155),
        assignment_date=today - timedelta(days=150),
        project_start=today - timedelta(days=140),
        project_end=today - timedelta(days=50),
        min_group_size=2,
        max_group_size=4,
    )


@pytest.fixture
def validated_subject(db, open_ter_period, encadrant_user):
    """Create a validated TER subject."""
    return TERSubject.objects.create(
        ter_period=open_ter_period,
        title="Sujet de recherche valide",
        description="Description detaillee du sujet de recherche qui fait plus de 50 caracteres.",
        domain="IA/ML",
        professor=encadrant_user,
        status=SubjectStatus.VALIDATED,
        max_groups=2,
    )


class TestMyTERNoEnrollment:
    """Tests for students not enrolled in any TER period."""

    def test_my_ter_no_period_when_not_enrolled(self, client: Client, student_user, open_ter_period):
        """Student not enrolled in any period gets no_period status."""
        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_period"
        assert data["ter_period"] is None
        assert data["group"] is None
        assert data["subject"] is None

    def test_my_ter_unauthenticated_returns_403(self, db, client: Client):
        """Unauthenticated request returns 403 Forbidden."""
        response = client.get("/api/ter/my")

        assert response.status_code == 403


class TestMyTERNoGroup:
    """Tests for students enrolled but without a group."""

    def test_my_ter_no_group_when_enrolled_but_no_group(
        self, client: Client, student_user, open_ter_period
    ):
        """Student enrolled but without a group gets no_group status."""
        # Enroll student in period
        open_ter_period.enrolled_students.add(student_user)

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_group"
        assert data["ter_period"] is not None
        assert data["ter_period"]["id"] == str(open_ter_period.id)
        assert data["ter_period"]["name"] == "TER 2024-2025 S1"
        assert data["group"] is None
        assert data["subject"] is None


class TestMyTERGroupForming:
    """Tests for students in an open (forming) group."""

    def test_my_ter_group_forming(
        self, client: Client, student_user, open_ter_period
    ):
        """Student in an open group gets group_forming status."""
        # Enroll student
        open_ter_period.enrolled_students.add(student_user)

        # Create open group
        group = Group.objects.create(
            name="Groupe Test",
            leader=student_user,
            project_type="TER",
            ter_period=open_ter_period,
        )
        group.members.add(student_user)

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "group_forming"
        assert data["ter_period"]["id"] == str(open_ter_period.id)
        assert data["group"]["id"] == str(group.id)
        assert data["group"]["name"] == "Groupe Test"
        assert data["group"]["status"] == GroupStatus.OUVERT
        assert data["subject"] is None


class TestMyTERGroupFormed:
    """Tests for students in a formed group without subject."""

    def test_my_ter_group_formed(
        self, client: Client, student_user, another_student, open_ter_period
    ):
        """Student in a formed group gets group_formed status."""
        # Enroll students
        open_ter_period.enrolled_students.add(student_user, another_student)

        # Create group and add members to trigger auto-form (min_group_size=2)
        group = Group.objects.create(
            name="Groupe Forme",
            leader=student_user,
            project_type="TER",
            ter_period=open_ter_period,
        )
        group.members.add(student_user, another_student)
        group.check_and_auto_form()

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "group_formed"
        assert data["group"]["status"] == GroupStatus.FORME
        assert data["subject"] is None


class TestMyTERSubjectAssigned:
    """Tests for students with an assigned subject."""

    def test_my_ter_subject_assigned(
        self, client: Client, student_user, another_student, open_ter_period, validated_subject
    ):
        """Student with assigned subject gets subject_assigned status."""
        # Enroll students
        open_ter_period.enrolled_students.add(student_user, another_student)

        # Create formed group with assigned subject
        group = Group.objects.create(
            name="Groupe Assigne",
            leader=student_user,
            project_type="TER",
            ter_period=open_ter_period,
            assigned_subject=validated_subject,
        )
        group.members.add(student_user, another_student)
        # Use direct update to set status to CLOTURE (bypass FSM for test)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "subject_assigned"
        assert data["subject"] is not None
        assert data["subject"]["id"] == str(validated_subject.id)
        assert data["subject"]["title"] == "Sujet de recherche valide"
        assert data["group"]["assigned_subject_id"] == str(validated_subject.id)


class TestMyTERSpecificPeriod:
    """Tests for querying a specific TER period."""

    def test_my_ter_specific_period_with_query_param(
        self, client: Client, student_user, open_ter_period, closed_ter_period
    ):
        """Student can query a specific period using ter_period_id."""
        # Enroll student in both periods
        open_ter_period.enrolled_students.add(student_user)
        closed_ter_period.enrolled_students.add(student_user)

        # Create group in closed period
        group = Group.objects.create(
            name="Old Group",
            leader=student_user,
            project_type="TER",
            ter_period=closed_ter_period,
        )
        group.members.add(student_user)

        client.force_login(student_user)

        # Query closed period specifically
        response = client.get(f"/api/ter/my?ter_period_id={closed_ter_period.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["ter_period"]["id"] == str(closed_ter_period.id)
        assert data["group"]["name"] == "Old Group"

    def test_my_ter_default_to_open_period(
        self, client: Client, student_user, open_ter_period, closed_ter_period
    ):
        """Without ter_period_id, defaults to open period where enrolled."""
        # Enroll student in both periods
        open_ter_period.enrolled_students.add(student_user)
        closed_ter_period.enrolled_students.add(student_user)

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        data = response.json()
        # Should return open period, not closed one
        assert data["ter_period"]["id"] == str(open_ter_period.id)

    def test_my_ter_specific_period_not_found(
        self, client: Client, student_user
    ):
        """Querying non-existent period returns 404."""
        client.force_login(student_user)

        response = client.get(f"/api/ter/my?ter_period_id={uuid4()}")

        assert response.status_code == 404


class TestMyTERResponseStructure:
    """Tests for response structure completeness."""

    def test_my_ter_period_detail_fields(
        self, client: Client, student_user, open_ter_period
    ):
        """Period response includes all detail fields."""
        open_ter_period.enrolled_students.add(student_user)
        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        period = response.json()["ter_period"]

        # Check all TERPeriodDetailSchema fields are present
        assert "id" in period
        assert "name" in period
        assert "academic_year" in period
        assert "status" in period
        assert "group_formation_start" in period
        assert "group_formation_end" in period
        assert "subject_selection_start" in period
        assert "subject_selection_end" in period
        assert "assignment_date" in period
        assert "project_start" in period
        assert "project_end" in period
        assert "min_group_size" in period
        assert "max_group_size" in period
        assert "created" in period
        assert "modified" in period

    def test_my_ter_group_detail_fields(
        self, client: Client, student_user, open_ter_period
    ):
        """Group response includes all detail fields."""
        open_ter_period.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Groupe Complet",
            leader=student_user,
            project_type="TER",
            ter_period=open_ter_period,
        )
        group.members.add(student_user)

        client.force_login(student_user)

        response = client.get("/api/ter/my")

        assert response.status_code == 200
        group_data = response.json()["group"]

        # Check all GroupDetailSchema fields are present
        assert "id" in group_data
        assert "name" in group_data
        assert "leader" in group_data
        assert "member_count" in group_data
        assert "status" in group_data
        assert "project_type" in group_data
        assert "created" in group_data
        assert "members" in group_data
        assert "ter_period" in group_data
        assert "assigned_subject_id" in group_data

        # Check leader and members structure
        assert "id" in group_data["leader"]
        assert "email" in group_data["leader"]
        assert len(group_data["members"]) == 1
