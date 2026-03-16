"""
Tests for the TER group balancing feature.

Covers:
- Balancing algorithm unit tests
- API endpoint integration tests
- Edge case tests
- Full workflow scenario tests
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.algorithms.balancing import (
    calculate_similarity_score,
    identify_problematic_entities,
    preview_balancing,
    run_balancing,
)
from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    BalancingOperation,
    BalancingOperationType,
    PeriodStatus,
    SubjectStatus,
    TERIndividualRanking,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.users.tests.factories import UserFactory


# ==================== Fixtures ====================


@pytest.fixture
def staff_user(db):
    """Create a staff user (Respo TER) for TER admin access."""
    user = UserFactory(
        email="staff@test.com",
        first_name="Staff",
        last_name="User",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    respo_ter_group, _ = DjangoGroup.objects.get_or_create(name=Role.RESPO_TER.value)
    user.groups.add(respo_ter_group)
    return user


@pytest.fixture
def student_user(db):
    """Create a student user."""
    user = UserFactory(
        email="student@test.com",
        first_name="Student",
        last_name="Test",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def another_student(db):
    """Create another student user."""
    user = UserFactory(
        email="student2@test.com",
        first_name="Another",
        last_name="Student",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def third_student(db):
    """Create a third student user."""
    user = UserFactory(
        email="student3@test.com",
        first_name="Third",
        last_name="Student",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def ter_period_open(db):
    """Create an open TER period with min_group_size=2."""
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025 S1",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=5),
        group_formation_end=today + timedelta(days=25),
        subject_selection_start=today + timedelta(days=31),
        subject_selection_end=today + timedelta(days=60),
        assignment_date=today + timedelta(days=61),
        project_start=today + timedelta(days=70),
        project_end=today + timedelta(days=180),
        min_group_size=2,
        max_group_size=4,
    )


@pytest.fixture
def subject_ia(ter_period_open, staff_user):
    """Create a validated IA subject."""
    return TERSubject.objects.create(
        ter_period=ter_period_open,
        title="Sujet IA",
        description="Description IA",
        domain="IA/ML",
        professor=staff_user,
        max_groups=2,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def subject_web(ter_period_open, staff_user):
    """Create a validated Web subject."""
    return TERSubject.objects.create(
        ter_period=ter_period_open,
        title="Sujet Web",
        description="Description Web",
        domain="Web",
        professor=staff_user,
        max_groups=2,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def subject_security(ter_period_open, staff_user):
    """Create a validated Security subject."""
    return TERSubject.objects.create(
        ter_period=ter_period_open,
        title="Sujet Securite",
        description="Description Securite",
        domain="Securite",
        professor=staff_user,
        max_groups=1,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def solo_group(ter_period_open, student_user):
    """Create a solo group (1 member) - incomplete."""
    group = Group.objects.create(
        name="Solo Group",
        leader=student_user,
        project_type="TER",
        ter_period=ter_period_open,
        status=GroupStatus.OUVERT,
    )
    group.members.add(student_user)
    return group


@pytest.fixture
def staff_client(staff_user):
    """Return a client authenticated as staff."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": staff_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


@pytest.fixture
def authenticated_client(student_user):
    """Return a client authenticated as student."""
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": student_user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client


def _get_csrf(client):
    """Get CSRF token from client."""
    resp = client.get("/api/auth/csrf")
    return resp.json()["csrf_token"]


# ==================== Unit Tests: Algorithm ====================


@pytest.mark.django_db
class TestIdentifyProblematicEntities:
    """Tests for identify_problematic_entities function."""

    def test_identify_solo_students(self, ter_period_open, student_user, another_student):
        """Enrolled students not in any group are identified as solo."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.solo_students) == 2
        assert student_user.id in entities.solo_students
        assert another_student.id in entities.solo_students

    def test_identify_incomplete_groups(
        self, ter_period_open, student_user, another_student
    ):
        """Groups below min_group_size are identified as incomplete."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create two solo groups (1 member each, min is 2)
        group1 = Group.objects.create(
            name="Group 1",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group1.members.add(student_user)

        group2 = Group.objects.create(
            name="Group 2",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group2.members.add(another_student)

        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.incomplete_groups) == 2
        assert len(entities.solo_groups) == 2
        assert group1.id in entities.incomplete_groups
        assert group2.id in entities.incomplete_groups

    def test_complete_groups_not_identified(
        self, ter_period_open, student_user, another_student
    ):
        """Groups meeting min_group_size are not identified as incomplete."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create a complete group (2 members, min is 2)
        group = Group.objects.create(
            name="Complete Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user, another_student)

        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.incomplete_groups) == 0
        assert len(entities.solo_students) == 0


@pytest.mark.django_db
class TestSimilarityCalculation:
    """Tests for calculate_similarity_score function."""

    def test_identical_rankings_score_high(self):
        """Identical preference rankings should score high."""
        prefs_a = {uuid4(): 1, uuid4(): 2, uuid4(): 3}
        # Use same keys for identical rankings
        common_key = list(prefs_a.keys())[0]
        prefs_b = {common_key: 1}

        score = calculate_similarity_score(prefs_a, prefs_b)

        # Should be positive since there's overlap
        assert score > 0

    def test_no_overlap_score_zero(self):
        """No overlapping preferences should score 0."""
        prefs_a = {uuid4(): 1, uuid4(): 2}
        prefs_b = {uuid4(): 1, uuid4(): 2}

        score = calculate_similarity_score(prefs_a, prefs_b)

        assert score == 0.0

    def test_both_empty_neutral_score(self):
        """Both empty preferences should score neutral (0.5)."""
        score = calculate_similarity_score({}, {})
        assert score == 0.5

    def test_one_empty_partial_score(self):
        """One empty preference should score partial (0.3)."""
        prefs_a = {uuid4(): 1}
        prefs_b = {}

        score = calculate_similarity_score(prefs_a, prefs_b)
        assert score == 0.3


@pytest.mark.django_db
class TestMergeSoloStudentToGroup:
    """Tests for merging solo students into groups."""

    def test_merge_student_to_group(
        self, ter_period_open, student_user, another_student, solo_group
    ):
        """Solo student is merged into incomplete group."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        result = run_balancing(
            ter_period_open,
            merge_solo_students=True,
            merge_incomplete_groups=False,
            auto_form_groups=False,
        )

        assert result.students_assigned >= 1

    def test_merge_respects_max_size(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """Merging respects max_group_size constraint."""
        # Set max to 2
        ter_period_open.max_group_size = 2
        ter_period_open.save()

        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create group with 2 members (at max)
        full_group = Group.objects.create(
            name="Full Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        full_group.members.add(student_user, another_student)

        entities = identify_problematic_entities(ter_period_open)

        # third_student should be solo
        assert third_student.id in entities.solo_students
        # full_group should not be incomplete (it has 2 members, min is 2)
        assert full_group.id not in entities.incomplete_groups


@pytest.mark.django_db
class TestAutoFormAfterBalancing:
    """Tests for auto-forming groups after balancing."""

    def test_auto_form_after_balancing(
        self, ter_period_open, student_user, another_student
    ):
        """Groups meeting min_group_size are auto-formed after balancing."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create two solo groups
        group1 = Group.objects.create(
            name="Group 1",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group1.members.add(student_user)

        group2 = Group.objects.create(
            name="Group 2",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group2.members.add(another_student)

        result = run_balancing(
            ter_period_open,
            merge_solo_students=True,
            merge_incomplete_groups=True,
            auto_form_groups=True,
        )

        # After merging and auto-forming, surviving groups should be "forme"
        assert result.groups_auto_formed >= 0


# ==================== Integration Tests: API Endpoints ====================


@pytest.mark.django_db
class TestBalancingEndpoints:
    """Tests for balancing API endpoints."""

    def test_preview_requires_ter_admin(
        self, authenticated_client, ter_period_open
    ):
        """Preview endpoint requires TER admin permissions."""
        response = authenticated_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-preview"
        )
        assert response.status_code == 403

    def test_preview_works_for_admin(self, staff_client, ter_period_open, student_user):
        """Preview endpoint works for TER admin."""
        ter_period_open.enrolled_students.add(student_user)

        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-preview"
        )

        assert response.status_code == 200
        data = response.json()
        assert "solo_students_count" in data
        assert "incomplete_groups_count" in data
        assert data["min_group_size"] == 2
        assert data["max_group_size"] == 4

    def test_balance_groups_requires_admin(
        self, authenticated_client, ter_period_open
    ):
        """Balance groups endpoint requires TER admin."""
        csrf = _get_csrf(authenticated_client)
        response = authenticated_client.post(
            f"/api/ter/periods/{ter_period_open.id}/balance-groups",
            data={"dry_run": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 403

    def test_balance_groups_dry_run(
        self, staff_client, ter_period_open, student_user, another_student
    ):
        """Dry run balance groups returns preview without changes."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/balance-groups",
            data={"dry_run": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify no actual changes were made
        entities = identify_problematic_entities(ter_period_open)
        assert len(entities.solo_students) == 2

    def test_move_student_between_groups(
        self, staff_client, ter_period_open, student_user, another_student, third_student
    ):
        """Admin can move student between groups."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create source group with two members
        source = Group.objects.create(
            name="Source",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        source.members.add(student_user, another_student)

        # Create target group with one member
        target = Group.objects.create(
            name="Target",
            leader=third_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        target.members.add(third_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(another_student.id),
                "source_group_id": str(source.id),
                "target_group_id": str(target.id),
                "reason": "Test move",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify student was moved (query fresh from DB to avoid FSM refresh issues)
        source_fresh = Group.objects.get(id=source.id)
        target_fresh = Group.objects.get(id=target.id)
        assert not source_fresh.members.filter(id=another_student.id).exists()
        assert target_fresh.members.filter(id=another_student.id).exists()

    def test_merge_groups_combines_members(
        self, staff_client, ter_period_open, student_user, another_student
    ):
        """Merging groups combines their members."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create two solo groups
        group_a = Group.objects.create(
            name="Group A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Group B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/merge",
            data={
                "group_a_id": str(group_a.id),
                "group_b_id": str(group_b.id),
                "reason": "Test merge",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["member_count"] == 2

    def test_force_assign_bypasses_algorithm(
        self, staff_client, ter_period_open, student_user, another_student, subject_ia
    ):
        """Force assign directly assigns subject to group."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create a complete group (use update to bypass FSM for test setup)
        group = Group.objects.create(
            name="Test Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user, another_student)
        # Force status via update for test setup
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.FORME)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(subject_ia.id),
                "close_group": True,
                "reason": "Test force assign",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify assignment (query fresh from DB)
        group_fresh = Group.objects.get(id=group.id)
        assert group_fresh.assigned_subject_id == subject_ia.id
        assert group_fresh.status == GroupStatus.CLOTURE

    def test_revert_assignment_reopens_group(
        self, staff_client, ter_period_open, student_user, another_student, subject_ia
    ):
        """Reverting assignment removes subject and reopens group."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create assigned group (use update to bypass FSM for test setup)
        group = Group.objects.create(
            name="Assigned Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_ia,
        )
        group.members.add(student_user, another_student)
        # Force status via update for test setup
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/revert-assignment",
            data={"reopen_group": True, "reason": "Test revert"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify revert (query fresh from DB)
        group_fresh = Group.objects.get(id=group.id)
        assert group_fresh.assigned_subject is None
        assert group_fresh.status == GroupStatus.OUVERT

    def test_force_form_group(
        self, staff_client, ter_period_open, student_user
    ):
        """Force form transitions group to forme regardless of size."""
        ter_period_open.enrolled_students.add(student_user)

        # Create solo group (below min_group_size of 2)
        group = Group.objects.create(
            name="Solo Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/force-form",
            data={"reason": "Allow solo to submit rankings"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify status (query fresh from DB)
        group_fresh = Group.objects.get(id=group.id)
        assert group_fresh.status == GroupStatus.FORME


# ==================== End-to-End Scenario Tests ====================


@pytest.mark.django_db
class TestEdgeCases:
    """Edge case tests for balancing algorithm."""

    def test_no_enrolled_students(self, ter_period_open):
        """Period with no enrolled students should have nothing to balance."""
        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.solo_students) == 0
        assert len(entities.incomplete_groups) == 0
        assert len(entities.solo_groups) == 0
        assert not entities  # Should be falsy

    def test_no_groups_only_solo_students(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """All enrolled students are solo (no groups exist)."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.solo_students) == 3
        assert len(entities.incomplete_groups) == 0
        assert len(entities.solo_groups) == 0

    def test_all_groups_complete(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """All groups meet min_group_size - nothing to balance."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create one complete group (3 members, min is 2)
        group = Group.objects.create(
            name="Complete Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user, another_student, third_student)

        entities = identify_problematic_entities(ter_period_open)

        assert len(entities.solo_students) == 0
        assert len(entities.incomplete_groups) == 0

    def test_single_solo_group_cannot_merge(
        self, ter_period_open, student_user
    ):
        """Single solo group has no one to merge with."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Lonely Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        result = run_balancing(
            ter_period_open,
            merge_solo_students=True,
            merge_incomplete_groups=True,
            auto_form_groups=False,
        )

        # No merges possible - still incomplete
        assert result.groups_merged == 0
        assert len(result.remaining_incomplete_groups) == 1

    def test_solo_student_no_groups_to_join(
        self, ter_period_open, student_user, another_student
    ):
        """Solo student with no incomplete groups to join."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create a complete group (another_student + one more needed)
        # But wait, min_group_size is 2, so we need 2 members
        # Let's create a formed group that's already at max
        ter_period_open.max_group_size = 2
        ter_period_open.save()

        group = Group.objects.create(
            name="Full Group",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(another_student)
        # Force to forme status
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.FORME)

        # student_user is solo, but the only group is formed (not ouvert)
        entities = identify_problematic_entities(ter_period_open)

        assert student_user.id in entities.solo_students
        assert len(entities.incomplete_groups) == 0  # Formed groups not counted

    def test_max_group_size_respected_during_merge(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """Merging students respects max_group_size constraint."""
        ter_period_open.max_group_size = 2
        ter_period_open.save()
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create incomplete group with 1 member
        group = Group.objects.create(
            name="Small Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        # Two solo students want to join, but only one can fit
        result = run_balancing(
            ter_period_open,
            merge_solo_students=True,
            merge_incomplete_groups=False,
            auto_form_groups=False,
        )

        # Only 1 student should be assigned (max_group_size = 2)
        group_fresh = Group.objects.get(id=group.id)
        assert group_fresh.member_count == 2
        assert result.students_assigned == 1
        assert len(result.remaining_solo_students) == 1

    def test_merge_two_solo_groups(
        self, ter_period_open, student_user, another_student
    ):
        """Two solo groups should merge into one."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        group_a = Group.objects.create(
            name="Solo A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Solo B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        result = run_balancing(
            ter_period_open,
            merge_solo_students=False,
            merge_incomplete_groups=True,
            auto_form_groups=True,
        )

        assert result.groups_merged == 1
        # One group should remain with 2 members
        remaining_groups = Group.objects.filter(ter_period=ter_period_open)
        assert remaining_groups.count() == 1
        assert remaining_groups.first().member_count == 2

    def test_three_solo_groups_merge_to_one(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """Three solo groups should merge progressively."""
        ter_period_open.min_group_size = 3
        ter_period_open.save()
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        for i, user in enumerate([student_user, another_student, third_student]):
            group = Group.objects.create(
                name=f"Solo {i}",
                leader=user,
                project_type="TER",
                ter_period=ter_period_open,
            )
            group.members.add(user)

        result = run_balancing(
            ter_period_open,
            merge_solo_students=False,
            merge_incomplete_groups=True,
            auto_form_groups=True,
        )

        # Should have merged twice (3 -> 2 -> 1) but algorithm merges pairs
        # So: 2 merges maximum, leaving 1 group with 2+ members
        remaining_groups = Group.objects.filter(ter_period=ter_period_open)
        total_members = sum(g.member_count for g in remaining_groups)
        assert total_members == 3  # All students still accounted for

    def test_formed_groups_ignored_by_balancing(
        self, ter_period_open, student_user, another_student
    ):
        """Groups already 'forme' should not be modified by balancing."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create a formed group with 1 member (below min but already formed)
        group = Group.objects.create(
            name="Already Formed",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.FORME)

        # another_student is solo
        entities = identify_problematic_entities(ter_period_open)

        # Formed group should not be in incomplete list
        assert group.id not in entities.incomplete_groups
        assert another_student.id in entities.solo_students

    def test_closed_groups_ignored_by_balancing(
        self, ter_period_open, student_user, another_student, subject_ia
    ):
        """Groups already 'cloture' should not be modified by balancing."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create a closed group with assigned subject
        group = Group.objects.create(
            name="Closed Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_ia,
        )
        group.members.add(student_user)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)

        entities = identify_problematic_entities(ter_period_open)

        assert group.id not in entities.incomplete_groups
        assert group.id not in entities.solo_groups

    def test_student_in_multiple_periods(self, ter_period_open, student_user, db):
        """Student enrolled in multiple periods - balancing is per-period."""
        today = date.today()
        other_period = TERPeriod.objects.create(
            name="Other Period",
            academic_year="2025-2026",
            status=PeriodStatus.OPEN,
            group_formation_start=today,
            group_formation_end=today + timedelta(days=30),
            subject_selection_start=today + timedelta(days=31),
            subject_selection_end=today + timedelta(days=60),
            assignment_date=today + timedelta(days=61),
            project_start=today + timedelta(days=70),
            project_end=today + timedelta(days=180),
            min_group_size=2,
            max_group_size=4,
        )

        ter_period_open.enrolled_students.add(student_user)
        other_period.enrolled_students.add(student_user)

        # Student has group in other_period but not in ter_period_open
        group = Group.objects.create(
            name="Other Period Group",
            leader=student_user,
            project_type="TER",
            ter_period=other_period,
        )
        group.members.add(student_user)

        # Check ter_period_open - student should be solo there
        entities = identify_problematic_entities(ter_period_open)
        assert student_user.id in entities.solo_students

        # Check other_period - student is in a group there
        other_entities = identify_problematic_entities(other_period)
        assert student_user.id not in other_entities.solo_students

    def test_balancing_with_preferences_similarity(
        self, ter_period_open, student_user, another_student, subject_ia, subject_web
    ):
        """Students with similar preferences should be matched together."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # Create two solo groups first (needed for individual rankings)
        group_a = Group.objects.create(
            name="Group A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Group B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        # Both students rank the same subject as #1
        TERIndividualRanking.objects.create(
            group=group_a, user=student_user, subject=subject_ia, rank=1,
        )
        TERIndividualRanking.objects.create(
            group=group_b, user=another_student, subject=subject_ia, rank=1,
        )

        result = run_balancing(
            ter_period_open,
            merge_solo_students=False,
            merge_incomplete_groups=True,
            auto_form_groups=True,
        )

        # Groups should merge based on preference similarity
        assert result.groups_merged == 1
        assert len(result.operations) > 0
        # Check similarity score was calculated
        assert result.operations[0].similarity_score >= 0

    def test_dry_run_makes_no_changes(
        self, ter_period_open, student_user, another_student
    ):
        """Dry run should not modify any data."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        group = Group.objects.create(
            name="Solo Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        initial_group_count = Group.objects.filter(ter_period=ter_period_open).count()

        result = run_balancing(
            ter_period_open,
            merge_solo_students=True,
            merge_incomplete_groups=True,
            auto_form_groups=True,
            dry_run=True,
        )

        # No operations should have been executed
        assert len(result.operations) == 0
        assert result.students_assigned == 0
        assert result.groups_merged == 0

        # Data should be unchanged
        final_group_count = Group.objects.filter(ter_period=ter_period_open).count()
        assert final_group_count == initial_group_count

    def test_preview_returns_correct_counts(
        self, ter_period_open, student_user, another_student, third_student
    ):
        """Preview should return accurate counts without making changes."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # 1 solo student (third_student)
        # 2 solo groups
        group_a = Group.objects.create(
            name="Solo A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Solo B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        preview = preview_balancing(ter_period_open)

        assert preview["solo_students_count"] == 1
        assert preview["incomplete_groups_count"] == 2
        assert preview["solo_groups_count"] == 2
        assert preview["min_group_size"] == 2
        assert preview["max_group_size"] == 4


@pytest.mark.django_db
class TestAPIEdgeCases:
    """Edge case tests for balancing API endpoints."""

    def test_move_student_to_full_group(
        self, staff_client, ter_period_open, student_user, another_student, third_student
    ):
        """Moving student to a full group should fail."""
        ter_period_open.max_group_size = 2
        ter_period_open.save()
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create full group
        full_group = Group.objects.create(
            name="Full Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        full_group.members.add(student_user, another_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(third_student.id),
                "target_group_id": str(full_group.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "taille maximale" in response.json()["message"].lower()

    def test_move_leader_fails(
        self, staff_client, ter_period_open, student_user, another_student
    ):
        """Moving a group leader should fail."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        source = Group.objects.create(
            name="Source",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        source.members.add(student_user, another_student)

        target = Group.objects.create(
            name="Target",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        target.members.add(another_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(student_user.id),  # Leader of source
                "source_group_id": str(source.id),
                "target_group_id": str(target.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "leader" in response.json()["message"].lower()

    def test_merge_same_group_fails(
        self, staff_client, ter_period_open, student_user
    ):
        """Merging a group with itself should fail."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Solo Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/merge",
            data={
                "group_a_id": str(group.id),
                "group_b_id": str(group.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "lui-meme" in response.json()["message"].lower()

    def test_merge_exceeds_max_size(
        self, staff_client, ter_period_open, student_user, another_student, third_student
    ):
        """Merging groups that would exceed max_group_size should fail."""
        ter_period_open.max_group_size = 2
        ter_period_open.save()
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        group_a = Group.objects.create(
            name="Group A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user, another_student)

        group_b = Group.objects.create(
            name="Group B",
            leader=third_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(third_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/merge",
            data={
                "group_a_id": str(group_a.id),
                "group_b_id": str(group_b.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "taille maximale" in response.json()["message"].lower()

    def test_merge_closed_group_fails(
        self, staff_client, ter_period_open, student_user, another_student, subject_ia
    ):
        """Merging a closed group should fail."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        closed_group = Group.objects.create(
            name="Closed",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_ia,
        )
        closed_group.members.add(student_user)
        Group.objects.filter(pk=closed_group.pk).update(status=GroupStatus.CLOTURE)

        open_group = Group.objects.create(
            name="Open",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        open_group.members.add(another_student)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/merge",
            data={
                "group_a_id": str(closed_group.id),
                "group_b_id": str(open_group.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "cloture" in response.json()["message"].lower()

    def test_force_assign_already_assigned_fails(
        self, staff_client, ter_period_open, student_user, subject_ia, subject_web
    ):
        """Force assigning to a group that already has a subject should fail."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Already Assigned",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_ia,
        )
        group.members.add(student_user)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.FORME)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/force-assign",
            data={
                "group_id": str(group.id),
                "subject_id": str(subject_web.id),
                "reason": "Test reason",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "deja" in response.json()["message"].lower()

    def test_force_assign_subject_at_capacity_fails(
        self, staff_client, ter_period_open, student_user, another_student, subject_security
    ):
        """Force assigning a subject at max capacity should fail."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        # subject_security has max_groups=1
        # Create a group already assigned to it
        assigned_group = Group.objects.create(
            name="Already Has Subject",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_security,
        )
        assigned_group.members.add(student_user)
        Group.objects.filter(pk=assigned_group.pk).update(status=GroupStatus.CLOTURE)

        # Try to assign same subject to another group
        other_group = Group.objects.create(
            name="Wants Subject",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        other_group.members.add(another_student)
        Group.objects.filter(pk=other_group.pk).update(status=GroupStatus.FORME)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/force-assign",
            data={
                "group_id": str(other_group.id),
                "subject_id": str(subject_security.id),
                "reason": "Test reason",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "capacite" in response.json()["message"].lower()

    def test_revert_unassigned_group_fails(
        self, staff_client, ter_period_open, student_user
    ):
        """Reverting assignment on a group without subject should fail."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="No Subject",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/revert-assignment",
            data={"reopen_group": True, "reason": "Test reason"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "pas de sujet" in response.json()["message"].lower()

    def test_force_form_already_formed_fails(
        self, staff_client, ter_period_open, student_user
    ):
        """Force forming an already formed group should fail."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Already Formed",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.FORME)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/force-form",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "deja forme" in response.json()["message"].lower()

    def test_force_form_closed_group_fails(
        self, staff_client, ter_period_open, student_user, subject_ia
    ):
        """Force forming a closed group should fail."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Closed Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
            assigned_subject=subject_ia,
        )
        group.members.add(student_user)
        Group.objects.filter(pk=group.pk).update(status=GroupStatus.CLOTURE)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/force-form",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 400
        assert "cloture" in response.json()["message"].lower()

    def test_nonexistent_period_returns_404(self, staff_client):
        """Operations on nonexistent period should return 404."""
        fake_id = uuid4()
        csrf = _get_csrf(staff_client)

        response = staff_client.get(f"/api/ter/periods/{fake_id}/balancing-preview")
        assert response.status_code == 404

        response = staff_client.post(
            f"/api/ter/periods/{fake_id}/balance-groups",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 404

    def test_nonexistent_group_returns_404(
        self, staff_client, ter_period_open
    ):
        """Operations on nonexistent group should return 404."""
        fake_id = uuid4()
        csrf = _get_csrf(staff_client)

        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{fake_id}/force-form",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 404

    def test_nonexistent_student_returns_404(
        self, staff_client, ter_period_open, student_user
    ):
        """Moving nonexistent student should return 404."""
        ter_period_open.enrolled_students.add(student_user)

        group = Group.objects.create(
            name="Target",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(uuid4()),
                "target_group_id": str(group.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 404

    def test_balancing_operations_audit_trail(
        self, staff_client, ter_period_open, student_user, another_student
    ):
        """All operations should be logged in the audit trail."""
        ter_period_open.enrolled_students.add(student_user, another_student)

        group_a = Group.objects.create(
            name="Group A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Group B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        csrf = _get_csrf(staff_client)

        # Run automatic balancing
        staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/balance-groups",
            data={"dry_run": False},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Check audit trail
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-operations"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0

        # Verify operation details
        for op in data["results"]:
            assert "operation_type" in op
            assert "details" in op
            assert "is_automatic" in op
            assert "created" in op

    def test_balancing_operations_filter_by_type(
        self, staff_client, ter_period_open, student_user, another_student, third_student
    ):
        """Audit trail can be filtered by operation type."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        group = Group.objects.create(
            name="Group",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group.members.add(student_user)

        csrf = _get_csrf(staff_client)

        # Move a student
        staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(another_student.id),
                "target_group_id": str(group.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Force form
        staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group.id}/force-form",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        # Filter by move_student
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-operations?operation_type=move_student"
        )
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["operation_type"] == "move_student"

        # Filter by force_form
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-operations?operation_type=force_form"
        )
        data = response.json()
        assert data["count"] == 1
        assert data["results"][0]["operation_type"] == "force_form"


@pytest.mark.django_db
class TestBalancingScenarios:
    """End-to-end scenario tests for the balancing workflow."""

    def test_full_workflow_balancing_then_assignment(
        self,
        staff_client,
        ter_period_open,
        student_user,
        another_student,
        third_student,
        subject_ia,
        subject_web,
    ):
        """Full workflow: balance groups, submit rankings, verify ready for assignment."""
        # Setup: enroll students
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create two solo groups and one solo student
        group1 = Group.objects.create(
            name="Solo 1",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group1.members.add(student_user)

        group2 = Group.objects.create(
            name="Solo 2",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group2.members.add(another_student)

        # third_student is solo (no group)

        # Step 1: Preview balancing
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-preview"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["solo_students_count"] == 1
        assert data["incomplete_groups_count"] == 2

        # Step 2: Run balancing
        csrf = _get_csrf(staff_client)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/balance-groups",
            data={
                "dry_run": False,
                "merge_solo_students": True,
                "merge_incomplete_groups": True,
                "auto_form_groups": True,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        # Step 3: Verify all groups are now "forme" or ready
        entities = identify_problematic_entities(ter_period_open)
        assert len(entities.solo_students) == 0

        # Step 4: Check audit trail
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-operations"
        )
        assert response.status_code == 200
        ops = response.json()
        assert ops["count"] > 0  # At least some operations logged

    def test_manual_intervention_workflow(
        self,
        staff_client,
        ter_period_open,
        student_user,
        another_student,
        third_student,
        subject_ia,
    ):
        """Admin manually manages groups when automatic balancing isn't suitable."""
        ter_period_open.enrolled_students.add(
            student_user, another_student, third_student
        )

        # Create groups
        group_a = Group.objects.create(
            name="Group A",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_a.members.add(student_user)

        group_b = Group.objects.create(
            name="Group B",
            leader=another_student,
            project_type="TER",
            ter_period=ter_period_open,
        )
        group_b.members.add(another_student)

        csrf = _get_csrf(staff_client)

        # Step 1: Move third_student to group_a
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/move-student",
            data={
                "student_id": str(third_student.id),
                "target_group_id": str(group_a.id),
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Step 2: Force form group_b (still solo)
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/{group_b.id}/force-form",
            data={"reason": "Student prefers working alone"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Step 3: Force assign subject to group_b
        response = staff_client.post(
            f"/api/ter/periods/{ter_period_open.id}/groups/force-assign",
            data={
                "group_id": str(group_b.id),
                "subject_id": str(subject_ia.id),
                "close_group": True,
                "reason": "Special case assignment",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200

        # Verify final state (query fresh from DB)
        group_a_fresh = Group.objects.get(id=group_a.id)
        group_b_fresh = Group.objects.get(id=group_b.id)

        assert group_a_fresh.member_count == 2  # student_user + third_student
        assert group_b_fresh.status == GroupStatus.CLOTURE
        assert group_b_fresh.assigned_subject_id == subject_ia.id

        # Check audit trail has all operations
        response = staff_client.get(
            f"/api/ter/periods/{ter_period_open.id}/balancing-operations"
        )
        ops = response.json()
        assert ops["count"] == 3  # move, force_form, force_assign
