"""
Unit tests for RGPD (GDPR) compliance functions.
"""

import pytest
from django.contrib.auth.models import Group

from backend_django.chat.models import Conversation
from backend_django.chat.models import Message
from backend_django.projects.models import AcademicProject
from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import Attachment
from backend_django.projects.models import Proposal
from backend_django.projects.models import ProposalApplication
from backend_django.users.models import User
from backend_django.users.rgpd import anonymize_user
from backend_django.users.rgpd import can_delete_user
from backend_django.users.rgpd import collect_user_data
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def user_with_data(db):
    """Create a user with various related data for testing."""
    user = UserFactory(
        email="testuser@example.com",
        first_name="Test",
        last_name="User",
    )
    user.set_password("TestPass123!")
    user.save()

    # Add to a group
    group = Group.objects.create(name="TestGroup")
    user.groups.add(group)

    return user


@pytest.fixture
def admin_user(db):
    """Create an admin user."""
    user = UserFactory(
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
    )
    return user


@pytest.fixture
def staff_user(db):
    """Create a staff (non-superuser) user."""
    user = UserFactory(
        email="staff@example.com",
        is_staff=True,
        is_superuser=False,
    )
    return user


@pytest.mark.django_db
class TestCollectUserData:
    """Tests for collect_user_data function."""

    def test_collects_basic_profile_data(self, user_with_data):
        """Test that basic profile data is collected."""
        data = collect_user_data(user_with_data)

        assert "profile" in data
        assert data["profile"]["email"] == "testuser@example.com"
        assert data["profile"]["first_name"] == "Test"
        assert data["profile"]["last_name"] == "User"
        assert str(user_with_data.id) == data["profile"]["id"]

    def test_collects_groups(self, user_with_data):
        """Test that group membership is collected."""
        data = collect_user_data(user_with_data)

        assert "groups" in data
        assert len(data["groups"]) == 1
        assert data["groups"][0]["name"] == "TestGroup"

    def test_collects_conversations_and_messages(self, user_with_data):
        """Test that conversations and messages are collected."""
        # Create a conversation with messages
        other_user = UserFactory()
        conversation = Conversation.objects.create(name="Test Conv")
        conversation.participants.add(user_with_data, other_user)

        Message.objects.create(
            conversation=conversation,
            sender=user_with_data,
            content="Hello from test user",
        )
        Message.objects.create(
            conversation=conversation,
            sender=other_user,
            content="Hello from other user",
        )

        data = collect_user_data(user_with_data)

        assert "conversations" in data
        assert len(data["conversations"]) == 1
        # Only messages sent by the user should be included
        assert len(data["conversations"][0]["messages"]) == 1
        assert data["conversations"][0]["messages"][0]["content"] == "Hello from test user"

    def test_collects_projects_as_student(self, user_with_data):
        """Test that projects where user is student are collected."""
        from datetime import date

        project = AcademicProject.objects.create(
            student=user_with_data,
            subject="Test Project",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
        )

        data = collect_user_data(user_with_data)

        assert "projects_as_student" in data
        assert len(data["projects_as_student"]) == 1
        assert data["projects_as_student"][0]["subject"] == "Test Project"

    def test_collects_proposal_applications(self, user_with_data):
        """Test that proposal applications are collected."""
        creator = UserFactory()
        proposal = Proposal.objects.create(
            title="Test Proposal",
            description="Test description",
            project_type=AcademicProjectType.SRW,
            created_by=creator,
            academic_year="2024-2025",
        )

        application = ProposalApplication.objects.create(
            proposal=proposal,
            applicant=user_with_data,
            motivation="I want to work on this",
        )

        data = collect_user_data(user_with_data)

        assert "proposal_applications" in data
        assert len(data["proposal_applications"]) == 1
        assert data["proposal_applications"][0]["motivation"] == "I want to work on this"

    def test_includes_export_metadata(self, user_with_data):
        """Test that export metadata is included."""
        data = collect_user_data(user_with_data)

        assert "export_date" in data
        assert "export_version" in data
        assert data["export_version"] == "1.0"


@pytest.mark.django_db
class TestCanDeleteUser:
    """Tests for can_delete_user function."""

    def test_cannot_delete_self(self, admin_user):
        """Test that users cannot delete themselves."""
        can_delete, reason = can_delete_user(admin_user, admin_user)

        assert can_delete is False
        assert "propre compte" in reason

    def test_non_superuser_cannot_delete_superuser(self, staff_user, admin_user):
        """Test that non-superusers cannot delete superusers."""
        can_delete, reason = can_delete_user(admin_user, staff_user)

        assert can_delete is False
        assert "superutilisateur" in reason

    def test_non_superuser_cannot_delete_staff(self, staff_user):
        """Test that non-superusers cannot delete other staff."""
        other_staff = UserFactory(is_staff=True, is_superuser=False)

        can_delete, reason = can_delete_user(other_staff, staff_user)

        assert can_delete is False
        assert "staff" in reason

    def test_superuser_can_delete_anyone(self, admin_user):
        """Test that superusers can delete any user."""
        regular_user = UserFactory()
        staff = UserFactory(is_staff=True)
        other_superuser = UserFactory(is_superuser=True)

        assert can_delete_user(regular_user, admin_user) == (True, "")
        assert can_delete_user(staff, admin_user) == (True, "")
        assert can_delete_user(other_superuser, admin_user) == (True, "")

    def test_staff_can_delete_regular_users(self, staff_user):
        """Test that staff can delete regular users."""
        regular_user = UserFactory()

        can_delete, reason = can_delete_user(regular_user, staff_user)

        assert can_delete is True
        assert reason == ""


@pytest.mark.django_db
class TestAnonymizeUser:
    """Tests for anonymize_user function."""

    def test_anonymizes_profile_data(self, user_with_data, admin_user):
        """Test that profile data is anonymized."""
        original_email = user_with_data.email

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        user_with_data.refresh_from_db()
        assert user_with_data.email != original_email
        assert "@deleted.studinsight.local" in user_with_data.email
        assert user_with_data.first_name == "Utilisateur"
        assert user_with_data.last_name == "Supprimé"
        assert user_with_data.is_active is False
        assert "profile_anonymized" in summary["actions"]

    def test_removes_from_groups(self, user_with_data, admin_user):
        """Test that user is removed from all groups."""
        assert user_with_data.groups.count() == 1

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        user_with_data.refresh_from_db()
        assert user_with_data.groups.count() == 0
        assert any("removed_from" in action and "groups" in action for action in summary["actions"])

    def test_anonymizes_messages(self, user_with_data, admin_user):
        """Test that sent messages are anonymized."""
        other_user = UserFactory()
        conversation = Conversation.objects.create(is_group=True, name="Group")
        conversation.participants.add(user_with_data, other_user)

        message = Message.objects.create(
            conversation=conversation,
            sender=user_with_data,
            content="Original message content",
        )

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        message.refresh_from_db()
        assert message.content == "[Message supprimé - Compte RGPD]"
        assert any("anonymized" in action and "messages" in action for action in summary["actions"])

    def test_deletes_attachments(self, user_with_data, admin_user):
        """Test that user's attachments are deleted."""
        # Create an attachment (without actual file for testing)
        attachment = Attachment.objects.create(
            owner=user_with_data,
            original_filename="test.pdf",
            content_type="application/pdf",
            size=1000,
        )
        attachment_id = attachment.id

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        assert not Attachment.objects.filter(id=attachment_id).exists()
        assert any("deleted" in action and "attachments" in action for action in summary["actions"])

    def test_deletes_proposal_applications(self, user_with_data, admin_user):
        """Test that proposal applications are deleted."""
        creator = UserFactory()
        proposal = Proposal.objects.create(
            title="Test Proposal",
            description="Test",
            project_type=AcademicProjectType.SRW,
            created_by=creator,
            academic_year="2024-2025",
        )
        application = ProposalApplication.objects.create(
            proposal=proposal,
            applicant=user_with_data,
        )
        app_id = application.id

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        assert not ProposalApplication.objects.filter(id=app_id).exists()
        assert any("deleted" in action and "proposal_applications" in action for action in summary["actions"])

    def test_preserves_projects_as_student(self, user_with_data, admin_user):
        """Test that projects where user is student are preserved (anonymized)."""
        from datetime import date

        project = AcademicProject.objects.create(
            student=user_with_data,
            subject="Test Project",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
        )

        anonymize_user(user_with_data, deleted_by=admin_user)

        # Project should still exist
        project.refresh_from_db()
        assert project.student_id == user_with_data.id  # FK preserved but user is now anonymized

    def test_clears_referent_supervisor_relationships(self, user_with_data, admin_user):
        """Test that referent/supervisor relationships are cleared."""
        from datetime import date

        student = UserFactory()
        project = AcademicProject.objects.create(
            student=student,
            referent=user_with_data,
            supervisor=user_with_data,
            subject="Test Project",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
        )

        anonymize_user(user_with_data, deleted_by=admin_user)

        project.refresh_from_db()
        assert project.referent is None
        assert project.supervisor is None

    def test_returns_summary_with_all_actions(self, user_with_data, admin_user):
        """Test that summary contains all performed actions."""
        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        assert "user_id" in summary
        assert "original_email" in summary
        assert "anonymized_at" in summary
        assert "deleted_by" in summary
        assert "actions" in summary
        assert len(summary["actions"]) > 0
