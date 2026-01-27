"""
Tests for TER and Stage periods API endpoints.
"""

from datetime import date, timedelta

import pytest
from django.test import Client

from backend_django.projects.models import PeriodStatus, StagePeriod, TERPeriod
from backend_django.users.models import User


@pytest.fixture
def student_user(db):
    """Create a regular student user."""
    return User.objects.create_user(
        email="student@test.fr",
        password="testpass123",
        first_name="Student",
        last_name="Test",
        is_active=True,
    )


@pytest.fixture
def staff_user(db):
    """Create a staff user."""
    return User.objects.create_user(
        email="staff@test.fr",
        password="testpass123",
        first_name="Staff",
        last_name="User",
        is_active=True,
        is_staff=True,
    )


@pytest.fixture
def ter_period_open(db):
    """Create an open TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025",
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
def ter_period_draft(db):
    """Create a draft TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2025-2026",
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


@pytest.fixture
def stage_period_open(db):
    """Create an open Stage period."""
    today = date.today()
    return StagePeriod.objects.create(
        name="Stage M2 2024-2025",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        offer_submission_start=today - timedelta(days=30),
        offer_submission_end=today + timedelta(days=30),
        application_start=today - timedelta(days=10),
        application_end=today + timedelta(days=60),
        internship_start=today + timedelta(days=90),
        internship_end=today + timedelta(days=180),
    )


@pytest.fixture
def authenticated_client(client: Client, student_user):
    """Client authenticated as student user."""
    client.force_login(student_user)
    return client


@pytest.fixture
def staff_client(client: Client, staff_user):
    """Client authenticated as staff user."""
    client.force_login(staff_user)
    return client


# ==================== TER Periods Tests ====================


@pytest.mark.django_db
class TestListTERPeriodsEndpoint:
    """Tests for GET /api/ter-periods/."""

    def test_unauthenticated_denied(self, client: Client):
        """Test unauthenticated access is denied."""
        response = client.get("/api/ter-periods/")
        assert response.status_code == 403

    def test_list_ter_periods_student(self, authenticated_client, ter_period_open, ter_period_draft):
        """Test student only sees open periods."""
        response = authenticated_client.get("/api/ter-periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == ter_period_open.name
        assert data[0]["status"] == "open"

    def test_list_ter_periods_staff_sees_all(self, staff_client, ter_period_open, ter_period_draft):
        """Test staff sees all periods."""
        response = staff_client.get("/api/ter-periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2

        names = [p["name"] for p in data]
        assert ter_period_open.name in names
        assert ter_period_draft.name in names

    def test_filter_by_status(self, staff_client, ter_period_open, ter_period_draft):
        """Test staff can filter by status."""
        response = staff_client.get("/api/ter-periods/?status=draft")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == ter_period_draft.name

    def test_filter_by_academic_year(self, staff_client, ter_period_open, ter_period_draft):
        """Test filtering by academic year."""
        response = staff_client.get("/api/ter-periods/?academic_year=2024-2025")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["academic_year"] == "2024-2025"

    def test_response_schema(self, authenticated_client, ter_period_open):
        """Test response contains expected fields."""
        response = authenticated_client.get("/api/ter-periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1

        period = data[0]
        assert "id" in period
        assert "name" in period
        assert "academic_year" in period
        assert "status" in period
        assert "group_formation_start" in period
        assert "group_formation_end" in period
        assert "min_group_size" in period
        assert "max_group_size" in period


@pytest.mark.django_db
class TestGetTERPeriodEndpoint:
    """Tests for GET /api/ter-periods/{id}."""

    def test_get_ter_period_detail(self, authenticated_client, ter_period_open):
        """Test getting TER period details."""
        response = authenticated_client.get(f"/api/ter-periods/{ter_period_open.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == ter_period_open.name
        assert data["academic_year"] == ter_period_open.academic_year

    def test_student_cannot_see_draft_period(self, authenticated_client, ter_period_draft):
        """Test student cannot access draft period."""
        response = authenticated_client.get(f"/api/ter-periods/{ter_period_draft.id}")
        assert response.status_code == 404

    def test_staff_can_see_draft_period(self, staff_client, ter_period_draft):
        """Test staff can access draft period."""
        response = staff_client.get(f"/api/ter-periods/{ter_period_draft.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == ter_period_draft.name

    def test_nonexistent_period(self, authenticated_client):
        """Test 404 for non-existent period."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/ter-periods/{fake_uuid}")
        assert response.status_code == 404


# ==================== Stage Periods Tests ====================


@pytest.mark.django_db
class TestListStagePeriodsEndpoint:
    """Tests for GET /api/stage-periods/."""

    def test_list_stage_periods(self, authenticated_client, stage_period_open):
        """Test listing stage periods."""
        response = authenticated_client.get("/api/stage-periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == stage_period_open.name

    def test_response_schema(self, authenticated_client, stage_period_open):
        """Test response contains expected fields."""
        response = authenticated_client.get("/api/stage-periods/")
        assert response.status_code == 200

        data = response.json()
        period = data[0]
        assert "id" in period
        assert "name" in period
        assert "academic_year" in period
        assert "status" in period
        assert "application_start" in period
        assert "application_end" in period


@pytest.mark.django_db
class TestGetStagePeriodEndpoint:
    """Tests for GET /api/stage-periods/{id}."""

    def test_get_stage_period_detail(self, authenticated_client, stage_period_open):
        """Test getting Stage period details."""
        response = authenticated_client.get(f"/api/stage-periods/{stage_period_open.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == stage_period_open.name
