"""
End-to-end tests for RGPD compliance workflows.

These tests simulate complete user scenarios:
- User requesting and receiving their data export
- Admin processing account deletion requests
- RGPD deletion workflow with data anonymization
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.chat.models import Conversation
from backend_django.chat.models import Message
from backend_django.core.roles import Role
from backend_django.projects.models import AcademicProject
from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import Proposal
from backend_django.projects.models import ProposalApplication
from backend_django.users.models import User
from backend_django.users.tests.factories import UserFactory


@pytest.fixture
def role_groups(db):
    """Create all role groups."""
    groups = {}
    for role in Role:
        groups[role] = Group.objects.get_or_create(name=role.value)[0]
    return groups


@pytest.fixture
def superadmin(db):
    """Create the main superadmin user."""
    user = UserFactory(
        email="superadmin@studinsight.fr",
        first_name="Super",
        last_name="Admin",
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    user.set_password("SuperSecure123!")
    user.save()
    return user


def authenticated_session(email, password):
    """Create an authenticated session and return client with CSRF token."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]

    login_response = client.post(
        "/api/auth/login",
        data={"email": email, "password": password},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    return client, csrf_token, login_response


@pytest.mark.django_db
class TestUserDataExportWorkflow:
    """
    E2E Test: User requests and receives their personal data.

    Scenario: A student wants to see all data Stud'Insight has about them:
    1. Student logs in
    2. Student requests data export
    3. Student receives comprehensive JSON with all their data
    """

    def test_student_exports_complete_data(self, role_groups, superadmin):
        """Test complete data export workflow for a student."""
        from datetime import date

        # Setup: Create student with various data
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Create student via admin
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "alice@etu.umontpellier.fr",
                "first_name": "Alice",
                "last_name": "Étudiant",
                "groups": ["Étudiant"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        student_id = response.json()["id"]

        # Get the student and set password
        student = User.objects.get(id=student_id)
        student.set_password("StudentPass123!")
        student.is_active = True
        student.save()

        # Create some project data for the student
        supervisor = UserFactory(is_active=True)
        AcademicProject.objects.create(
            student=student,
            supervisor=supervisor,
            subject="Machine Learning pour la détection de fraude",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
            description="Projet de TER sur le ML",
        )

        # Create a conversation with messages
        conversation = Conversation.objects.create(name="Discussion TER")
        conversation.participants.add(student, supervisor)
        Message.objects.create(
            conversation=conversation,
            sender=student,
            content="Bonjour, j'ai une question sur le projet.",
        )

        # Create a proposal application
        proposal = Proposal.objects.create(
            title="Autre sujet intéressant",
            description="Description du sujet",
            project_type=AcademicProjectType.SRW,
            created_by=supervisor,
            academic_year="2024-2025",
        )
        ProposalApplication.objects.create(
            proposal=proposal,
            applicant=student,
            motivation="Je suis très motivé",
        )

        # Step 1: Student logs in and exports data
        student_client, student_csrf, _ = authenticated_session(
            student.email, "StudentPass123!"
        )

        response = student_client.get("/api/rgpd/export")
        assert response.status_code == 200

        data = response.json()["data"]

        # Verify profile
        assert data["profile"]["email"] == "alice@etu.umontpellier.fr"
        assert data["profile"]["first_name"] == "Alice"

        # Verify groups
        assert len(data["groups"]) == 1
        assert data["groups"][0]["name"] == "Étudiant"

        # Verify projects
        assert len(data["projects_as_student"]) == 1
        assert "Machine Learning" in data["projects_as_student"][0]["subject"]

        # Verify conversations
        assert len(data["conversations"]) == 1
        assert len(data["conversations"][0]["messages"]) == 1

        # Verify applications
        assert len(data["proposal_applications"]) == 1
        assert data["proposal_applications"][0]["motivation"] == "Je suis très motivé"


@pytest.mark.django_db
class TestAccountDeletionWorkflow:
    """
    E2E Test: Admin processes RGPD account deletion.

    Scenario: A user requests account deletion and admin processes it:
    1. User requests deletion
    2. Admin exports user data (for record)
    3. Admin confirms deletion
    4. All personal data is anonymized
    5. Academic records preserved but anonymized
    """

    def test_complete_rgpd_deletion_workflow(self, role_groups, superadmin):
        """Test complete RGPD deletion workflow."""
        from datetime import date

        # Setup: Create user with comprehensive data
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Create user
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "todelete@example.com",
                "first_name": "Jean",
                "last_name": "Supprime",
                "groups": ["Étudiant", "Encadrant"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        user_id = response.json()["id"]

        user = User.objects.get(id=user_id)
        user.set_password("ToDelete123!")
        user.is_active = True
        user.save()

        # Create project where user is student
        project = AcademicProject.objects.create(
            student=user,
            subject="Projet à conserver",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
        )
        project_id = project.id

        # Create conversations
        other_user = UserFactory(is_active=True)
        conversation = Conversation.objects.create(is_group=True, name="Group chat")
        conversation.participants.add(user, other_user)
        Message.objects.create(
            conversation=conversation,
            sender=user,
            content="Message original",
        )

        # Step 1: User requests deletion
        user_client, user_csrf, _ = authenticated_session(
            user.email, "ToDelete123!"
        )

        response = user_client.post(
            "/api/rgpd/request-deletion",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=user_csrf,
        )
        assert response.status_code == 200
        assert "30 jours" in response.json()["message"]

        # Step 2: Admin exports user data first (for records/backup)
        response = admin_client.get(f"/api/users/{user_id}/rgpd/export")
        assert response.status_code == 200
        exported_data = response.json()["data"]
        assert exported_data["profile"]["email"] == "todelete@example.com"

        # Step 3: Admin confirms deletion
        response = admin_client.post(
            f"/api/users/{user_id}/rgpd/delete",
            data={"confirm": True, "reason": "RGPD deletion request"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        result = response.json()
        assert result["success"] is True
        assert "@deleted.studinsight.local" in result["anonymized_email"]
        assert "profile_anonymized" in result["actions"]

        # Step 4: Verify anonymization
        user.refresh_from_db()
        assert user.first_name == "Utilisateur"
        assert user.last_name == "Supprimé"
        assert user.is_active is False
        assert user.groups.count() == 0

        # Step 5: Verify academic records preserved
        project = AcademicProject.objects.get(id=project_id)
        assert project.subject == "Projet à conserver"  # Subject preserved
        assert project.student_id == user.id  # Link preserved (user is anonymized)

        # Verify messages anonymized
        message = Message.objects.filter(conversation=conversation, sender=user).first()
        assert message.content == "[Message supprimé - Compte RGPD]"


@pytest.mark.django_db
class TestDeletionProtectionWorkflow:
    """
    E2E Test: Protection against unauthorized deletions.

    Scenario: Various protection mechanisms:
    1. Staff cannot delete superuser
    2. Users cannot delete other users
    3. Confirmation is required
    """

    def test_protection_against_unauthorized_deletion(self, role_groups, superadmin):
        """Test that various protection mechanisms work."""
        # Create a staff user (non-superuser)
        staff = UserFactory(
            email="staff@studinsight.fr",
            is_staff=True,
            is_superuser=False,
            is_active=True,
        )
        staff.set_password("StaffPass123!")
        staff.save()

        # Create a regular user
        regular = UserFactory(
            email="regular@studinsight.fr",
            is_staff=False,
            is_active=True,
        )
        regular.set_password("RegularPass123!")
        regular.save()

        # Test 1: Staff cannot delete superuser
        staff_client, staff_csrf, _ = authenticated_session(
            staff.email, "StaffPass123!"
        )

        response = staff_client.post(
            f"/api/users/{superadmin.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=staff_csrf,
        )
        assert response.status_code == 403

        # Test 2: Regular user cannot delete others
        regular_client, regular_csrf, _ = authenticated_session(
            regular.email, "RegularPass123!"
        )

        response = regular_client.post(
            f"/api/users/{staff.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=regular_csrf,
        )
        assert response.status_code == 403

        # Test 3: Confirmation required
        admin_client, admin_csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        response = admin_client.post(
            f"/api/users/{regular.id}/rgpd/delete",
            data={"confirm": False},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=admin_csrf,
        )
        assert response.status_code == 400

        # Test 4: With confirmation, deletion succeeds
        response = admin_client.post(
            f"/api/users/{regular.id}/rgpd/delete",
            data={"confirm": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=admin_csrf,
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestMultiRoleUserDeletionWorkflow:
    """
    E2E Test: Deletion of user with multiple roles and relationships.

    Scenario: A professor who is Encadrant and Respo TER gets deleted:
    1. Their projects as referent/supervisor should be cleared
    2. Their proposals should be preserved (but linked to anonymized user)
    3. All roles should be removed
    """

    def test_multi_role_user_deletion(self, role_groups, superadmin):
        """Test deletion of user with multiple roles."""
        from datetime import date

        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Create professor with multiple roles
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "prof@univ-montpellier.fr",
                "first_name": "Professeur",
                "last_name": "ToDelete",
                "groups": ["Encadrant", "Respo TER"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        prof_id = response.json()["id"]

        prof = User.objects.get(id=prof_id)
        prof.is_active = True
        prof.save()

        # Create student for the project
        student = UserFactory(is_active=True)

        # Create project where prof is supervisor
        project = AcademicProject.objects.create(
            student=student,
            supervisor=prof,
            subject="Projet supervisé",
            project_type=AcademicProjectType.SRW,
            start_date=date.today(),
            end_date=date.today(),
        )

        # Create proposal by prof
        proposal = Proposal.objects.create(
            title="Sujet proposé",
            description="Description",
            project_type=AcademicProjectType.SRW,
            created_by=prof,
            supervisor=prof,
            academic_year="2024-2025",
        )

        # Delete professor
        response = admin_client.post(
            f"/api/users/{prof_id}/rgpd/delete",
            data={"confirm": True, "reason": "Professor leaving"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Verify roles removed
        prof.refresh_from_db()
        assert prof.groups.count() == 0

        # Verify project supervisor cleared
        project.refresh_from_db()
        assert project.supervisor is None
        assert project.student == student  # Student preserved

        # Verify proposal preserved but linked to anonymized user
        proposal.refresh_from_db()
        assert proposal.created_by_id == prof.id  # Still linked
        assert proposal.supervisor is None  # Cleared
        assert proposal.title == "Sujet proposé"  # Content preserved
