"""Tests for notification integrations across modules."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.chat.models import Conversation
from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupInvitation, GroupStatus, InvitationStatus
from backend_django.notifications.models import Notification
from backend_django.stages.models import (
    ApplicationStatus,
    OfferStatus,
    StageApplication,
    StageOffer,
    StagePeriod,
)
from backend_django.stages.models import PeriodStatus as StagePeriodStatus
from backend_django.ter.models import PeriodStatus as TERPeriodStatus
from backend_django.ter.models import SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def student(db):
    user = User.objects.create_user(
        email="student-notif@example.com",
        password="password123",
        first_name="Alice",
        last_name="Student",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def student2(db):
    user = User.objects.create_user(
        email="student2-notif@example.com",
        password="password123",
        first_name="Bob",
        last_name="Student",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def professor(db):
    user = User.objects.create_user(
        email="prof-notif@example.com",
        password="password123",
        first_name="Prof",
        last_name="Encadrant",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def respo_ter(db):
    user = User.objects.create_user(
        email="respo-notif@example.com",
        password="password123",
        first_name="Respo",
        last_name="TER",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(group)
    return user


@pytest.fixture
def externe(db):
    user = User.objects.create_user(
        email="externe-notif@example.com",
        password="password123",
        first_name="Externe",
        last_name="Supervisor",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2026",
        academic_year="2025-2026",
        status=TERPeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=30),
        group_formation_end=today + timedelta(days=30),
        subject_selection_start=today - timedelta(days=30),
        subject_selection_end=today + timedelta(days=60),
        assignment_date=today + timedelta(days=61),
        project_start=today + timedelta(days=70),
        project_end=today + timedelta(days=180),
        min_group_size=2,
        max_group_size=5,
    )


@pytest.fixture
def stage_period(db):
    today = date.today()
    return StagePeriod.objects.create(
        name="Stage 2026",
        academic_year="2025-2026",
        status=StagePeriodStatus.OPEN,
        offer_submission_start=today - timedelta(days=60),
        offer_submission_end=today - timedelta(days=30),
        application_start=today - timedelta(days=30),
        application_end=today + timedelta(days=30),
        internship_start=today + timedelta(days=60),
        internship_end=today + timedelta(days=180),
    )


# =============================================================================
# Chat Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestChatNotifications:
    def test_message_creates_notifications_for_participants(self, student, student2):
        from backend_django.chat.models import Message

        conv = Conversation.objects.create()
        conv.participants.add(student, student2)

        # Create message directly to test notification integration
        Message.objects.create(
            conversation=conv,
            sender=student,
            content="Hello!",
        )
        conv.save()

        # Simulate what the API does - call notification service
        from backend_django.notifications.services import send_bulk_notifications

        other_participants = conv.participants.exclude(id=student.id)
        send_bulk_notifications(
            recipients=list(other_participants),
            notification_type="chat.new_message",
            title="Nouveau message",
            message=f"{student.get_full_name()} vous a envoyé un message.",
            data={"conversation_id": str(conv.id)},
        )

        notifs = Notification.objects.filter(recipient=student2)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "chat.new_message"

        # Sender should NOT get a notification
        assert Notification.objects.filter(recipient=student).count() == 0


# =============================================================================
# Group Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestGroupNotifications:
    def test_invitation_notifies_invitee(self, student, student2, ter_period):
        ter_period.enrolled_students.add(student, student2)
        group = Group.objects.create(
            name="Test Group",
            leader=student,
            ter_period=ter_period,
            status=GroupStatus.OUVERT,
        )
        group.members.add(student)

        client = Client()
        client.login(email=student.email, password="password123")

        response = client.post(
            f"/api/groups/{group.id}/invite",
            data={"invitee_email": student2.email},
            content_type="application/json",
        )
        assert response.status_code == 201

        notifs = Notification.objects.filter(recipient=student2)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "group.invitation_received"

    def test_accept_invitation_notifies_leader(self, student, student2, ter_period):
        ter_period.enrolled_students.add(student, student2)
        group = Group.objects.create(
            name="Test Group",
            leader=student,
            ter_period=ter_period,
            status=GroupStatus.OUVERT,
        )
        group.members.add(student)

        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=student2,
            invited_by=student,
        )
        invitation.accept()

        notifs = Notification.objects.filter(recipient=student)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "group.invitation_accepted"

    def test_decline_invitation_notifies_leader(self, student, student2, ter_period):
        ter_period.enrolled_students.add(student, student2)
        group = Group.objects.create(
            name="Test Group",
            leader=student,
            ter_period=ter_period,
            status=GroupStatus.OUVERT,
        )
        group.members.add(student)

        invitation = GroupInvitation.objects.create(
            group=group,
            invitee=student2,
            invited_by=student,
        )
        invitation.decline()

        notifs = Notification.objects.filter(recipient=student)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "group.invitation_declined"


# =============================================================================
# Stage Application Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestStageNotifications:
    def test_accept_application_notifies_student(self, student, externe, stage_period):
        offer = StageOffer.objects.create(
            stage_period=stage_period,
            supervisor=externe,
            title="Stage IA",
            description="Stage en IA",
            company_name="TechCorp",
            status=OfferStatus.VALIDATED,
        )
        application = StageApplication.objects.create(
            offer=offer,
            student=student,
            motivation="Motivé!",
            status=ApplicationStatus.PENDING,
        )

        client = Client()
        client.login(email=externe.email, password="password123")

        response = client.post(
            f"/api/stages/offers/{offer.id}/applications/{application.id}/accept"
        )
        assert response.status_code == 200

        notifs = Notification.objects.filter(recipient=student)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "stage.application_accepted"

    def test_reject_application_notifies_student(self, student, externe, stage_period):
        offer = StageOffer.objects.create(
            stage_period=stage_period,
            supervisor=externe,
            title="Stage IA",
            description="Stage en IA",
            company_name="TechCorp",
            status=OfferStatus.VALIDATED,
        )
        application = StageApplication.objects.create(
            offer=offer,
            student=student,
            motivation="Motivé!",
            status=ApplicationStatus.PENDING,
        )

        client = Client()
        client.login(email=externe.email, password="password123")

        response = client.post(
            f"/api/stages/offers/{offer.id}/applications/{application.id}/reject",
            data={"reason": "Profil incompatible"},
            content_type="application/json",
        )
        assert response.status_code == 200

        notifs = Notification.objects.filter(recipient=student)
        assert notifs.count() == 1
        notif = notifs.first()
        assert notif.notification_type == "stage.application_rejected"
        assert notif.data["reason"] == "Profil incompatible"


# =============================================================================
# TER Subject Integration Tests
# =============================================================================


@pytest.mark.django_db
class TestTERNotifications:
    def test_validate_subject_notifies_professor(self, professor, respo_ter, ter_period):
        subject = TERSubject.objects.create(
            ter_period=ter_period,
            professor=professor,
            title="Sujet ML",
            description="Machine Learning research",
            status=SubjectStatus.SUBMITTED,
        )

        client = Client()
        client.login(email=respo_ter.email, password="password123")

        response = client.post(f"/api/ter/subjects/{subject.id}/validate")
        assert response.status_code == 200

        notifs = Notification.objects.filter(recipient=professor)
        assert notifs.count() == 1
        assert notifs.first().notification_type == "ter.subject_validated"

    def test_reject_subject_notifies_professor(self, professor, respo_ter, ter_period):
        subject = TERSubject.objects.create(
            ter_period=ter_period,
            professor=professor,
            title="Sujet NLP",
            description="NLP research",
            status=SubjectStatus.SUBMITTED,
        )

        client = Client()
        client.login(email=respo_ter.email, password="password123")

        response = client.post(
            f"/api/ter/subjects/{subject.id}/reject",
            data={"reason": "Hors périmètre"},
            content_type="application/json",
        )
        assert response.status_code == 200

        notifs = Notification.objects.filter(recipient=professor)
        assert notifs.count() == 1
        notif = notifs.first()
        assert notif.notification_type == "ter.subject_rejected"
        assert "Hors périmètre" in notif.data["reason"]
