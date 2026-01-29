"""
Tests for the TER periods API endpoints.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.core.roles import Role
from backend_django.ter.models import PeriodStatus, TERPeriod, TERSubject
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
    """Create a staff user (Respo TER) for TER admin access."""
    user = UserFactory(
        email="staff@test.com",
        first_name="Staff",
        last_name="User",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    # Add Respo TER role for TER admin access
    respo_ter_group, _ = Group.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(respo_ter_group)
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


@pytest.fixture
def encadrant_user(db):
    """Create an encadrant user."""
    user = UserFactory(
        email="encadrant@test.com",
        first_name="Prof",
        last_name="Encadrant",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    encadrant_group, _ = Group.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(encadrant_group)
    return user


def _get_csrf(client):
    """Get CSRF token from client."""
    resp = client.get("/api/auth/csrf")
    return resp.json()["csrf_token"]


@pytest.mark.django_db
class TestStudentsEndpoints:
    """Tests for GET/POST/DELETE /api/ter/periods/{id}/students."""

    def test_list_students_as_staff(self, staff_client, staff_user, student_user, ter_period_open):
        """Staff can list enrolled students."""
        ter_period_open.enrolled_students.add(student_user)

        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/students")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == student_user.email
        assert data[0]["first_name"] == student_user.first_name

    def test_list_students_empty(self, staff_client, ter_period_open):
        """Staff gets empty list when no students enrolled."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/students")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_students_forbidden_for_student(self, authenticated_client, ter_period_open):
        """Non-staff users cannot list enrolled students."""
        response = authenticated_client.get(f"/api/ter/periods/{ter_period_open.id}/students")

        assert response.status_code == 403

    def test_add_student(self, staff_client, staff_user, student_user, ter_period_open):
        """Staff can add a student to a period."""
        csrf = _get_csrf(staff_client)

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(student_user.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == student_user.email

        # Verify student is now enrolled
        assert ter_period_open.enrolled_students.filter(id=student_user.id).exists()

    def test_add_student_already_enrolled(self, staff_client, staff_user, student_user, ter_period_open):
        """Adding an already enrolled student returns 409."""
        ter_period_open.enrolled_students.add(student_user)
        csrf = _get_csrf(staff_client)

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(student_user.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 409

    def test_add_student_not_found(self, staff_client, staff_user, ter_period_open):
        """Adding a non-existent user returns 404."""
        import uuid
        csrf = _get_csrf(staff_client)

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(uuid.uuid4())},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 404

    def test_add_student_forbidden_for_student(self, authenticated_client, student_user, ter_period_open):
        """Non-staff users cannot add students."""
        csrf = _get_csrf(authenticated_client)

        response = authenticated_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(student_user.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_remove_student(self, staff_client, staff_user, student_user, ter_period_open):
        """Staff can remove a student from a period."""
        ter_period_open.enrolled_students.add(student_user)
        csrf = _get_csrf(staff_client)

        response = staff_client.delete(
            f"/api/ter/periods/{ter_period_open.id}/students/{student_user.id}",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 204

        # Verify student is no longer enrolled
        assert not ter_period_open.enrolled_students.filter(id=student_user.id).exists()

    def test_remove_student_not_enrolled(self, staff_client, staff_user, student_user, ter_period_open):
        """Removing a non-enrolled student returns 404."""
        csrf = _get_csrf(staff_client)

        response = staff_client.delete(
            f"/api/ter/periods/{ter_period_open.id}/students/{student_user.id}",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 404

    def test_remove_student_forbidden_for_student(self, authenticated_client, student_user, ter_period_open):
        """Non-staff users cannot remove students."""
        ter_period_open.enrolled_students.add(student_user)
        csrf = _get_csrf(authenticated_client)

        response = authenticated_client.delete(
            f"/api/ter/periods/{ter_period_open.id}/students/{student_user.id}",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 403

    def test_add_then_list_students(self, staff_client, staff_user, student_user, another_student, ter_period_open):
        """Full flow: add two students, list them, remove one."""
        csrf = _get_csrf(staff_client)

        # Add two students
        staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(student_user.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/students",
            data={"user_id": str(another_student.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # List - should have 2
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/students")
        assert response.status_code == 200
        assert len(response.json()) == 2

        # Remove one
        staff_client.delete(
            f"/api/ter/periods/{ter_period_open.id}/students/{student_user.id}",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # List - should have 1
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/students")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == another_student.email


@pytest.mark.django_db
class TestEncadrantsEndpoint:
    """Tests for GET /api/ter/periods/{id}/encadrants."""

    def test_list_encadrants_with_subjects(
        self, staff_client, staff_user, encadrant_user, ter_period_open
    ):
        """Staff can list encadrants derived from subjects."""
        # Create a subject with professor
        TERSubject.objects.create(
            ter_period=ter_period_open,
            title="Sujet IA",
            description="Description",
            domain="IA/ML",
            professor=encadrant_user,
            status="validated",
        )

        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/encadrants")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["email"] == encadrant_user.email

    def test_list_encadrants_professor_and_supervisor(
        self, staff_client, staff_user, encadrant_user, ter_period_open
    ):
        """Both professor and supervisor are listed as encadrants."""
        supervisor = UserFactory(
            email="supervisor@test.com",
            first_name="Super",
            last_name="Visor",
            is_active=True,
        )

        TERSubject.objects.create(
            ter_period=ter_period_open,
            title="Sujet Securite",
            description="Description",
            domain="Sécurité",
            professor=encadrant_user,
            supervisor=supervisor,
            status="validated",
        )

        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/encadrants")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        emails = {d["email"] for d in data}
        assert encadrant_user.email in emails
        assert supervisor.email in emails

    def test_list_encadrants_no_duplicates(
        self, staff_client, staff_user, encadrant_user, ter_period_open
    ):
        """Same encadrant on multiple subjects appears only once."""
        TERSubject.objects.create(
            ter_period=ter_period_open,
            title="Sujet 1",
            description="Desc",
            domain="IA/ML",
            professor=encadrant_user,
            status="validated",
        )
        TERSubject.objects.create(
            ter_period=ter_period_open,
            title="Sujet 2",
            description="Desc",
            domain="Web",
            professor=encadrant_user,
            status="validated",
        )

        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/encadrants")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    def test_list_encadrants_empty(self, staff_client, ter_period_open):
        """No subjects means no encadrants."""
        response = staff_client.get(f"/api/ter/periods/{ter_period_open.id}/encadrants")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_encadrants_forbidden_for_student(self, authenticated_client, ter_period_open):
        """Non-staff users cannot list encadrants."""
        response = authenticated_client.get(f"/api/ter/periods/{ter_period_open.id}/encadrants")

        assert response.status_code == 403
