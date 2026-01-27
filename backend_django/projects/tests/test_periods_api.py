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
    """Tests for GET /api/ter/periods/."""

    def test_unauthenticated_denied(self, client: Client):
        """Test unauthenticated access is denied."""
        response = client.get("/api/ter/periods/")
        assert response.status_code == 403

    def test_list_ter_periods_student(
        self, authenticated_client, ter_period_open, ter_period_draft, student_user
    ):
        """Test student only sees open periods where they are enrolled."""
        # Enroll student in the open period
        ter_period_open.enrolled_students.add(student_user)

        response = authenticated_client.get("/api/ter/periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == ter_period_open.name
        assert data[0]["status"] == "open"

    def test_list_ter_periods_staff_sees_all(self, staff_client, ter_period_open, ter_period_draft):
        """Test staff sees all periods."""
        response = staff_client.get("/api/ter/periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2

        names = [p["name"] for p in data]
        assert ter_period_open.name in names
        assert ter_period_draft.name in names

    def test_filter_by_status(self, staff_client, ter_period_open, ter_period_draft):
        """Test staff can filter by status."""
        response = staff_client.get("/api/ter/periods/?status=draft")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == ter_period_draft.name

    def test_filter_by_academic_year(self, staff_client, ter_period_open, ter_period_draft):
        """Test filtering by academic year."""
        response = staff_client.get("/api/ter/periods/?academic_year=2024-2025")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["academic_year"] == "2024-2025"

    def test_response_schema(self, authenticated_client, ter_period_open, student_user):
        """Test response contains expected fields."""
        # Enroll student in the period
        ter_period_open.enrolled_students.add(student_user)

        response = authenticated_client.get("/api/ter/periods/")
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
    """Tests for GET /api/ter/periods/{id}."""

    def test_get_ter_period_detail(self, authenticated_client, ter_period_open):
        """Test getting TER period details."""
        response = authenticated_client.get(f"/api/ter/periods/{ter_period_open.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == ter_period_open.name
        assert data["academic_year"] == ter_period_open.academic_year

    def test_student_cannot_see_draft_period(self, authenticated_client, ter_period_draft):
        """Test student cannot access draft period."""
        response = authenticated_client.get(f"/api/ter/periods/{ter_period_draft.id}")
        assert response.status_code == 404

    def test_staff_can_see_draft_period(self, staff_client, ter_period_draft):
        """Test staff can access draft period."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_draft.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == ter_period_draft.name

    def test_nonexistent_period(self, authenticated_client):
        """Test 404 for non-existent period."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/ter/periods/{fake_uuid}")
        assert response.status_code == 404


# ==================== Stage Periods Tests ====================


@pytest.mark.django_db
class TestListStagePeriodsEndpoint:
    """Tests for GET /api/stages/periods/."""

    def test_list_stage_periods(self, authenticated_client, stage_period_open):
        """Test listing stage periods."""
        response = authenticated_client.get("/api/stages/periods/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == stage_period_open.name

    def test_response_schema(self, authenticated_client, stage_period_open):
        """Test response contains expected fields."""
        response = authenticated_client.get("/api/stages/periods/")
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
    """Tests for GET /api/stages/periods/{id}."""

    def test_get_stage_period_detail(self, authenticated_client, stage_period_open):
        """Test getting Stage period details."""
        response = authenticated_client.get(f"/api/stages/periods/{stage_period_open.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == stage_period_open.name


# ==================== TER Period Create Tests ====================


@pytest.fixture
def valid_ter_period_data():
    """Valid data for creating a TER period."""
    today = date.today()
    return {
        "name": "TER Test 2026-2027",
        "academic_year": "2026-2027",
        "group_formation_start": str(today + timedelta(days=10)),
        "group_formation_end": str(today + timedelta(days=30)),
        "subject_selection_start": str(today + timedelta(days=31)),
        "subject_selection_end": str(today + timedelta(days=50)),
        "assignment_date": str(today + timedelta(days=51)),
        "project_start": str(today + timedelta(days=60)),
        "project_end": str(today + timedelta(days=180)),
        "min_group_size": 2,
        "max_group_size": 4,
    }


@pytest.mark.django_db
class TestCreateTERPeriodEndpoint:
    """Tests for POST /api/ter/periods/."""

    def test_staff_can_create_ter_period(self, staff_client, valid_ter_period_data):
        """Test staff can create a TER period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/ter/periods/",
            data=valid_ter_period_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == valid_ter_period_data["name"]
        assert data["academic_year"] == valid_ter_period_data["academic_year"]
        assert data["status"] == "draft"  # New periods start as draft
        assert data["min_group_size"] == 2
        assert data["max_group_size"] == 4

    def test_student_cannot_create_ter_period(self, authenticated_client, valid_ter_period_data):
        """Test student cannot create a TER period."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/ter/periods/",
            data=valid_ter_period_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403

    def test_duplicate_period_rejected(self, staff_client, ter_period_open):
        """Test duplicate period name in same year is rejected."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        today = date.today()
        duplicate_data = {
            "name": ter_period_open.name,
            "academic_year": ter_period_open.academic_year,
            "group_formation_start": str(today + timedelta(days=10)),
            "group_formation_end": str(today + timedelta(days=30)),
            "subject_selection_start": str(today + timedelta(days=31)),
            "subject_selection_end": str(today + timedelta(days=50)),
            "assignment_date": str(today + timedelta(days=51)),
            "project_start": str(today + timedelta(days=60)),
            "project_end": str(today + timedelta(days=180)),
        }

        response = staff_client.post(
            "/api/ter/periods/",
            data=duplicate_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "existe deja" in response.json()["message"]

    def test_invalid_academic_year_format(self, staff_client):
        """Test invalid academic year format is rejected."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        today = date.today()
        invalid_data = {
            "name": "Test Period",
            "academic_year": "2024",  # Invalid format
            "group_formation_start": str(today + timedelta(days=10)),
            "group_formation_end": str(today + timedelta(days=30)),
            "subject_selection_start": str(today + timedelta(days=31)),
            "subject_selection_end": str(today + timedelta(days=50)),
            "assignment_date": str(today + timedelta(days=51)),
            "project_start": str(today + timedelta(days=60)),
            "project_end": str(today + timedelta(days=180)),
        }

        response = staff_client.post(
            "/api/ter/periods/",
            data=invalid_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 422  # Validation error


@pytest.mark.django_db
class TestUpdateTERPeriodEndpoint:
    """Tests for PUT /api/ter/periods/{id}."""

    def test_staff_can_update_draft_period(self, staff_client, ter_period_draft):
        """Test staff can update a draft period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.put(
            f"/api/ter/periods/{ter_period_draft.id}",
            data={"name": "Updated Name"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"

    def test_cannot_update_open_period(self, staff_client, ter_period_open):
        """Test cannot update an open period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.put(
            f"/api/ter/periods/{ter_period_open.id}",
            data={"name": "Should Fail"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "brouillon" in response.json()["message"]

    def test_student_cannot_update_period(self, authenticated_client, ter_period_draft):
        """Test student cannot update a period."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.put(
            f"/api/ter/periods/{ter_period_draft.id}",
            data={"name": "Should Fail"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestTERPeriodStatusTransitions:
    """Tests for TER period status transitions."""

    def test_open_draft_period(self, staff_client, ter_period_draft):
        """Test opening a draft period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_draft.id}/open",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "open"

    def test_cannot_open_already_open_period(self, staff_client, ter_period_open):
        """Test cannot open an already open period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/open",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

    def test_close_open_period(self, staff_client, ter_period_open):
        """Test closing an open period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/close",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "closed"

    def test_cannot_close_draft_period(self, staff_client, ter_period_draft):
        """Test cannot close a draft period."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_draft.id}/close",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

    def test_student_cannot_change_status(self, authenticated_client, ter_period_draft):
        """Test student cannot change period status."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/ter/periods/{ter_period_draft.id}/open",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestCopyTERPeriodEndpoint:
    """Tests for POST /api/ter/periods/{id}/copy."""

    def test_staff_can_copy_period(self, staff_client, ter_period_open):
        """Test staff can copy a TER period to a new academic year."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "TER 2025-2026"
        assert data["academic_year"] == "2025-2026"
        assert data["status"] == "draft"
        assert data["min_group_size"] == ter_period_open.min_group_size
        assert data["max_group_size"] == ter_period_open.max_group_size

    def test_copy_shifts_dates_by_year_offset(self, staff_client, ter_period_open):
        """Test that copy shifts all dates by the year difference."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()

        # Calculate expected shifted dates (1 year = 365 days offset)
        from datetime import datetime
        original_start = datetime.strptime(
            str(ter_period_open.group_formation_start), "%Y-%m-%d"
        ).date()
        new_start = datetime.strptime(
            data["group_formation_start"], "%Y-%m-%d"
        ).date()

        # The offset should be approximately 365 days (1 year)
        days_diff = (new_start - original_start).days
        assert 364 <= days_diff <= 366  # Allow for leap year variation

    def test_student_cannot_copy_period(self, authenticated_client, ter_period_open):
        """Test student cannot copy a TER period."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = authenticated_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403

    def test_cannot_copy_to_duplicate_name_and_year(self, staff_client, ter_period_open):
        """Test cannot copy if name already exists in target year."""
        # Create a period with the target name/year
        TERPeriod.objects.create(
            name="TER 2025-2026",
            academic_year="2025-2026",
            status=PeriodStatus.DRAFT,
            group_formation_start=date.today() + timedelta(days=100),
            group_formation_end=date.today() + timedelta(days=130),
            subject_selection_start=date.today() + timedelta(days=131),
            subject_selection_end=date.today() + timedelta(days=160),
            assignment_date=date.today() + timedelta(days=165),
            project_start=date.today() + timedelta(days=170),
            project_end=date.today() + timedelta(days=280),
        )

        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "existe deja" in response.json()["message"]

    def test_copy_nonexistent_period_returns_404(self, staff_client):
        """Test copying a nonexistent period returns 404."""
        import uuid

        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{uuid.uuid4()}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 404

    def test_copy_with_invalid_academic_year_format(self, staff_client, ter_period_open):
        """Test copy with invalid academic year format fails validation."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025",  # Invalid format
        }

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 422

    def test_copy_with_empty_name_fails(self, staff_client, ter_period_open):
        """Test copy with empty name fails validation."""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 422

    def test_copy_preserves_group_size_settings(self, staff_client, db):
        """Test that copy preserves min/max group size from source."""
        today = date.today()
        source = TERPeriod.objects.create(
            name="Custom TER",
            academic_year="2024-2025",
            status=PeriodStatus.OPEN,
            group_formation_start=today,
            group_formation_end=today + timedelta(days=30),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
            min_group_size=2,
            max_group_size=6,
        )

        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "Custom TER Copy",
            "academic_year": "2025-2026",
        }

        response = staff_client.post(
            f"/api/ter/periods/{source.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["min_group_size"] == 2
        assert data["max_group_size"] == 6

    def test_unauthenticated_cannot_copy(self, client, ter_period_open):
        """Test unauthenticated user cannot copy period."""
        response = client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        copy_data = {
            "name": "TER 2025-2026",
            "academic_year": "2025-2026",
        }

        response = client.post(
            f"/api/ter/periods/{ter_period_open.id}/copy",
            data=copy_data,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        # Controller has IsAuthenticated permission, so unauthenticated gets 403
        assert response.status_code == 403


# ==================== TER Period Stats Tests ====================


@pytest.fixture
def enrolled_students(db, ter_period_open):
    """Create students enrolled in the TER period."""
    students = []
    for i in range(5):
        student = User.objects.create_user(
            email=f"enrolled{i}@test.fr",
            password="testpass123",
            first_name=f"Enrolled{i}",
            last_name="Student",
            is_active=True,
        )
        students.append(student)
        ter_period_open.enrolled_students.add(student)
    return students


@pytest.fixture
def group_with_members(db, ter_period_open, enrolled_students):
    """Create a group with some enrolled students."""
    from backend_django.groups.models import Group

    group = Group.objects.create(
        name="Test Group",
        leader=enrolled_students[0],
        ter_period=ter_period_open,
    )
    # Add first 3 students to the group
    group.members.add(enrolled_students[0], enrolled_students[1], enrolled_students[2])
    return group


@pytest.fixture
def ter_subject_validated(db, ter_period_open, staff_user):
    """Create a validated TER subject."""
    from backend_django.ter.models import TERSubject, SubjectStatus

    return TERSubject.objects.create(
        ter_period=ter_period_open,
        title="Test Subject",
        description="A test subject",
        domain="Test",
        professor=staff_user,
        status=SubjectStatus.VALIDATED,
    )


@pytest.mark.django_db
class TestTERPeriodStatsEndpoint:
    """Tests for GET /api/ter/periods/{id}/stats."""

    def test_staff_can_view_stats(self, staff_client, ter_period_open):
        """Test staff can view period stats."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 200

        data = response.json()
        assert "students_enrolled" in data
        assert "students_in_groups" in data
        assert "students_solitaires" in data
        assert "groups_total" in data
        assert "groups_complete" in data
        assert "groups_assigned" in data
        assert "subjects_total" in data
        assert "subjects_validated" in data
        assert "subjects_assigned" in data

    def test_student_cannot_view_stats(self, authenticated_client, ter_period_open):
        """Test student cannot view period stats."""
        response = authenticated_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 403

    def test_stats_counts_enrolled_students(
        self, staff_client, ter_period_open, enrolled_students
    ):
        """Test stats correctly counts enrolled students."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["students_enrolled"] == 5

    def test_stats_counts_students_in_groups(
        self, staff_client, ter_period_open, enrolled_students, group_with_members
    ):
        """Test stats correctly counts students in groups."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["students_in_groups"] == 3  # 3 members in group
        assert data["students_solitaires"] == 2  # 5 enrolled - 3 in group

    def test_stats_counts_groups(
        self, staff_client, ter_period_open, group_with_members
    ):
        """Test stats correctly counts groups."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["groups_total"] == 1
        # Group has 3 members, min_group_size is 1, so it's complete
        assert data["groups_complete"] == 1

    def test_stats_counts_subjects(
        self, staff_client, ter_period_open, ter_subject_validated
    ):
        """Test stats correctly counts subjects."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["subjects_total"] == 1
        assert data["subjects_validated"] == 1

    def test_stats_nonexistent_period(self, staff_client):
        """Test 404 for non-existent period."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = staff_client.get(f"/api/ter/periods/{fake_uuid}/stats")
        assert response.status_code == 404
