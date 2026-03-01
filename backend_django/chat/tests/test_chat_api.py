"""
Tests for Chat API - Epic 6 Messaging System.

Tests for conversation management, message sending, file attachments,
and role-based permissions.
"""

import io
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from backend_django.chat.models import Conversation, Message
from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def student_user(db):
    """Create a student user with Etudiant role."""
    user = User.objects.create_user(
        email="student@example.com",
        password="password123",
        first_name="Jean",
        last_name="Etudiant",
    )
    etudiant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(etudiant_group)
    return user


@pytest.fixture
def another_student(db):
    """Create another student user with Etudiant role."""
    user = User.objects.create_user(
        email="student2@example.com",
        password="password123",
        first_name="Marie",
        last_name="Etudiante",
    )
    etudiant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(etudiant_group)
    return user


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
def admin_user(db):
    """Create an admin user."""
    user = User.objects.create_user(
        email="admin@example.com",
        password="password123",
        first_name="Admin",
        last_name="System",
        is_staff=True,
    )
    admin_group, _ = DjangoGroup.objects.get_or_create(name=Role.ADMIN.value)
    user.groups.add(admin_group)
    return user


@pytest.fixture
def respo_ter_user(db):
    """Create a Respo TER user."""
    user = User.objects.create_user(
        email="respo_ter@example.com",
        password="password123",
        first_name="Respo",
        last_name="TER",
    )
    respo_group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(respo_group)
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


@pytest.fixture
def closed_group_with_subject(db, student_user, another_student, open_ter_period, validated_subject):
    """Create a closed group with an assigned subject."""
    group = Group.objects.create(
        name="Groupe TER",
        leader=student_user,
        project_type="TER",
        ter_period=open_ter_period,
        assigned_subject=validated_subject,
    )
    group.members.add(student_user, another_student)
    # Directly set status to CLOTURE (bypass FSM for test)
    Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)
    # Re-fetch from DB to get updated status (avoids FSM __set__ restriction)
    return Group.objects.get(pk=group.pk)


@pytest.fixture
def conversation(db, student_user, encadrant_user):
    """Create a 1-on-1 conversation."""
    conv = Conversation.objects.create(
        name="",
        is_group=False,
    )
    conv.participants.add(student_user, encadrant_user)
    return conv


@pytest.fixture
def group_conversation(db, student_user, another_student, encadrant_user):
    """Create a group conversation."""
    conv = Conversation.objects.create(
        name="TER: Groupe TER",
        is_group=True,
    )
    conv.participants.add(student_user, another_student, encadrant_user)
    return conv


# =============================================================================
# Tests: Authentication
# =============================================================================


@pytest.mark.django_db
class TestChatAuthentication:
    """Test authentication requirements for chat endpoints."""

    def test_list_conversations_requires_auth(self, client: Client):
        """Listing conversations requires authentication."""
        response = client.get("/api/chat/conversations")
        assert response.status_code == 403

    def test_create_conversation_requires_auth(self, client: Client):
        """Creating conversation requires authentication."""
        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [], "is_group": False},
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_get_conversation_requires_auth(self, client: Client, conversation):
        """Getting conversation details requires authentication."""
        response = client.get(f"/api/chat/conversations/{conversation.id}")
        assert response.status_code == 403


# =============================================================================
# Tests: List Conversations
# =============================================================================


@pytest.mark.django_db
class TestListConversations:
    """Tests for GET /chat/conversations."""

    def test_list_empty_conversations(self, client: Client, student_user):
        """User with no conversations gets empty list."""
        client.force_login(student_user)

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_conversations_returns_user_conversations(
        self, client: Client, student_user, conversation
    ):
        """User sees their conversations."""
        client.force_login(student_user)

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(conversation.id)

    def test_list_conversations_excludes_others(
        self, client: Client, student_user, another_student
    ):
        """User doesn't see conversations they're not part of."""
        # Create conversation between other users
        conv = Conversation.objects.create(is_group=False)
        conv.participants.add(another_student)

        client.force_login(student_user)

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_conversations_includes_unread_count(
        self, client: Client, student_user, encadrant_user, conversation
    ):
        """Conversation includes unread message count."""
        # Create messages from encadrant (unread for student)
        Message.objects.create(
            conversation=conversation,
            sender=encadrant_user,
            content="Message 1",
        )
        Message.objects.create(
            conversation=conversation,
            sender=encadrant_user,
            content="Message 2",
        )

        client.force_login(student_user)

        response = client.get("/api/chat/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data[0]["unread_count"] == 2


# =============================================================================
# Tests: Create Conversation
# =============================================================================


@pytest.mark.django_db
class TestCreateConversation:
    """Tests for POST /chat/conversations."""

    def test_create_conversation_requires_participant(
        self, client: Client, student_user
    ):
        """Creating conversation requires at least one participant."""
        client.force_login(student_user)

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_create_conversation_invalid_participant(
        self, client: Client, student_user
    ):
        """Creating conversation with invalid participant returns error."""
        client.force_login(student_user)
        from uuid import uuid4

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [str(uuid4())], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_create_group_conversation(
        self, client: Client, admin_user, student_user, another_student
    ):
        """Admin can create group conversation."""
        client.force_login(admin_user)

        response = client.post(
            "/api/chat/conversations",
            data={
                "participant_ids": [str(student_user.id), str(another_student.id)],
                "is_group": True,
                "name": "Groupe Test",
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_group"] is True
        assert data["name"] == "Groupe Test"
        assert len(data["participants"]) == 3  # admin + 2 students

    def test_create_duplicate_conversation_returns_existing(
        self, client: Client, admin_user, student_user
    ):
        """Creating duplicate 1-on-1 conversation returns existing one."""
        # Admin can message anyone without restrictions
        # Create a conversation first
        existing_conv = Conversation.objects.create(is_group=False)
        existing_conv.participants.add(admin_user, student_user)

        client.force_login(admin_user)

        # Try to create another conversation with same participant
        response = client.post(
            "/api/chat/conversations",
            data={
                "participant_ids": [str(student_user.id)],
                "is_group": False,
            },
            content_type="application/json",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(existing_conv.id)


# =============================================================================
# Tests: Get Conversation Detail
# =============================================================================


@pytest.mark.django_db
class TestGetConversation:
    """Tests for GET /chat/conversations/{id}."""

    def test_get_conversation_as_participant(
        self, client: Client, student_user, conversation
    ):
        """Participant can view conversation details."""
        client.force_login(student_user)

        response = client.get(f"/api/chat/conversations/{conversation.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conversation.id)
        assert "messages" in data
        assert "participants" in data

    def test_get_conversation_non_participant_denied(
        self, client: Client, another_student, conversation
    ):
        """Non-participant cannot view conversation."""
        client.force_login(another_student)

        response = client.get(f"/api/chat/conversations/{conversation.id}")

        assert response.status_code == 403

    def test_get_conversation_marks_messages_read(
        self, client: Client, student_user, encadrant_user, conversation
    ):
        """Viewing conversation marks messages as read."""
        # Create unread message
        msg = Message.objects.create(
            conversation=conversation,
            sender=encadrant_user,
            content="Hello",
        )
        assert not msg.read_by.filter(id=student_user.id).exists()

        client.force_login(student_user)
        client.get(f"/api/chat/conversations/{conversation.id}")

        # Check message is now read
        msg.refresh_from_db()
        assert msg.read_by.filter(id=student_user.id).exists()


# =============================================================================
# Tests: Send Message
# =============================================================================


@pytest.mark.django_db
class TestSendMessage:
    """Tests for POST /chat/conversations/{id}/messages."""

    def test_send_text_message(
        self, client: Client, student_user, conversation
    ):
        """Participant can send text message."""
        client.force_login(student_user)

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=Hello!",
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"]["content"] == "Hello!"

    def test_send_empty_message_fails(
        self, client: Client, student_user, conversation
    ):
        """Sending empty message fails."""
        client.force_login(student_user)

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/messages",
        )

        assert response.status_code == 400

    def test_send_message_non_participant_denied(
        self, client: Client, another_student, conversation
    ):
        """Non-participant cannot send message."""
        client.force_login(another_student)

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=Hello!",
        )

        assert response.status_code == 403

    def test_send_file_message(
        self, client: Client, student_user, conversation
    ):
        """Participant can send file attachment."""
        client.force_login(student_user)

        file_content = b"Test file content"
        test_file = SimpleUploadedFile(
            "test.txt",
            file_content,
            content_type="text/plain",
        )

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/messages",
            {"file": test_file},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"]["file_name"] == "test.txt"
        # file_url may be None in test environment with local storage
        assert "file_url" in data["message"]

    def test_send_message_with_text_and_file(
        self, client: Client, student_user, conversation
    ):
        """Participant can send message with text and file."""
        client.force_login(student_user)

        test_file = SimpleUploadedFile(
            "document.pdf",
            b"PDF content",
            content_type="application/pdf",
        )

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/messages?content=Here%20is%20the%20document",
            {"file": test_file},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"]["content"] == "Here is the document"
        assert data["message"]["file_name"] == "document.pdf"


# =============================================================================
# Tests: List Messages
# =============================================================================


@pytest.mark.django_db
class TestListMessages:
    """Tests for GET /chat/conversations/{id}/messages."""

    def test_list_messages(
        self, client: Client, student_user, encadrant_user, conversation
    ):
        """Participant can list conversation messages."""
        # Create some messages
        Message.objects.create(
            conversation=conversation,
            sender=student_user,
            content="Hello",
        )
        Message.objects.create(
            conversation=conversation,
            sender=encadrant_user,
            content="Hi there",
        )

        client.force_login(student_user)

        response = client.get(f"/api/chat/conversations/{conversation.id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_messages_with_after_param(
        self, client: Client, student_user, encadrant_user, conversation
    ):
        """Can filter messages after a specific message ID."""
        msg1 = Message.objects.create(
            conversation=conversation,
            sender=student_user,
            content="First message",
        )
        msg2 = Message.objects.create(
            conversation=conversation,
            sender=encadrant_user,
            content="Second message",
        )

        client.force_login(student_user)

        response = client.get(
            f"/api/chat/conversations/{conversation.id}/messages?after={msg1.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "Second message"


# =============================================================================
# Tests: Group Academic Chat (Story 6.1)
# =============================================================================


@pytest.mark.django_db
class TestGroupAcademicChat:
    """Tests for POST /chat/groups/{group_id}/chat - Academic group chat."""

    def test_get_or_create_academic_chat_as_member(
        self, client: Client, student_user, closed_group_with_subject
    ):
        """Group member can access/create academic chat."""
        client.force_login(student_user)

        response = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")

        assert response.status_code == 201
        data = response.json()
        assert "TER: Groupe TER" in data["name"]
        assert data["is_group"] is True

    def test_get_or_create_academic_chat_as_professor(
        self, client: Client, encadrant_user, closed_group_with_subject
    ):
        """Professor can access/create academic chat."""
        client.force_login(encadrant_user)

        response = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")

        assert response.status_code == 201
        data = response.json()
        assert "TER: Groupe TER" in data["name"]

    def test_get_or_create_academic_chat_returns_existing(
        self, client: Client, student_user, closed_group_with_subject
    ):
        """Second call returns existing conversation (same ID)."""
        client.force_login(student_user)

        # First call creates
        response1 = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")
        assert response1.status_code == 201
        conv_id = response1.json()["id"]

        # Add a message so the second call detects it as existing
        conv = Conversation.objects.get(id=conv_id)
        Message.objects.create(
            conversation=conv,
            sender=student_user,
            content="Test message",
        )

        # Second call returns existing (with 200) since there's now a message
        response2 = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")
        assert response2.status_code == 200
        assert response2.json()["id"] == conv_id

    def test_academic_chat_non_member_denied(
        self, client: Client, another_student, closed_group_with_subject
    ):
        """Non-member cannot access academic chat."""
        # Remove another_student from group
        closed_group_with_subject.members.remove(another_student)

        client.force_login(another_student)

        response = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")

        assert response.status_code == 403

    def test_academic_chat_admin_can_access(
        self, client: Client, admin_user, closed_group_with_subject
    ):
        """Admin can access any academic chat."""
        client.force_login(admin_user)

        response = client.post(f"/api/chat/groups/{closed_group_with_subject.id}/chat")

        assert response.status_code == 201

    def test_academic_chat_requires_assigned_subject(
        self, client: Client, student_user, open_ter_period
    ):
        """Academic chat requires group to have assigned subject."""
        # Create group without subject
        group = Group.objects.create(
            name="Groupe Sans Sujet",
            leader=student_user,
            project_type="TER",
            ter_period=open_ter_period,
        )
        group.members.add(student_user)

        client.force_login(student_user)

        response = client.post(f"/api/chat/groups/{group.id}/chat")

        assert response.status_code == 400


# =============================================================================
# Tests: Messaging Permissions (can_users_message_each_other)
# =============================================================================


@pytest.mark.django_db
class TestMessagingPermissions:
    """Tests for role-based messaging permission logic."""

    def test_admin_can_message_anyone(
        self, client: Client, admin_user, student_user
    ):
        """Admin can create conversation with anyone."""
        client.force_login(admin_user)

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [str(student_user.id)], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 201

    def test_respo_ter_can_message_encadrant(
        self, client: Client, respo_ter_user, encadrant_user
    ):
        """Respo TER can message encadrants."""
        client.force_login(respo_ter_user)

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [str(encadrant_user.id)], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 201

    def test_student_can_message_professor_when_in_closed_group(
        self, client: Client, student_user, encadrant_user, closed_group_with_subject
    ):
        """Student in closed group with subject can message their professor."""
        client.force_login(student_user)

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [str(encadrant_user.id)], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 201

    def test_random_student_cannot_message_random_encadrant(
        self, client: Client, db
    ):
        """Student without relationship cannot message random professor."""
        # Create a student without any group
        random_student = User.objects.create_user(
            email="random_student@example.com",
            password="password123",
        )
        etudiant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
        random_student.groups.add(etudiant_group)

        # Create a random encadrant not linked to student
        random_encadrant = User.objects.create_user(
            email="random_prof@example.com",
            password="password123",
        )
        encadrant_group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
        random_encadrant.groups.add(encadrant_group)

        client.force_login(random_student)

        response = client.post(
            "/api/chat/conversations",
            data={"participant_ids": [str(random_encadrant.id)], "is_group": False},
            content_type="application/json",
        )

        assert response.status_code == 403


# =============================================================================
# Tests: List Users for Chat
# =============================================================================


@pytest.mark.django_db
class TestListChatUsers:
    """Tests for GET /chat/users."""

    def test_list_users_requires_auth(self, client: Client):
        """Listing users requires authentication."""
        response = client.get("/api/chat/users")
        assert response.status_code == 403

    def test_list_users_excludes_self(
        self, client: Client, student_user, another_student
    ):
        """User list excludes the requesting user."""
        client.force_login(student_user)

        response = client.get("/api/chat/users")

        assert response.status_code == 200
        data = response.json()
        user_ids = [u["id"] for u in data]
        assert str(student_user.id) not in user_ids

    def test_list_users_with_search(
        self, client: Client, student_user, another_student
    ):
        """Can search users by name."""
        client.force_login(student_user)

        response = client.get(f"/api/chat/users?search={another_student.first_name}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(u["first_name"] == another_student.first_name for u in data)
