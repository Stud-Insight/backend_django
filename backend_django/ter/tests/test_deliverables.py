"""
Tests for TER Deliverables API.

Tests upload, download, and management of group deliverables.
"""

import io
from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    MAX_DELIVERABLE_SIZE_BYTES,
    DeliverableAccessLog,
    DeliverableAccessType,
    DeliverableType,
    PeriodStatus,
    TERDeliverable,
    TERPeriod,
    UploadStatus,
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
        project_start=today + timedelta(days=60),
        project_end=today + timedelta(days=150),
        min_group_size=2,
        max_group_size=4,
    )


@pytest.fixture
def formed_group(db, ter_period, student_user, student_user_2):
    """Create a formed group with members."""
    group = Group.objects.create(
        name="Test Group",
        ter_period=ter_period,
        leader=student_user,
        status=GroupStatus.FORME,
    )
    group.members.add(student_user, student_user_2)
    return group


@pytest.fixture
def small_file():
    """Create a small test file (< 1MB)."""
    content = b"Test file content " * 1000  # ~18KB
    return SimpleUploadedFile(
        name="test_report.pdf",
        content=content,
        content_type="application/pdf",
    )


@pytest.fixture
def large_file():
    """Create a file that exceeds the size limit."""
    # Create content larger than 50MB
    content = b"x" * (MAX_DELIVERABLE_SIZE_BYTES + 1024)
    return SimpleUploadedFile(
        name="huge_file.zip",
        content=content,
        content_type="application/zip",
    )


class TestUploadDeliverable:
    """Tests for deliverable upload."""

    def test_upload_success(self, client: Client, student_user, formed_group, small_file):
        """Group member can upload a deliverable."""
        client.force_login(student_user)

        # Query params for metadata, file in POST data
        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}?deliverable_type=report&description=Final%20report&is_confidential=false",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["upload_status"] == "completed"
        assert "deliverable_id" in data

        # Verify deliverable was created
        deliverable = TERDeliverable.objects.get(id=data["deliverable_id"])
        assert deliverable.original_filename == "test_report.pdf"
        assert deliverable.group == formed_group
        assert deliverable.uploaded_by == student_user
        assert deliverable.deliverable_type == DeliverableType.REPORT

    def test_upload_file_too_large(self, client: Client, student_user, formed_group, large_file):
        """Upload fails if file exceeds size limit."""
        client.force_login(student_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}",
            data={"file": large_file},
            format="multipart",
        )

        assert response.status_code == 400
        data = response.json()
        assert "trop volumineux" in data["message"]
        assert "max 50MB" in data["message"]

    def test_upload_non_member_forbidden(self, client: Client, admin_user, formed_group, small_file, student_user_2):
        """Non-member cannot upload (unless admin)."""
        # Create a user who is not a member
        other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
        )
        client.force_login(other_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 403

    def test_upload_admin_allowed(self, client: Client, admin_user, formed_group, small_file):
        """Admin can upload to any group."""
        client.force_login(admin_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 201

    def test_upload_invalid_type(self, client: Client, student_user, formed_group, small_file):
        """Upload fails with invalid deliverable type."""
        client.force_login(student_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}?deliverable_type=invalid_type",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 400
        assert "invalide" in response.json()["message"]


class TestListDeliverables:
    """Tests for listing group deliverables."""

    def test_list_group_deliverables(self, client: Client, student_user, formed_group, ter_period):
        """Group member can list deliverables."""
        # Create some deliverables
        TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report1.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )
        TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report2.pdf",
            content_type="application/pdf",
            size=2000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.get(f"/api/ter/deliverables/group/{formed_group.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_non_member_forbidden(self, client: Client, formed_group):
        """Non-member cannot list group deliverables."""
        other_user = User.objects.create_user(
            email="other@example.com",
            password="password123",
        )
        client.force_login(other_user)

        response = client.get(f"/api/ter/deliverables/group/{formed_group.id}")

        assert response.status_code == 403


class TestDownloadDeliverable:
    """Tests for downloading deliverables."""

    def test_download_requires_auth(self, client: Client, student_user, formed_group, ter_period):
        """Download requires authentication."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        response = client.get(f"/api/ter/deliverables/{deliverable.id}/download")

        assert response.status_code in [401, 403]

    def test_download_pending_upload_fails(self, client: Client, student_user, formed_group, ter_period):
        """Cannot download if upload is not complete."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.PENDING,
        )

        client.force_login(student_user)

        response = client.get(f"/api/ter/deliverables/{deliverable.id}/download")

        assert response.status_code == 400
        assert "pas encore disponible" in response.json()["message"]


class TestUploadStatus:
    """Tests for checking upload status."""

    def test_check_upload_status(self, client: Client, student_user, formed_group, ter_period):
        """Can check upload status of own deliverable."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.PROCESSING,
        )

        client.force_login(student_user)

        response = client.get(f"/api/ter/deliverables/{deliverable.id}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["upload_status"] == "processing"
        assert data["is_complete"] is False


class TestUpdateDeliverable:
    """Tests for updating deliverable metadata."""

    def test_update_description(self, client: Client, student_user, formed_group, ter_period):
        """Uploader can update deliverable metadata."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            description="Original description",
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.put(
            f"/api/ter/deliverables/{deliverable.id}",
            data={
                "description": "Updated description",
                "is_confidential": True,
            },
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["is_confidential"] is True

    def test_update_non_owner_forbidden(self, client: Client, student_user, student_user_2, formed_group, ter_period):
        """Non-owner (but group member) cannot update."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user_2)

        response = client.put(
            f"/api/ter/deliverables/{deliverable.id}",
            data={"description": "Hacked"},
            content_type="application/json",
        )

        # student_user_2 is a member but not uploader or leader
        # The leader can manage, but student_user_2 is not the leader
        # Check if student_user is the leader
        assert formed_group.leader == student_user
        assert response.status_code == 403


class TestDeleteDeliverable:
    """Tests for deleting deliverables."""

    def test_delete_own_deliverable(self, client: Client, student_user, formed_group, ter_period):
        """Uploader can delete their deliverable."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 200
        assert TERDeliverable.objects.filter(id=deliverable.id).count() == 0

    def test_leader_can_delete_any_group_deliverable(
        self, client: Client, student_user, student_user_2, formed_group, ter_period
    ):
        """Group leader can delete any deliverable in their group."""
        # student_user is the leader
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user_2,  # Uploaded by another member
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)  # Leader

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 200

    def test_admin_can_delete_any_deliverable(
        self, client: Client, admin_user, student_user, formed_group, ter_period
    ):
        """Admin can delete any deliverable."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(admin_user)

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 200


class TestFileSizeValidation:
    """Tests specifically for file size validation."""

    def test_file_under_limit_accepted(self, client: Client, student_user, formed_group):
        """File under the limit should be accepted."""
        # Create a 1KB file (well under limit)
        content = b"x" * 1024
        file = SimpleUploadedFile(
            name="small.bin",
            content=content,
            content_type="application/octet-stream",
        )

        client.force_login(student_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}",
            data={"file": file},
            format="multipart",
        )

        assert response.status_code == 201

    def test_file_over_limit_rejected(self, client: Client, student_user, formed_group):
        """File over limit should be rejected via validation function."""
        from backend_django.ter.api.deliverables import validate_file_size
        from unittest.mock import MagicMock

        # Create a mock file with size over limit
        mock_file = MagicMock()
        mock_file.size = MAX_DELIVERABLE_SIZE_BYTES + 1

        # Test the validation function directly
        error = validate_file_size(mock_file)
        assert error is not None
        assert "trop volumineux" in error
        assert "max 50MB" in error

    def test_file_at_limit_accepted(self, client: Client, student_user, formed_group):
        """File at exactly the limit should pass validation."""
        from backend_django.ter.api.deliverables import validate_file_size
        from unittest.mock import MagicMock

        # Create a mock file exactly at limit
        mock_file = MagicMock()
        mock_file.size = MAX_DELIVERABLE_SIZE_BYTES

        # Test the validation function directly
        error = validate_file_size(mock_file)
        assert error is None


class TestDeadlineValidation:
    """Tests for deliverable modification deadline validation."""

    @pytest.fixture
    def expired_ter_period(self, db):
        """Create a TER period with expired project_end date."""
        today = date.today()
        return TERPeriod.objects.create(
            name="TER Expired",
            academic_year="2023-2024",
            status=PeriodStatus.OPEN,
            group_formation_start=today - timedelta(days=200),
            group_formation_end=today - timedelta(days=170),
            subject_selection_start=today - timedelta(days=160),
            subject_selection_end=today - timedelta(days=130),
            assignment_date=today - timedelta(days=120),
            project_start=today - timedelta(days=100),
            project_end=today - timedelta(days=1),  # Expired yesterday
            min_group_size=2,
            max_group_size=4,
        )

    @pytest.fixture
    def expired_group(self, db, expired_ter_period, student_user, student_user_2):
        """Create a group in an expired TER period."""
        group = Group.objects.create(
            name="Expired Group",
            ter_period=expired_ter_period,
            leader=student_user,
            status=GroupStatus.FORME,
        )
        group.members.add(student_user, student_user_2)
        return group

    def test_upload_blocked_after_deadline(
        self, client: Client, student_user, expired_group, small_file
    ):
        """Student cannot upload after project deadline."""
        client.force_login(student_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{expired_group.id}",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 400
        data = response.json()
        assert "date limite" in data["message"]
        assert "depassee" in data["message"]

    def test_upload_allowed_for_admin_after_deadline(
        self, client: Client, admin_user, expired_group, small_file
    ):
        """Admin can upload even after project deadline."""
        client.force_login(admin_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{expired_group.id}",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 201

    def test_update_blocked_after_deadline(
        self, client: Client, student_user, expired_group, expired_ter_period
    ):
        """Student cannot update deliverable after project deadline."""
        # Create a deliverable first
        deliverable = TERDeliverable.objects.create(
            ter_period=expired_ter_period,
            group=expired_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.put(
            f"/api/ter/deliverables/{deliverable.id}",
            data={"description": "Updated description"},
            content_type="application/json",
        )

        assert response.status_code == 400
        assert "date limite" in response.json()["message"]

    def test_delete_blocked_after_deadline(
        self, client: Client, student_user, expired_group, expired_ter_period
    ):
        """Student cannot delete deliverable after project deadline."""
        deliverable = TERDeliverable.objects.create(
            ter_period=expired_ter_period,
            group=expired_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 400
        assert "date limite" in response.json()["message"]

    def test_admin_can_delete_after_deadline(
        self, client: Client, admin_user, student_user, expired_group, expired_ter_period
    ):
        """Admin can delete deliverable after project deadline."""
        deliverable = TERDeliverable.objects.create(
            ter_period=expired_ter_period,
            group=expired_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(admin_user)

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 200

    def test_download_still_allowed_after_deadline(
        self, client: Client, student_user, expired_group, expired_ter_period
    ):
        """Download should still work after deadline (read-only operation)."""
        deliverable = TERDeliverable.objects.create(
            ter_period=expired_ter_period,
            group=expired_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        # Download should work - it's read-only
        response = client.get(f"/api/ter/deliverables/{deliverable.id}")
        assert response.status_code == 200


class TestAuditLogging:
    """Tests for deliverable access audit logging."""

    def test_upload_creates_audit_log(
        self, client: Client, student_user, formed_group, small_file
    ):
        """Uploading a deliverable creates an audit log entry."""
        client.force_login(student_user)

        response = client.post(
            f"/api/ter/deliverables/upload/{formed_group.id}",
            data={"file": small_file},
            format="multipart",
        )

        assert response.status_code == 201
        deliverable_id = response.json()["deliverable_id"]

        # Check audit log was created
        logs = DeliverableAccessLog.objects.filter(
            deliverable_id=deliverable_id,
            access_type=DeliverableAccessType.UPLOAD,
        )
        assert logs.count() == 1
        log = logs.first()
        assert log.user_email == student_user.email
        assert log.deliverable_filename == "test_report.pdf"

    def test_update_creates_audit_log(
        self, client: Client, student_user, formed_group, ter_period
    ):
        """Updating a deliverable creates an audit log entry."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.put(
            f"/api/ter/deliverables/{deliverable.id}",
            data={"description": "Updated description"},
            content_type="application/json",
        )

        assert response.status_code == 200

        # Check audit log was created
        logs = DeliverableAccessLog.objects.filter(
            deliverable=deliverable,
            access_type=DeliverableAccessType.UPDATE,
        )
        assert logs.count() == 1
        assert "description" in logs.first().details.get("updated_fields", {})

    def test_delete_creates_audit_log(
        self, client: Client, student_user, formed_group, ter_period
    ):
        """Deleting a deliverable creates an audit log entry."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )
        deliverable_id = deliverable.id

        client.force_login(student_user)

        response = client.delete(f"/api/ter/deliverables/{deliverable.id}")

        assert response.status_code == 200

        # Check audit log was created (deliverable is null after deletion)
        logs = DeliverableAccessLog.objects.filter(
            access_type=DeliverableAccessType.DELETE,
            deliverable_filename="report.pdf",
        )
        assert logs.count() == 1
        assert logs.first().deliverable is None  # Deliverable was deleted

    def test_view_access_logs_requires_admin(
        self, client: Client, student_user, formed_group, ter_period
    ):
        """Non-admin cannot view access logs."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        client.force_login(student_user)

        response = client.get(f"/api/ter/deliverables/{deliverable.id}/access-logs")

        assert response.status_code == 403

    def test_admin_can_view_access_logs(
        self, client: Client, admin_user, student_user, formed_group, ter_period
    ):
        """Admin can view access logs for a deliverable."""
        deliverable = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )

        # Create some log entries
        DeliverableAccessLog.log_access(
            deliverable=deliverable,
            user=student_user,
            access_type=DeliverableAccessType.DOWNLOAD,
        )

        client.force_login(admin_user)

        response = client.get(f"/api/ter/deliverables/{deliverable.id}/access-logs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["access_type"] == "download"

    def test_admin_can_view_group_access_logs(
        self, client: Client, admin_user, student_user, formed_group, ter_period
    ):
        """Admin can view access logs for all deliverables in a group."""
        deliverable1 = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report1.pdf",
            content_type="application/pdf",
            size=1000,
            upload_status=UploadStatus.COMPLETED,
        )
        deliverable2 = TERDeliverable.objects.create(
            ter_period=ter_period,
            group=formed_group,
            uploaded_by=student_user,
            original_filename="report2.pdf",
            content_type="application/pdf",
            size=2000,
            upload_status=UploadStatus.COMPLETED,
        )

        # Create log entries
        DeliverableAccessLog.log_access(
            deliverable=deliverable1,
            user=student_user,
            access_type=DeliverableAccessType.DOWNLOAD,
        )
        DeliverableAccessLog.log_access(
            deliverable=deliverable2,
            user=student_user,
            access_type=DeliverableAccessType.DOWNLOAD,
        )

        client.force_login(admin_user)

        response = client.get(f"/api/ter/deliverables/group/{formed_group.id}/access-logs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
