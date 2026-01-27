"""
Tests for the TER periods API endpoints.
"""

from datetime import date, timedelta

import pytest
from django.test import Client

from backend_django.ter.models import PeriodStatus, TERPeriod
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def student_user(db):
    """Create a student user."""
    user = UserFactory(
        email="student@test.com",
        first_name="Student",
        last_name="Test",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def another_student(db):
    """Create another student user."""
    user = UserFactory(
        email="student2@test.com",
        first_name="Another",
        last_name="Student",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def staff_user(db):
    """Create a staff user."""
    user = UserFactory(
        email="staff@test.com",
        first_name="Staff",
        last_name="User",
        is_active=True,
        is_staff=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def ter_period_open(db):
    """Create an open TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025 S1",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=5),
        group_formation_end=today + timedelta(days=25),
        subject_selection_start=today + timedelta(days=31),
        subject_selection_end=today + timedelta(days=60),
        assignment_date=today + timedelta(days=61),
        project_start=today + timedelta(days=70),
        project_end=today + timedelta(days=180),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def authenticated_client(student_user):
    """Return a client authenticated as student."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": student_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.fixture
def staff_client(staff_user):
    """Return a client authenticated as staff."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": staff_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.mark.django_db
class TestListPeriodsEndpoint:
    """Tests for GET /api/ter/periods/."""

    def test_list_periods_student_only_sees_enrolled(
        self, authenticated_client, student_user, ter_period_open
    ):
        """Non-staff users only see periods they're enrolled in."""
        today = date.today()

        # Create another open period where student is NOT enrolled
        other_period = TERPeriod.objects.create(
            name="Other Period",
            academic_year="2024-2025",
            status=PeriodStatus.OPEN,
            group_formation_start=today - timedelta(days=5),
            group_formation_end=today + timedelta(days=25),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
            min_group_size=1,
            max_group_size=4,
        )

        # Enroll student in first period only
        ter_period_open.enrolled_students.add(student_user)

        response = authenticated_client.get("/api/ter/periods/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(ter_period_open.id)

    def test_list_periods_student_sees_nothing_when_not_enrolled(
        self, authenticated_client, student_user, ter_period_open
    ):
        """Non-staff user sees no periods when not enrolled in any."""
        # Student is not enrolled in any period
        response = authenticated_client.get("/api/ter/periods/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_periods_student_sees_multiple_enrolled(
        self, authenticated_client, student_user, ter_period_open
    ):
        """Non-staff user sees all periods they're enrolled in."""
        today = date.today()

        # Create another open period
        other_period = TERPeriod.objects.create(
            name="Other Period",
            academic_year="2025-2026",
            status=PeriodStatus.OPEN,
            group_formation_start=today - timedelta(days=5),
            group_formation_end=today + timedelta(days=25),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
            min_group_size=1,
            max_group_size=4,
        )

        # Enroll student in both periods
        ter_period_open.enrolled_students.add(student_user)
        other_period.enrolled_students.add(student_user)

        response = authenticated_client.get("/api/ter/periods/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_periods_student_does_not_see_draft_even_if_enrolled(
        self, authenticated_client, student_user
    ):
        """Non-staff users don't see draft periods even if enrolled."""
        today = date.today()

        # Create a draft period
        draft_period = TERPeriod.objects.create(
            name="Draft Period",
            academic_year="2024-2025",
            status=PeriodStatus.DRAFT,
            group_formation_start=today + timedelta(days=5),
            group_formation_end=today + timedelta(days=25),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
            min_group_size=1,
            max_group_size=4,
        )

        # Enroll student in draft period
        draft_period.enrolled_students.add(student_user)

        response = authenticated_client.get("/api/ter/periods/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_list_periods_staff_sees_all(
        self, staff_client, staff_user, ter_period_open
    ):
        """Staff users see all periods regardless of enrollment."""
        today = date.today()

        # Create draft and closed periods
        TERPeriod.objects.create(
            name="Draft Period",
            academic_year="2025-2026",
            status=PeriodStatus.DRAFT,
            group_formation_start=today + timedelta(days=100),
            group_formation_end=today + timedelta(days=130),
            subject_selection_start=today + timedelta(days=131),
            subject_selection_end=today + timedelta(days=160),
            assignment_date=today + timedelta(days=165),
            project_start=today + timedelta(days=170),
            project_end=today + timedelta(days=280),
            min_group_size=1,
            max_group_size=4,
        )

        TERPeriod.objects.create(
            name="Closed Period",
            academic_year="2023-2024",
            status=PeriodStatus.CLOSED,
            group_formation_start=today - timedelta(days=365),
            group_formation_end=today - timedelta(days=335),
            subject_selection_start=today - timedelta(days=330),
            subject_selection_end=today - timedelta(days=300),
            assignment_date=today - timedelta(days=295),
            project_start=today - timedelta(days=290),
            project_end=today - timedelta(days=180),
            min_group_size=1,
            max_group_size=4,
        )

        response = staff_client.get("/api/ter/periods/")

        assert response.status_code == 200
        data = response.json()
        # Staff sees all periods (open + draft + closed)
        assert len(data) == 3

    def test_list_periods_staff_can_filter_by_status(
        self, staff_client, staff_user, ter_period_open
    ):
        """Staff can filter periods by status."""
        today = date.today()

        # Create a draft period
        TERPeriod.objects.create(
            name="Draft Period",
            academic_year="2025-2026",
            status=PeriodStatus.DRAFT,
            group_formation_start=today + timedelta(days=100),
            group_formation_end=today + timedelta(days=130),
            subject_selection_start=today + timedelta(days=131),
            subject_selection_end=today + timedelta(days=160),
            assignment_date=today + timedelta(days=165),
            project_start=today + timedelta(days=170),
            project_end=today + timedelta(days=280),
            min_group_size=1,
            max_group_size=4,
        )

        # Filter by open status
        response = staff_client.get("/api/ter/periods/?status=open")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "open"

        # Filter by draft status
        response = staff_client.get("/api/ter/periods/?status=draft")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "draft"
