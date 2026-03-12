"""Tests for assignment result notifications (Story 4-7)."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group as DjangoGroup

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.notifications.models import Notification
from backend_django.ter.models import (
    PeriodStatus,
    SubjectStatus,
    TERPeriod,
    TERRanking,
    TERSubject,
)
from backend_django.users.models import User


@pytest.fixture
def professor(db):
    user = User.objects.create_user(
        email="prof-assign@example.com",
        password="password123",
        first_name="Prof",
        last_name="Encadrant",
    )
    group, _ = DjangoGroup.objects.get_or_create(name=Role.ENCADRANT.value)
    user.groups.add(group)
    return user


@pytest.fixture
def students(db):
    users = []
    for i in range(4):
        user = User.objects.create_user(
            email=f"student-assign-{i}@example.com",
            password="password123",
            first_name=f"Student{i}",
            last_name="Test",
        )
        group, _ = DjangoGroup.objects.get_or_create(name=Role.ETUDIANT.value)
        user.groups.add(group)
        users.append(user)
    return users


@pytest.fixture
def ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Assign Test",
        academic_year="2025-2026",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=60),
        group_formation_end=today - timedelta(days=30),
        subject_selection_start=today - timedelta(days=30),
        subject_selection_end=today - timedelta(days=1),
        assignment_date=today,
        project_start=today + timedelta(days=10),
        project_end=today + timedelta(days=180),
        min_group_size=2,
        max_group_size=5,
    )


@pytest.fixture
def subjects(ter_period, professor):
    return [
        TERSubject.objects.create(
            ter_period=ter_period,
            professor=professor,
            title=f"Sujet {i}",
            description=f"Description sujet {i}",
            status=SubjectStatus.VALIDATED,
            max_groups=2,
        )
        for i in range(2)
    ]


@pytest.fixture
def formed_groups(ter_period, students):
    """Create 2 formed groups with 2 students each."""
    groups = []
    for i in range(2):
        g = Group.objects.create(
            name=f"Groupe {i}",
            leader=students[i * 2],
            ter_period=ter_period,
            status=GroupStatus.FORME,
        )
        g.members.add(students[i * 2], students[i * 2 + 1])
        groups.append(g)
    return groups


@pytest.fixture
def rankings(formed_groups, subjects):
    """Group 0 ranks: Sujet 0, Sujet 1. Group 1 ranks: Sujet 1, Sujet 0."""
    TERRanking.objects.create(group=formed_groups[0], subject=subjects[0], rank=1)
    TERRanking.objects.create(group=formed_groups[0], subject=subjects[1], rank=2)
    TERRanking.objects.create(group=formed_groups[1], subject=subjects[1], rank=1)
    TERRanking.objects.create(group=formed_groups[1], subject=subjects[0], rank=2)


@pytest.mark.django_db(transaction=True)
class TestAssignmentNotifications:
    def test_students_notified_with_choice_rank(
        self, ter_period, formed_groups, subjects, rankings, students
    ):
        from backend_django.algorithms.tasks import run_ter_assignment_task

        result = run_ter_assignment_task(str(ter_period.id))

        assert result["success"] is True
        assert result["assigned"] == 2

        # Group 0 students should get choice rank 1 (they got their 1st choice)
        g0_notifs = Notification.objects.filter(
            recipient__in=[students[0], students[1]],
            notification_type="ter.subject_assigned",
        )
        assert g0_notifs.count() == 2
        notif = g0_notifs.first()
        assert "choix n°" in notif.message
        assert notif.data["choice_rank"] is not None

    def test_professor_notified_with_group_list(
        self, ter_period, formed_groups, subjects, rankings, professor
    ):
        from backend_django.algorithms.tasks import run_ter_assignment_task

        run_ter_assignment_task(str(ter_period.id))

        prof_notifs = Notification.objects.filter(
            recipient=professor,
            notification_type="ter.groups_assigned",
        )
        assert prof_notifs.count() == 1
        notif = prof_notifs.first()
        assert "groupe(s) assigné(s)" in notif.title
        assert notif.data["group_count"] >= 1
        assert ter_period.name in notif.message

    def test_no_notifications_when_no_rankings(self, ter_period, subjects):
        """No formed groups with rankings → no assignment → no notifications."""
        from backend_django.algorithms.tasks import run_ter_assignment_task

        result = run_ter_assignment_task(str(ter_period.id))

        assert result["success"] is True
        assert result["total_groups"] == 0
        assert Notification.objects.count() == 0
