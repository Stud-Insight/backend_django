"""
Tests for the StudentGroup model and FSM transitions.
"""

from datetime import date
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django_fsm import TransitionNotAllowed

from backend_django.groups.models import Group as StudentGroup
from backend_django.groups.models import GroupStatus
from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import PeriodStatus
from backend_django.projects.models import StagePeriod
from backend_django.projects.models import TERPeriod
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
def stage_period(db):
    """Create a Stage period for testing."""
    today = date.today()
    return StagePeriod.objects.create(
        name="Stage M2 2024-2025",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        offer_submission_start=today,
        offer_submission_end=today + timedelta(days=60),
        application_start=today + timedelta(days=30),
        application_end=today + timedelta(days=90),
        internship_start=today + timedelta(days=120),
        internship_end=today + timedelta(days=300),
    )


@pytest.fixture
def leader(db):
    """Create a group leader."""
    return UserFactory(email="leader@test.com", first_name="Leader", last_name="Student")


@pytest.fixture
def members(db):
    """Create additional group members."""
    return [
        UserFactory(email=f"member{i}@test.com", first_name=f"Member{i}", last_name="Student")
        for i in range(1, 4)
    ]


@pytest.mark.django_db
class TestTERPeriod:
    """Tests for TERPeriod model."""

    def test_create_ter_period(self, ter_period):
        """Test creating a TER period."""
        assert ter_period.name == "TER 2024-2025 S1"
        assert ter_period.academic_year == "2024-2025"
        assert ter_period.status == PeriodStatus.OPEN
        assert ter_period.min_group_size == 1
        assert ter_period.max_group_size == 4

    def test_str_representation(self, ter_period):
        """Test string representation."""
        assert str(ter_period) == "TER 2024-2025 S1 (2024-2025)"

    def test_auto_academic_year(self, db):
        """Test that academic year is auto-set if not provided."""
        today = date.today()
        period = TERPeriod.objects.create(
            name="Test Period",
            group_formation_start=today,
            group_formation_end=today + timedelta(days=30),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
        )
        assert period.academic_year != ""


@pytest.mark.django_db
class TestStagePeriod:
    """Tests for StagePeriod model."""

    def test_create_stage_period(self, stage_period):
        """Test creating a Stage period."""
        assert stage_period.name == "Stage M2 2024-2025"
        assert stage_period.academic_year == "2024-2025"
        assert stage_period.status == PeriodStatus.OPEN

    def test_str_representation(self, stage_period):
        """Test string representation."""
        assert str(stage_period) == "Stage M2 2024-2025 (2024-2025)"


@pytest.mark.django_db
class TestStudentGroup:
    """Tests for StudentGroup model."""

    def test_create_group_with_ter_period(self, ter_period, leader):
        """Test creating a student group for TER."""
        group = StudentGroup.objects.create(
            name="Team Alpha",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.name == "Team Alpha"
        assert group.leader == leader
        assert group.status == GroupStatus.OUVERT
        assert group.project_type == AcademicProjectType.SRW
        assert group.ter_period == ter_period
        assert group.stage_period is None

    def test_create_group_with_stage_period(self, stage_period, leader):
        """Test creating a student group for Stage."""
        group = StudentGroup.objects.create(
            name="Internship Team",
            leader=leader,
            project_type=AcademicProjectType.INTERNSHIP,
            stage_period=stage_period,
        )

        assert group.stage_period == stage_period
        assert group.ter_period is None

    def test_leader_added_to_members_on_save(self, ter_period, leader):
        """Test that leader is automatically added to members."""
        group = StudentGroup.objects.create(
            name="Team Beta",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.is_member(leader)
        assert group.member_count == 1

    def test_str_representation(self, ter_period, leader):
        """Test string representation."""
        group = StudentGroup.objects.create(
            name="Team Gamma",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert "Team Gamma" in str(group)
        assert "Ouvert" in str(group)

    def test_is_leader(self, ter_period, leader, members):
        """Test is_leader method."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.members.add(*members)

        assert group.is_leader(leader) is True
        assert group.is_leader(members[0]) is False

    def test_is_member(self, ter_period, leader, members):
        """Test is_member method."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.members.add(members[0])

        assert group.is_member(leader) is True
        assert group.is_member(members[0]) is True
        assert group.is_member(members[1]) is False

    def test_get_period_ter(self, ter_period, leader):
        """Test get_period returns TER period."""
        group = StudentGroup.objects.create(
            name="TER Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.get_period() == ter_period

    def test_get_period_stage(self, stage_period, leader):
        """Test get_period returns Stage period."""
        group = StudentGroup.objects.create(
            name="Stage Group",
            leader=leader,
            project_type=AcademicProjectType.INTERNSHIP,
            stage_period=stage_period,
        )

        assert group.get_period() == stage_period


@pytest.mark.django_db
class TestStudentGroupCanAddMember:
    """Tests for can_add_member method."""

    def test_can_add_member_when_open(self, ter_period, leader):
        """Test can add member when group is open."""
        group = StudentGroup.objects.create(
            name="Open Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.can_add_member() is True

    def test_cannot_add_member_when_formed(self, ter_period, leader):
        """Test cannot add member when group is formed."""
        group = StudentGroup.objects.create(
            name="Formed Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.save()

        assert group.can_add_member() is False

    def test_cannot_add_member_when_closed(self, ter_period, leader):
        """Test cannot add member when group is closed."""
        group = StudentGroup.objects.create(
            name="Closed Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.close_group()
        group.save()

        assert group.can_add_member() is False

    def test_cannot_add_member_when_max_reached(self, ter_period, leader, members):
        """Test cannot add member when max group size reached."""
        group = StudentGroup.objects.create(
            name="Full Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        # Add members to reach max (4 total with leader)
        group.members.add(*members[:3])  # 3 + leader = 4

        assert group.member_count == 4
        assert group.can_add_member() is False

    def test_stage_group_has_no_size_limit(self, stage_period, leader, members):
        """Test that Stage groups have no size limit (internships are individual)."""
        group = StudentGroup.objects.create(
            name="Stage Group",
            leader=leader,
            project_type=AcademicProjectType.INTERNSHIP,
            stage_period=stage_period,
        )
        # Add many members - should always be allowed since Stage has no limit
        group.members.add(*members)

        assert group.member_count == 4  # leader + 3 members
        assert group.can_add_member() is True  # No limit for Stage


@pytest.mark.django_db
class TestStudentGroupCanRemoveMember:
    """Tests for can_remove_member method."""

    def test_can_remove_member_when_open(self, ter_period, leader, members):
        """Test can remove member when group is open."""
        group = StudentGroup.objects.create(
            name="Open Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.members.add(members[0])

        assert group.can_remove_member(members[0]) is True

    def test_cannot_remove_leader(self, ter_period, leader):
        """Test cannot remove the leader."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.can_remove_member(leader) is False

    def test_cannot_remove_member_when_formed(self, ter_period, leader, members):
        """Test cannot remove member when group is formed."""
        group = StudentGroup.objects.create(
            name="Formed Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.members.add(members[0])
        group.form_group()
        group.save()

        assert group.can_remove_member(members[0]) is False

    def test_cannot_remove_non_member(self, ter_period, leader, members):
        """Test cannot remove someone who is not a member."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.can_remove_member(members[0]) is False

    def test_can_remove_member_from_stage_group(self, stage_period, leader, members):
        """Test can remove member from Stage group when open."""
        group = StudentGroup.objects.create(
            name="Stage Group",
            leader=leader,
            project_type=AcademicProjectType.INTERNSHIP,
            stage_period=stage_period,
        )
        group.members.add(members[0])

        assert group.can_remove_member(members[0]) is True


@pytest.mark.django_db
class TestStudentGroupFSMTransitions:
    """Tests for FSM state transitions."""

    def test_form_group_transition(self, ter_period, leader):
        """Test transitioning from ouvert to formé."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        assert group.status == GroupStatus.OUVERT

        group.form_group()
        group.save()

        assert group.status == GroupStatus.FORME

    def test_close_group_transition(self, ter_period, leader):
        """Test transitioning from formé to clôturé."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.save()

        assert group.status == GroupStatus.FORME

        group.close_group()
        group.save()

        assert group.status == GroupStatus.CLOTURE

    def test_reopen_group_transition(self, ter_period, leader):
        """Test transitioning from formé back to ouvert."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.save()

        assert group.status == GroupStatus.FORME

        group.reopen_group()
        group.save()

        assert group.status == GroupStatus.OUVERT

    def test_cannot_form_already_formed_group(self, ter_period, leader):
        """Test cannot transition from formé to formé."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.save()

        with pytest.raises(TransitionNotAllowed):
            group.form_group()

    def test_cannot_close_open_group(self, ter_period, leader):
        """Test cannot transition directly from ouvert to clôturé."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )

        with pytest.raises(TransitionNotAllowed):
            group.close_group()

    def test_cannot_reopen_closed_group(self, ter_period, leader):
        """Test cannot reopen a closed group."""
        group = StudentGroup.objects.create(
            name="Test Group",
            leader=leader,
            project_type=AcademicProjectType.SRW,
            ter_period=ter_period,
        )
        group.form_group()
        group.close_group()
        group.save()

        with pytest.raises(TransitionNotAllowed):
            group.reopen_group()


@pytest.mark.django_db
class TestStudentGroupConstraints:
    """Tests for database constraints."""

    def test_must_have_either_ter_or_stage_period(self, ter_period, stage_period, leader):
        """Test that group must have exactly one period type."""
        # This should fail - both periods set
        with pytest.raises(IntegrityError):
            StudentGroup.objects.create(
                name="Invalid Group",
                leader=leader,
                project_type=AcademicProjectType.SRW,
                ter_period=ter_period,
                stage_period=stage_period,
            )

    def test_must_have_at_least_one_period(self, leader):
        """Test that group must have at least one period."""
        with pytest.raises(IntegrityError):
            StudentGroup.objects.create(
                name="Invalid Group",
                leader=leader,
                project_type=AcademicProjectType.SRW,
            )
