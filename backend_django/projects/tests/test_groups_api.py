"""
Tests for the groups API endpoints.
"""

from datetime import date
from datetime import timedelta

import pytest
from django.test import Client

from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import GroupStatus
from backend_django.projects.models import PeriodStatus
from backend_django.projects.models import StudentGroup
from backend_django.projects.models import TERPeriod
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
def ter_period_open(db):
    """Create an open TER period in formation phase."""
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
def ter_period_formation_ended(db):
    """Create a TER period where formation phase has ended."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2023-2024 S2",
        academic_year="2023-2024",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=60),
        group_formation_end=today - timedelta(days=30),  # Ended
        subject_selection_start=today - timedelta(days=29),
        subject_selection_end=today + timedelta(days=10),
        assignment_date=today + timedelta(days=15),
        project_start=today + timedelta(days=20),
        project_end=today + timedelta(days=120),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def ter_period_draft(db):
    """Create a draft (not open) TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Draft",
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
def another_client(another_student):
    """Return a client authenticated as another student."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": another_student.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.mark.django_db
class TestCreateGroupEndpoint:
    """Tests for POST /api/groups."""

    def test_unauthenticated_denied(self, ter_period_open):
        """Test unauthenticated request is denied."""
        client = Client()
        response = client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = client.post(
            "/api/groups/",
            data={"name": "My Group", "ter_period_id": str(ter_period_open.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        # Returns 403 Forbidden when not authenticated (permission denied)
        assert response.status_code == 403

    def test_create_group_success(self, authenticated_client, ter_period_open, student_user):
        """Test creating a group successfully."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "ML Enthusiasts", "ter_period_id": str(ter_period_open.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "ML Enthusiasts"
        assert data["status"] == GroupStatus.OUVERT
        assert data["project_type"] == AcademicProjectType.SRW
        assert data["leader"]["email"] == student_user.email
        assert data["member_count"] == 1
        assert len(data["members"]) == 1
        assert data["members"][0]["email"] == student_user.email

    def test_create_group_no_period_specified(self, authenticated_client):
        """Test error when no period is specified."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "My Group"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "période TER ou Stage" in response.json()["message"]

    def test_create_group_period_not_open(self, authenticated_client, ter_period_draft):
        """Test error when period is not open."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "My Group", "ter_period_id": str(ter_period_draft.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "n'est pas ouverte" in response.json()["message"]

    def test_create_group_formation_ended(self, authenticated_client, ter_period_formation_ended):
        """Test error when formation period has ended."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "My Group", "ter_period_id": str(ter_period_formation_ended.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "formation des groupes est terminée" in response.json()["message"]

    def test_cannot_lead_multiple_groups_same_period(self, authenticated_client, ter_period_open, student_user):
        """Test user cannot lead multiple groups for same TER period."""
        # Create first group
        StudentGroup.objects.create(
            name="First Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # Try to create second group
        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "Second Group", "ter_period_id": str(ter_period_open.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "déjà leader" in response.json()["message"]

    def test_name_validation_too_short(self, authenticated_client, ter_period_open):
        """Test name must be at least 3 characters."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "AB", "ter_period_id": str(ter_period_open.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 422  # Validation error

    def test_name_validation_empty(self, authenticated_client, ter_period_open):
        """Test name cannot be empty."""
        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            "/api/groups/",
            data={"name": "", "ter_period_id": str(ter_period_open.id)},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 422  # Validation error


@pytest.mark.django_db
class TestListGroupsEndpoint:
    """Tests for GET /api/groups."""

    def test_list_groups(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test listing all groups."""
        # Create some groups
        StudentGroup.objects.create(
            name="Group A",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )
        StudentGroup.objects.create(
            name="Group B",
            leader=another_student,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get("/api/groups/")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2
        names = [g["name"] for g in data]
        assert "Group A" in names
        assert "Group B" in names

    def test_filter_by_ter_period(self, authenticated_client, ter_period_open, ter_period_draft, student_user, another_student):
        """Test filtering groups by TER period."""
        # Set draft period to open for this test
        ter_period_draft.status = PeriodStatus.OPEN
        ter_period_draft.save()

        StudentGroup.objects.create(
            name="Group Period 1",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )
        StudentGroup.objects.create(
            name="Group Period 2",
            leader=another_student,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_draft,
        )

        response = authenticated_client.get(f"/api/groups/?ter_period_id={ter_period_open.id}")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Group Period 1"


@pytest.mark.django_db
class TestMyGroupsEndpoint:
    """Tests for GET /api/groups/my."""

    def test_my_groups(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test getting my groups."""
        # Create a group where student is leader
        group1 = StudentGroup.objects.create(
            name="My Led Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        # Create a group where student is just a member
        group2 = StudentGroup.objects.create(
            name="Other Group",
            leader=another_student,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )
        group2.members.add(student_user)

        # Create a group where student is not a member
        StudentGroup.objects.create(
            name="Not My Group",
            leader=another_student,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get("/api/groups/my")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 2
        names = [g["name"] for g in data]
        assert "My Led Group" in names
        assert "Other Group" in names
        assert "Not My Group" not in names


@pytest.mark.django_db
class TestGetGroupEndpoint:
    """Tests for GET /api/groups/{id}."""

    def test_get_group_detail(self, authenticated_client, ter_period_open, student_user):
        """Test getting group details."""
        group = StudentGroup.objects.create(
            name="Detail Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get(f"/api/groups/{group.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Detail Group"
        assert data["leader"]["email"] == student_user.email
        assert data["ter_period"]["name"] == ter_period_open.name
        assert data["stage_period"] is None

    def test_get_nonexistent_group(self, authenticated_client):
        """Test 404 for non-existent group."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = authenticated_client.get(f"/api/groups/{fake_uuid}")
        assert response.status_code == 404


@pytest.mark.django_db
class TestInviteToGroupEndpoint:
    """Tests for POST /api/groups/{id}/invite."""

    def test_invite_success(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test leader can invite a student."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": another_student.email, "message": "Join us!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["invitee"]["email"] == another_student.email
        assert data["status"] == "pending"
        assert data["message"] == "Join us!"

    def test_invite_non_leader_denied(self, another_client, ter_period_open, student_user, another_student):
        """Test non-leader cannot invite."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = another_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # another_student tries to invite (not the leader)
        response = another_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": "someone@test.com"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403

    def test_invite_to_closed_group_denied(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test cannot invite to a formed/closed group."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )
        group.form_group()
        group.save()

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": another_student.email},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "ouvert" in response.json()["message"]

    def test_invite_existing_member_denied(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test cannot invite someone already in the group."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )
        group.members.add(another_student)

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": another_student.email},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400
        assert "déjà membre" in response.json()["message"]

    def test_invite_unknown_email(self, authenticated_client, ter_period_open, student_user):
        """Test inviting unknown email returns 404."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": "unknown@test.com"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 404

    def test_duplicate_pending_invitation_denied(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test cannot send duplicate pending invitation."""
        from backend_django.projects.models import GroupInvitation

        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        # Create existing pending invitation
        GroupInvitation.objects.create(
            group=group,
            invitee=another_student,
            invited_by=student_user,
        )

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = authenticated_client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": another_student.email},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 409  # AlreadyExistsError


@pytest.mark.django_db
class TestRespondToInvitationEndpoint:
    """Tests for POST /api/groups/invitations/{id}/respond."""

    def test_accept_invitation(self, another_client, ter_period_open, student_user, another_student):
        """Test invitee can accept invitation."""
        from backend_django.projects.models import GroupInvitation

        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=another_student,
            invited_by=student_user,
        )

        response = another_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = another_client.post(
            f"/api/groups/invitations/{invitation.id}/respond",
            data={"accept": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "accepted"

        # Verify user was added to group (reload from DB to avoid FSM issues)
        updated_group = StudentGroup.objects.get(id=group.id)
        assert updated_group.is_member(another_student)

    def test_decline_invitation(self, another_client, ter_period_open, student_user, another_student):
        """Test invitee can decline invitation."""
        from backend_django.projects.models import GroupInvitation

        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=another_student,
            invited_by=student_user,
        )

        response = another_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = another_client.post(
            f"/api/groups/invitations/{invitation.id}/respond",
            data={"accept": False},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "declined"

        # Verify user was NOT added to group (reload from DB)
        updated_group = StudentGroup.objects.get(id=group.id)
        assert not updated_group.is_member(another_student)

    def test_respond_wrong_user_denied(self, authenticated_client, ter_period_open, student_user, another_student):
        """Test cannot respond to someone else's invitation."""
        from backend_django.projects.models import GroupInvitation

        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=another_student,
            invited_by=student_user,
        )

        response = authenticated_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        # student_user (leader) tries to respond to another_student's invitation
        response = authenticated_client.post(
            f"/api/groups/invitations/{invitation.id}/respond",
            data={"accept": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestMyInvitationsEndpoint:
    """Tests for GET /api/groups/invitations/received."""

    def test_list_my_invitations(self, another_client, ter_period_open, student_user, another_student):
        """Test user can see their received invitations."""
        from backend_django.projects.models import GroupInvitation

        group = StudentGroup.objects.create(
            name="Test Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        GroupInvitation.objects.create(
            group=group,
            invitee=another_student,
            invited_by=student_user,
            message="Please join!",
        )

        response = another_client.get("/api/groups/invitations/received")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["group_name"] == "Test Group"
        assert data[0]["message"] == "Please join!"


@pytest.mark.django_db
class TestAutoDeclineInvitations:
    """Tests for auto-declining other invitations when accepting one."""

    def test_accept_auto_declines_other_invitations_same_period(
        self, another_client, ter_period_open, student_user, another_student
    ):
        """Test accepting invitation auto-declines others for same period."""
        from backend_django.projects.models import GroupInvitation, InvitationStatus

        # Create two groups in the same period
        group1 = StudentGroup.objects.create(
            name="Group 1",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        third_user = UserFactory(email="third@test.com", is_active=True)
        third_user.set_password("testpass123")
        third_user.save()

        group2 = StudentGroup.objects.create(
            name="Group 2",
            leader=third_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        # Invite another_student to both groups
        inv1 = GroupInvitation.objects.create(
            group=group1,
            invitee=another_student,
            invited_by=student_user,
        )
        inv2 = GroupInvitation.objects.create(
            group=group2,
            invitee=another_student,
            invited_by=third_user,
        )

        # another_student accepts inv1
        response = another_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = another_client.post(
            f"/api/groups/invitations/{inv1.id}/respond",
            data={"accept": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # inv1 should be accepted
        inv1.refresh_from_db()
        assert inv1.status == InvitationStatus.ACCEPTED

        # inv2 should be auto-declined
        inv2.refresh_from_db()
        assert inv2.status == InvitationStatus.DECLINED

    def test_accept_does_not_affect_different_period(
        self, another_client, ter_period_open, student_user, another_student
    ):
        """Test accepting invitation does not affect invitations for different periods."""
        from backend_django.projects.models import GroupInvitation, InvitationStatus, StagePeriod, PeriodStatus
        from datetime import timedelta

        today = date.today()

        # Create a stage period
        stage_period = StagePeriod.objects.create(
            name="Stage 2024-2025",
            academic_year="2024-2025",
            status=PeriodStatus.OPEN,
            offer_submission_start=today,
            offer_submission_end=today + timedelta(days=30),
            application_start=today,
            application_end=today + timedelta(days=60),
            internship_start=today + timedelta(days=90),
            internship_end=today + timedelta(days=180),
        )

        # TER group
        group_ter = StudentGroup.objects.create(
            name="TER Group",
            leader=student_user,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period_open,
        )

        third_user = UserFactory(email="third2@test.com", is_active=True)
        third_user.set_password("testpass123")
        third_user.save()

        # Stage group
        group_stage = StudentGroup.objects.create(
            name="Stage Group",
            leader=third_user,
            project_type=AcademicProjectType.INTERNSHIP,
            stage_period=stage_period,
        )

        # Invite another_student to both
        inv_ter = GroupInvitation.objects.create(
            group=group_ter,
            invitee=another_student,
            invited_by=student_user,
        )
        inv_stage = GroupInvitation.objects.create(
            group=group_stage,
            invitee=another_student,
            invited_by=third_user,
        )

        # Accept TER invitation
        response = another_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = another_client.post(
            f"/api/groups/invitations/{inv_ter.id}/respond",
            data={"accept": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        # Stage invitation should still be pending (different period type)
        inv_stage.refresh_from_db()
        assert inv_stage.status == InvitationStatus.PENDING
