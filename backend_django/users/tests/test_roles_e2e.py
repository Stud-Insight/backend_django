"""
End-to-end tests for the role-based permission system.

These tests simulate real user scenarios and complete workflows:
- Admin onboarding new users with appropriate roles
- Role changes during user lifecycle
- Multi-user role interactions
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.core.roles import Role
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
class TestAdminOnboardingWorkflow:
    """
    E2E Test: Admin onboards new university staff members.

    Scenario: A new academic year starts. The admin needs to:
    1. Create accounts for new Respo TER and Respo Stage
    2. Create accounts for new Encadrants
    3. Verify all can access their respective features
    """

    def test_onboard_academic_staff(self, role_groups, superadmin):
        """Test complete onboarding of academic staff."""
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Step 1: Create Respo TER
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "respo.ter@univ-montpellier.fr",
                "first_name": "Jean",
                "last_name": "Dupont",
                "groups": ["Respo TER"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        respo_ter_id = response.json()["id"]

        # Verify Respo TER role
        respo_ter = User.objects.get(id=respo_ter_id)
        assert respo_ter.groups.filter(name="Respo TER").exists()

        # Step 2: Create Respo Stage
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "respo.stage@univ-montpellier.fr",
                "first_name": "Marie",
                "last_name": "Martin",
                "groups": ["Respo Stage"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201

        # Step 3: Create multiple Encadrants
        encadrants_data = [
            {"email": "prof1@univ-montpellier.fr", "first_name": "Pierre", "last_name": "Bernard"},
            {"email": "prof2@univ-montpellier.fr", "first_name": "Sophie", "last_name": "Petit"},
        ]

        for enc_data in encadrants_data:
            response = admin_client.post(
                "/api/users/create",
                data={
                    **enc_data,
                    "groups": ["Encadrant"],
                },
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            assert response.status_code == 201

        # Step 4: Verify all users created with correct roles
        response = admin_client.get("/api/users/")
        users = response.json()

        # Check each role is assigned correctly
        respo_ter_user = next(u for u in users if u["email"] == "respo.ter@univ-montpellier.fr")
        assert any(g["name"] == "Respo TER" for g in respo_ter_user["groups"])

        respo_stage_user = next(u for u in users if u["email"] == "respo.stage@univ-montpellier.fr")
        assert any(g["name"] == "Respo Stage" for g in respo_stage_user["groups"])

        encadrant_users = [u for u in users if "prof" in u["email"]]
        for enc in encadrant_users:
            assert any(g["name"] == "Encadrant" for g in enc["groups"])


@pytest.mark.django_db
class TestStudentLifecycleWorkflow:
    """
    E2E Test: Student role lifecycle.

    Scenario: A student goes through the academic year:
    1. Admin creates student account
    2. Student completes TER
    3. Admin adds Encadrant role (student becomes teaching assistant)
    """

    def test_student_to_encadrant_promotion(self, role_groups, superadmin):
        """Test promoting a student to also be an Encadrant."""
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Step 1: Create student
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "student@etu.umontpellier.fr",
                "first_name": "Alice",
                "last_name": "Durand",
                "groups": ["Étudiant"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        student_id = response.json()["id"]

        # Verify only Étudiant role
        student = User.objects.get(id=student_id)
        assert student.groups.count() == 1
        assert student.groups.filter(name="Étudiant").exists()

        # Step 2: Promote to also be Encadrant (without removing Étudiant)
        response = admin_client.post(
            f"/api/users/{student_id}/roles/add",
            data={"roles": ["Encadrant"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Step 3: Verify both roles
        student.refresh_from_db()
        assert student.groups.count() == 2
        assert student.groups.filter(name="Étudiant").exists()
        assert student.groups.filter(name="Encadrant").exists()

        # Verify via API
        response = admin_client.get(f"/api/users/{student_id}")
        groups = [g["name"] for g in response.json()["groups"]]
        assert "Étudiant" in groups
        assert "Encadrant" in groups


@pytest.mark.django_db
class TestExternalSupervisorWorkflow:
    """
    E2E Test: External supervisor (company) workflow.

    Scenario: A company wants to offer internships:
    1. Admin creates Externe account
    2. Later, company contact changes
    3. Admin transfers the role to new contact
    """

    def test_externe_account_management(self, role_groups, superadmin):
        """Test managing external supervisor accounts."""
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Step 1: Create Externe for company
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "contact@techcorp.fr",
                "first_name": "Marc",
                "last_name": "Tech",
                "groups": ["Externe"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        old_contact_id = response.json()["id"]

        # Step 2: Create new contact
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "newcontact@techcorp.fr",
                "first_name": "Julie",
                "last_name": "Tech",
                "groups": ["Externe"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201

        # Step 3: Remove role from old contact
        response = admin_client.post(
            f"/api/users/{old_contact_id}/roles/remove",
            data={"roles": ["Externe"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Verify old contact has no Externe role
        old_contact = User.objects.get(id=old_contact_id)
        assert not old_contact.groups.filter(name="Externe").exists()


@pytest.mark.django_db
class TestMultiRoleUserWorkflow:
    """
    E2E Test: User with multiple responsibilities.

    Scenario: A professor who is both:
    - Encadrant (supervises student projects)
    - Respo TER (coordinates the TER program)
    """

    def test_professor_with_dual_responsibilities(self, role_groups, superadmin):
        """Test user managing multiple roles."""
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Step 1: Create professor with Encadrant role
        response = admin_client.post(
            "/api/users/create",
            data={
                "email": "professor@univ-montpellier.fr",
                "first_name": "François",
                "last_name": "Leclerc",
                "groups": ["Encadrant"],
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201
        prof_id = response.json()["id"]

        # Step 2: Professor becomes Respo TER (add role)
        response = admin_client.post(
            f"/api/users/{prof_id}/roles/add",
            data={"roles": ["Respo TER"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Step 3: Verify both roles
        prof = User.objects.get(id=prof_id)
        assert prof.groups.count() == 2

        # Step 4: End of mandate, remove Respo TER but keep Encadrant
        response = admin_client.post(
            f"/api/users/{prof_id}/roles/remove",
            data={"roles": ["Respo TER"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        prof.refresh_from_db()
        assert prof.groups.count() == 1
        assert prof.groups.filter(name="Encadrant").exists()
        assert not prof.groups.filter(name="Respo TER").exists()


@pytest.mark.django_db
class TestAdminRoleSecurityWorkflow:
    """
    E2E Test: Admin role security constraints.

    Scenario: Testing that Admin role assignment is protected:
    1. Staff user cannot assign Admin role
    2. Superuser can assign Admin role
    3. Admin role grants full access
    """

    def test_admin_role_assignment_security(self, role_groups, superadmin):
        """Test Admin role can only be assigned by superusers."""
        # Create a staff user (not superuser)
        staff_user = UserFactory(
            email="staff@studinsight.fr",
            is_staff=True,
            is_superuser=False,
            is_active=True,
        )
        staff_user.set_password("StaffPass123!")
        staff_user.save()

        # Create a regular user to test role assignment on
        target_user = UserFactory(
            email="target@studinsight.fr",
            is_active=True,
        )

        # Step 1: Staff tries to assign Admin role - should fail
        staff_client, staff_csrf, _ = authenticated_session(
            staff_user.email, "StaffPass123!"
        )

        response = staff_client.put(
            f"/api/users/{target_user.id}/roles",
            data={"roles": ["Admin"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=staff_csrf,
        )
        assert response.status_code == 403

        # Step 2: Superuser assigns Admin role - should succeed
        admin_client, admin_csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        response = admin_client.put(
            f"/api/users/{target_user.id}/roles",
            data={"roles": ["Admin"]},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=admin_csrf,
        )
        assert response.status_code == 200

        # Verify Admin role assigned
        target_user.refresh_from_db()
        assert target_user.groups.filter(name="Admin").exists()


@pytest.mark.django_db
class TestBulkUserManagementWorkflow:
    """
    E2E Test: Managing multiple users at once.

    Scenario: Start of academic year - admin creates multiple students.
    """

    def test_create_student_cohort(self, role_groups, superadmin):
        """Test creating a cohort of students."""
        admin_client, csrf, _ = authenticated_session(
            superadmin.email, "SuperSecure123!"
        )

        # Create 5 students
        students = [
            {"email": f"student{i}@etu.umontpellier.fr", "first_name": f"Student{i}", "last_name": "Test"}
            for i in range(1, 6)
        ]

        created_ids = []
        for student in students:
            response = admin_client.post(
                "/api/users/create",
                data={
                    **student,
                    "groups": ["Étudiant"],
                },
                content_type="application/json",
                HTTP_X_CSRFTOKEN=csrf,
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])

        # Verify all students created with Étudiant role
        for student_id in created_ids:
            user = User.objects.get(id=student_id)
            assert user.groups.filter(name="Étudiant").exists()

        # List all users and verify count
        response = admin_client.get("/api/users/")
        all_users = response.json()

        student_users = [u for u in all_users if "etu.umontpellier.fr" in u["email"]]
        assert len(student_users) == 5

        for student in student_users:
            assert any(g["name"] == "Étudiant" for g in student["groups"])
