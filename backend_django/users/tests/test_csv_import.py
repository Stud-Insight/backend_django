"""
Tests for CSV user import endpoint.
"""

import io

import pytest
from django.contrib.auth.models import Group
from django.test import Client

from backend_django.core.roles import Role
from backend_django.users.models import User


@pytest.fixture
def staff_user(db):
    """Create a staff user."""
    user = User.objects.create_user(
        email="staff@test.fr",
        password="testpass123",
        first_name="Staff",
        last_name="User",
        is_active=True,
        is_staff=True,
    )
    return user


@pytest.fixture
def regular_user(db):
    """Create a regular user."""
    user = User.objects.create_user(
        email="user@test.fr",
        password="testpass123",
        first_name="Regular",
        last_name="User",
        is_active=True,
    )
    return user


@pytest.fixture
def etudiant_group(db):
    """Create the Etudiant role group."""
    group, _ = Group.objects.get_or_create(name=Role.ETUDIANT.value)
    return group


@pytest.fixture
def staff_client(staff_user):
    """Client authenticated as staff user."""
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def regular_client(regular_user):
    """Client authenticated as regular user."""
    client = Client()
    client.force_login(regular_user)
    return client


def create_csv_file(content: str) -> io.BytesIO:
    """Create a CSV file-like object from string content."""
    file = io.BytesIO(content.encode("utf-8"))
    file.name = "students.csv"
    return file


@pytest.mark.django_db
class TestCSVImportEndpoint:
    """Tests for POST /api/users/import-csv."""

    def test_staff_can_import_csv(self, staff_client, etudiant_group):
        """Test staff can import users from CSV."""
        csv_content = """email,first_name,last_name
student1@test.fr,Jean,Dupont
student2@test.fr,Marie,Martin
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["created_count"] == 2
        assert data["skipped_count"] == 0
        assert data["error_count"] == 0

        # Verify users were created
        assert User.objects.filter(email="student1@test.fr").exists()
        assert User.objects.filter(email="student2@test.fr").exists()

        # Verify user attributes
        user1 = User.objects.get(email="student1@test.fr")
        assert user1.first_name == "Jean"
        assert user1.last_name == "Dupont"
        assert user1.is_active is False  # Requires activation

        # Verify Etudiant role assigned
        assert etudiant_group in user1.groups.all()

    def test_import_with_french_column_names(self, staff_client, etudiant_group):
        """Test import with French column names (prenom, nom)."""
        csv_content = """email,prenom,nom
student@test.fr,Pierre,Durand
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created_count"] == 1

        user = User.objects.get(email="student@test.fr")
        assert user.first_name == "Pierre"
        assert user.last_name == "Durand"

    def test_import_skips_existing_users(self, staff_client, etudiant_group):
        """Test that existing users are skipped."""
        # Create existing user
        User.objects.create_user(
            email="existing@test.fr",
            password="test123",
            first_name="Existing",
            is_active=True,
        )

        csv_content = """email,first_name,last_name
existing@test.fr,New,Name
new@test.fr,New,User
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created_count"] == 1
        assert data["skipped_count"] == 1

        # Existing user unchanged
        existing = User.objects.get(email="existing@test.fr")
        assert existing.first_name == "Existing"

    def test_import_with_missing_email_column(self, staff_client):
        """Test error when email column is missing."""
        csv_content = """first_name,last_name
Jean,Dupont
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

        data = response.json()
        assert data["code"] == "MISSING_COLUMN"
        assert "email" in data["message"]

    def test_import_with_missing_first_name_column(self, staff_client):
        """Test error when first_name/prenom column is missing."""
        csv_content = """email,last_name
student@test.fr,Dupont
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

        data = response.json()
        assert data["code"] == "MISSING_COLUMN"
        assert "first_name" in data["message"] or "prenom" in data["message"]

    def test_import_with_invalid_email_format(self, staff_client, etudiant_group):
        """Test that invalid email formats are reported as errors."""
        csv_content = """email,first_name,last_name
invalid-email,Jean,Dupont
valid@test.fr,Marie,Martin
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert data["created_count"] == 1
        assert data["error_count"] == 1
        assert data["errors"][0]["line"] == 2
        assert data["errors"][0]["email"] == "invalid-email"
        assert "email" in data["errors"][0]["error"].lower()

    def test_import_with_missing_email_value(self, staff_client, etudiant_group):
        """Test that missing email values are reported as errors."""
        csv_content = """email,first_name,last_name
,Jean,Dupont
valid@test.fr,Marie,Martin
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created_count"] == 1
        assert data["error_count"] == 1
        assert data["errors"][0]["line"] == 2
        assert "manquant" in data["errors"][0]["error"].lower()

    def test_import_with_missing_first_name_value(self, staff_client, etudiant_group):
        """Test that missing first_name values are reported as errors."""
        csv_content = """email,first_name,last_name
student@test.fr,,Dupont
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["error_count"] == 1
        assert "prénom" in data["errors"][0]["error"].lower()

    def test_import_without_last_name(self, staff_client, etudiant_group):
        """Test that last_name is optional."""
        csv_content = """email,first_name,last_name
student@test.fr,Jean,
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created_count"] == 1

        user = User.objects.get(email="student@test.fr")
        assert user.last_name == ""

    def test_regular_user_cannot_import(self, regular_client):
        """Test that non-staff users cannot import CSV."""
        csv_content = """email,first_name,last_name
student@test.fr,Jean,Dupont
"""
        response = regular_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = regular_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 403

    def test_unauthenticated_cannot_import(self, client):
        """Test that unauthenticated users cannot import CSV."""
        csv_content = """email,first_name,last_name
student@test.fr,Jean,Dupont
"""
        response = client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        # Controller has IsStaff permission, unauthenticated gets 403
        assert response.status_code == 403

    def test_import_empty_csv(self, staff_client):
        """Test error on empty CSV file."""
        csv_content = ""

        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 400

        data = response.json()
        assert data["code"] == "INVALID_CSV"

    def test_import_trims_whitespace(self, staff_client, etudiant_group):
        """Test that whitespace is trimmed from values."""
        csv_content = """email,first_name,last_name
  student@test.fr  ,  Jean  ,  Dupont
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created_count"] == 1

        user = User.objects.get(email="student@test.fr")
        assert user.first_name == "Jean"
        assert user.last_name == "Dupont"

    def test_import_case_insensitive_email_check(self, staff_client, etudiant_group):
        """Test that email duplicate check is case-insensitive."""
        # Create existing user with uppercase email
        User.objects.create_user(
            email="EXISTING@test.fr",
            password="test123",
            first_name="Existing",
            is_active=True,
        )

        csv_content = """email,first_name,last_name
existing@test.fr,New,Name
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["skipped_count"] == 1
        assert data["created_count"] == 0

    def test_import_returns_created_users_list(self, staff_client, etudiant_group):
        """Test that response includes list of created users."""
        csv_content = """email,first_name,last_name
student@test.fr,Jean,Dupont
"""
        response = staff_client.get("/api/auth/csrf")
        csrf_token = response.json()["csrf_token"]

        response = staff_client.post(
            "/api/users/import-csv",
            data={"file": create_csv_file(csv_content)},
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["created_users"]) == 1
        assert data["created_users"][0]["email"] == "student@test.fr"
        assert data["created_users"][0]["first_name"] == "Jean"
        assert "id" in data["created_users"][0]
