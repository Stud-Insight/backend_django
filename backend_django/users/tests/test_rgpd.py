"""
Unit tests for RGPD (GDPR) compliance functions.
"""

from datetime import date
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup

from backend_django.chat.models import Conversation
from backend_django.chat.models import Message
from backend_django.groups.models import Group as StudentGroup
from backend_django.projects.models import Attachment
from backend_django.projects.models import PeriodStatus
from backend_django.projects.models import TERPeriod
from backend_django.users.rgpd import anonymize_user
from backend_django.users.rgpd import can_delete_user
from backend_django.users.rgpd import collect_user_data
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def ter_period(db):
    """Create a TER period for testing."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025 S1",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today,
        group_formation_end=today + timedelta(days=30),
        subject_selection_start=today + timedelta(days=31),
        subject_selection_end=today + timedelta(days=60),
        assignment_date=today + timedelta(days=61),
        project_start=today + timedelta(days=70),
        project_end=today + timedelta(days=180),
        min_group_size=1,
        max_group_size=4,
    )


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

    # Add to a Django group (role)
    role = DjangoGroup.objects.create(name="TestRole")
    user.groups.add(role)

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

    def test_collects_roles(self, user_with_data):
        """Test that role membership is collected."""
        data = collect_user_data(user_with_data)

        assert "roles" in data
        assert len(data["roles"]) == 1
        assert data["roles"][0]["name"] == "TestRole"

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

    def test_collects_student_groups(self, user_with_data, ter_period):
        """Test that student group memberships are collected."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=user_with_data,
            ter_period=ter_period,
            project_type="TER",
        )
        group.members.add(user_with_data)

        data = collect_user_data(user_with_data)

        assert "student_groups" in data
        assert len(data["student_groups"]) == 1
        assert data["student_groups"][0]["name"] == "Test Group"
        assert data["student_groups"][0]["is_leader"] is True

    def test_includes_export_metadata(self, user_with_data):
        """Test that export metadata is included."""
        data = collect_user_data(user_with_data)

        assert "export_date" in data
        assert "export_version" in data
        assert data["export_version"] == "2.0"


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
        assert user_with_data.last_name == "Supprime"
        assert user_with_data.is_active is False
        assert "profile_anonymized" in summary["actions"]

    def test_removes_from_roles(self, user_with_data, admin_user):
        """Test that user is removed from all roles."""
        assert user_with_data.groups.count() == 1

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        user_with_data.refresh_from_db()
        assert user_with_data.groups.count() == 0
        assert any("removed_from" in action and "roles" in action for action in summary["actions"])

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
        assert message.content == "[Message supprime - Compte RGPD]"
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

    def test_removes_from_student_groups(self, user_with_data, admin_user, ter_period):
        """Test that user is removed from student groups."""
        # Create a group where user is a member but not leader
        leader = UserFactory()
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            ter_period=ter_period,
            project_type="TER",
        )
        group.members.add(leader, user_with_data)

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        # User should be removed from the group
        assert not group.members.filter(id=user_with_data.id).exists()
        # Group should still exist (has other members)
        assert StudentGroup.objects.filter(id=group.id).exists()
        assert any("student_groups" in action for action in summary["actions"])

    def test_transfers_leadership_when_leader_deleted(self, user_with_data, admin_user, ter_period):
        """Test that leadership is transferred when leader is deleted."""
        other_member = UserFactory()
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=user_with_data,
            ter_period=ter_period,
            project_type="TER",
        )
        group.members.add(user_with_data, other_member)

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        # Re-fetch group to avoid FSM field refresh issues
        group = StudentGroup.objects.get(id=group.id)
        # Leadership should be transferred to other member
        assert group.leader_id == other_member.id
        assert any("transferred_leadership" in action for action in summary["actions"])

    def test_deletes_empty_group_when_leader_deleted(self, user_with_data, admin_user, ter_period):
        """Test that empty groups are deleted when leader is deleted."""
        group = StudentGroup.objects.create(
            name="Solo Group",
            leader=user_with_data,
            ter_period=ter_period,
            project_type="TER",
        )
        group.members.add(user_with_data)
        group_id = group.id

        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        # Group should be deleted (was solo)
        assert not StudentGroup.objects.filter(id=group_id).exists()
        assert any("deleted_empty_group" in action for action in summary["actions"])

    def test_returns_summary_with_all_actions(self, user_with_data, admin_user):
        """Test that summary contains all performed actions."""
        summary = anonymize_user(user_with_data, deleted_by=admin_user)

        assert "user_id" in summary
        assert "original_email" in summary
        assert "anonymized_at" in summary
        assert "deleted_by" in summary
        assert "actions" in summary
        assert len(summary["actions"]) > 0
