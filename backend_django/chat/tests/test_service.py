"""
Tests for Chat Service Functions - Epic 6 Permission Logic.

Tests for role-based messaging permissions and academic chat creation.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Group as DjangoGroup

from backend_django.chat.api.service import (
    can_users_message_each_other,
    get_or_create_academic_chat,
    get_role_data,
)
from backend_django.chat.models import Conversation
from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import PeriodStatus, SubjectStatus, TERPeriod, TERSubject
from backend_django.users.models import User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def student(db):
    """Create a student user."""
    user = User.objects.create_user(
        email="student@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def another_student(db):
    """Create another student user."""
    user = User.objects.create_user(
        email="student2@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def encadrant(db):
    """Create an encadrant (professor) user."""
    user = User.objects.create_user(
        email="prof@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def admin(db):
    """Create an admin user."""
    user = User.objects.create_user(
        email="admin@test.com",
        password="password123",
        is_staff=True,
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ADMIN.value)
    user.groups.add(group)
    return user


@pytest.fixture
def respo_ter(db):
    """Create a Respo TER user."""
    user = User.objects.create_user(
        email="respo_ter@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(group)
    return user


@pytest.fixture
def respo_stage(db):
    """Create a Respo Stage user."""
    user = User.objects.create_user(
        email="respo_stage@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_STAGE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def externe(db):
    """Create an externe user."""
    user = User.objects.create_user(
        email="externe@test.com",
        password="password123",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.EXTERNE.value)
    user.groups.add(group)
    return user


@pytest.fixture
def ter_period(db):
    """Create a TER period."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025",
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
def ter_subject(db, ter_period, encadrant):
    """Create a TER subject."""
    return TERSubject.objects.create(
        ter_period=ter_period,
        title="Sujet Test",
        description="Description du sujet de test avec au moins cinquante caracteres.",
        domain="IA",
        professor=encadrant,
        status=SubjectStatus.VALIDATED,
        max_groups=2,
    )


@pytest.fixture
def closed_ter_group(db, student, another_student, ter_period, ter_subject):
    """Create a closed TER group with subject."""
    group = Group.objects.create(
        name="Groupe TER Test",
        leader=student,
        project_type="TER",
        ter_period=ter_period,
        assigned_subject=ter_subject,
    )
    group.members.add(student, another_student)
    Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)
    # Re-fetch from DB to get updated status (avoids FSM __set__ restriction)
    return Group.objects.get(pk=group.pk)


# =============================================================================
# Tests: get_role_data
# =============================================================================


@pytest.mark.django_db
class TestGetRoleData:
    """Tests for get_role_data function."""

    def test_get_role_data_admin(self, admin):
        """Admin role data is correct."""
        data = get_role_data(admin)
        assert data["is_admin"] is True
        assert data["is_encadrant"] is False
        assert data["is_etudiant"] is False

    def test_get_role_data_student(self, student):
        """Student role data is correct."""
        data = get_role_data(student)
        assert data["is_etudiant"] is True
        assert data["is_admin"] is False
        assert data["is_encadrant"] is False

    def test_get_role_data_encadrant(self, encadrant):
        """Encadrant role data is correct."""
        data = get_role_data(encadrant)
        assert data["is_encadrant"] is True
        assert data["is_admin"] is False
        assert data["is_etudiant"] is False

    def test_get_role_data_respo_ter(self, respo_ter):
        """Respo TER role data is correct."""
        data = get_role_data(respo_ter)
        assert data["is_respo_ter"] is True
        assert data["is_respo_stage"] is False

    def test_get_role_data_respo_stage(self, respo_stage):
        """Respo Stage role data is correct."""
        data = get_role_data(respo_stage)
        assert data["is_respo_stage"] is True
        assert data["is_respo_ter"] is False


# =============================================================================
# Tests: can_users_message_each_other
# =============================================================================


@pytest.mark.django_db
class TestCanUsersMessageEachOther:
    """Tests for can_users_message_each_other function."""

    # Admin bypass tests
    def test_admin_can_message_anyone(self, admin, student):
        """Admin can message any user."""
        assert can_users_message_each_other(admin, student) is True
        assert can_users_message_each_other(student, admin) is True

    def test_admin_can_message_encadrant(self, admin, encadrant):
        """Admin can message encadrant."""
        assert can_users_message_each_other(admin, encadrant) is True

    # Respo TER tests
    def test_respo_ter_can_message_encadrant(self, respo_ter, encadrant):
        """Respo TER can message encadrant."""
        assert can_users_message_each_other(respo_ter, encadrant) is True
        assert can_users_message_each_other(encadrant, respo_ter) is True

    def test_respo_ter_can_message_ter_student(self, respo_ter, student, ter_period):
        """Respo TER can message student in TER group."""
        # Create TER group with student
        group = Group.objects.create(
            name="TER Group",
            leader=student,
            project_type="TER",
            ter_period=ter_period,
        )
        group.members.add(student)

        assert can_users_message_each_other(respo_ter, student) is True

    def test_respo_ter_cannot_message_stage_student(self, respo_ter, student, ter_period):
        """Respo TER cannot message student only in Stage group."""
        # Create Stage group with student (no TER group)
        group = Group.objects.create(
            name="Stage Group",
            leader=student,
            project_type="Stage",
            ter_period=ter_period,
        )
        group.members.add(student)

        assert can_users_message_each_other(respo_ter, student) is False

    def test_respo_ter_cannot_message_externe(self, respo_ter, externe):
        """Respo TER cannot message externe."""
        assert can_users_message_each_other(respo_ter, externe) is False

    # Respo Stage tests
    def test_respo_stage_can_message_externe(self, respo_stage, externe):
        """Respo Stage can message externe."""
        assert can_users_message_each_other(respo_stage, externe) is True
        assert can_users_message_each_other(externe, respo_stage) is True

    def test_respo_stage_can_message_stage_student(self, respo_stage, student, ter_period):
        """Respo Stage can message student in Stage group."""
        # Create Stage group with student
        group = Group.objects.create(
            name="Stage Group",
            leader=student,
            project_type="Stage",
            ter_period=ter_period,
        )
        group.members.add(student)

        assert can_users_message_each_other(respo_stage, student) is True

    def test_respo_stage_cannot_message_ter_student(self, respo_stage, student, ter_period):
        """Respo Stage cannot message student only in TER group."""
        # Create TER group with student (no Stage group)
        group = Group.objects.create(
            name="TER Group",
            leader=student,
            project_type="TER",
            ter_period=ter_period,
        )
        group.members.add(student)

        assert can_users_message_each_other(respo_stage, student) is False

    def test_respo_stage_cannot_message_encadrant(self, respo_stage, encadrant):
        """Respo Stage cannot message encadrant (TER role)."""
        assert can_users_message_each_other(respo_stage, encadrant) is False

    # Student-Professor messaging in closed groups
    def test_student_can_message_professor_in_closed_group(
        self, student, encadrant, closed_ter_group
    ):
        """Student in closed TER group can message their professor."""
        assert can_users_message_each_other(student, encadrant) is True
        assert can_users_message_each_other(encadrant, student) is True

    def test_student_cannot_message_unrelated_professor(self, student, db):
        """Student cannot message professor not linked to their group."""
        # Create unrelated professor
        other_prof = User.objects.create_user(
            email="other_prof@test.com",
            password="password123",
        )
        group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
        other_prof.groups.add(group)

        assert can_users_message_each_other(student, other_prof) is False

    def test_student_cannot_message_other_student(self, student, another_student):
        """Students cannot directly message each other."""
        # Without any special relationship
        assert can_users_message_each_other(student, another_student) is False

    # Edge cases
    def test_same_user_cannot_message_self(self, student):
        """Technically checking same user returns False (no relationship)."""
        assert can_users_message_each_other(student, student) is False


# =============================================================================
# Tests: get_or_create_academic_chat
# =============================================================================


@pytest.mark.django_db
class TestGetOrCreateAcademicChat:
    """Tests for get_or_create_academic_chat function."""

    def test_creates_academic_chat(self, closed_ter_group):
        """Creates new conversation for group."""
        conv = get_or_create_academic_chat(closed_ter_group)

        assert conv is not None
        assert conv.is_group is True
        assert "TER: Groupe TER Test" in conv.name
        assert conv.participants.count() == 3  # 2 students + 1 professor

    def test_returns_existing_chat(self, closed_ter_group):
        """Returns existing conversation on second call."""
        conv1 = get_or_create_academic_chat(closed_ter_group)
        conv2 = get_or_create_academic_chat(closed_ter_group)

        assert conv1.id == conv2.id

    def test_returns_none_without_subject(self, student, ter_period):
        """Returns None if group has no assigned subject."""
        group = Group.objects.create(
            name="No Subject Group",
            leader=student,
            project_type="TER",
            ter_period=ter_period,
        )
        group.members.add(student)

        conv = get_or_create_academic_chat(group)

        assert conv is None

    def test_returns_none_without_professor(self, student, ter_period, db):
        """Returns None if subject has no professor."""
        # Create subject without professor
        subject = TERSubject.objects.create(
            ter_period=ter_period,
            title="Sujet Sans Prof",
            description="Description du sujet sans professeur avec cinquante caracteres minimum.",
            domain="IA",
            professor=None,
            status=SubjectStatus.VALIDATED,
            max_groups=2,
        )

        group = Group.objects.create(
            name="No Prof Group",
            leader=student,
            project_type="TER",
            ter_period=ter_period,
            assigned_subject=subject,
        )
        group.members.add(student)

        conv = get_or_create_academic_chat(group)

        assert conv is None

    def test_chat_includes_all_participants(self, closed_ter_group, encadrant, student, another_student):
        """Academic chat includes all group members and professor."""
        conv = get_or_create_academic_chat(closed_ter_group)

        participant_ids = set(conv.participants.values_list("id", flat=True))
        assert student.id in participant_ids
        assert another_student.id in participant_ids
        assert encadrant.id in participant_ids
