"""
Tests for the TER individual rankings API endpoints.

Covers:
- POST /{group_id}/individual - submit personal ranking
- GET /{group_id}/individual - view all members' rankings
- GET /{group_id}/suggested - aggregated suggested ranking
"""

import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Group as DjangoGroup
from django.test import Client

from backend_django.core.roles import Role
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import (
    PeriodStatus,
    SubjectStatus,
    TERIndividualRanking,
    TERPeriod,
    TERSubject,
)
from backend_django.users.tests.factories import UserFactory


# ==================== Fixtures ====================


@pytest.fixture
def student_user(db):
    user = UserFactory(
        email="student@test.com",
        first_name="Alice",
        last_name="Dupont",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def another_student(db):
    user = UserFactory(
        email="student2@test.com",
        first_name="Bob",
        last_name="Martin",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def outsider(db):
    user = UserFactory(
        email="outsider@test.com",
        first_name="Eve",
        last_name="Hacker",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def staff_user(db):
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
def ter_period(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER 2024-2025",
        academic_year="2024-2025",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=30),
        group_formation_end=today - timedelta(days=1),
        subject_selection_start=today - timedelta(days=1),
        subject_selection_end=today + timedelta(days=30),
        assignment_date=today + timedelta(days=31),
        project_start=today + timedelta(days=40),
        project_end=today + timedelta(days=180),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def ter_period_expired(db):
    today = date.today()
    return TERPeriod.objects.create(
        name="TER Expired",
        academic_year="2023-2024",
        status=PeriodStatus.OPEN,
        group_formation_start=today - timedelta(days=200),
        group_formation_end=today - timedelta(days=150),
        subject_selection_start=today - timedelta(days=150),
        subject_selection_end=today - timedelta(days=10),
        assignment_date=today - timedelta(days=5),
        project_start=today - timedelta(days=3),
        project_end=today + timedelta(days=100),
        min_group_size=1,
        max_group_size=4,
    )


@pytest.fixture
def professor(db):
    user = UserFactory(
        email="prof@test.com",
        first_name="Prof",
        last_name="Test",
        is_active=True,
    )
    user.set_password("testpass123")
    user.save()
    return user


@pytest.fixture
def subject_ia(ter_period, professor):
    return TERSubject.objects.create(
        title="Intelligence Artificielle",
        description="Projet IA",
        domain="IA/ML",
        professor=professor,
        ter_period=ter_period,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def subject_web(ter_period, professor):
    return TERSubject.objects.create(
        title="Developpement Web",
        description="Projet Web",
        domain="Web",
        professor=professor,
        ter_period=ter_period,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def subject_secu(ter_period, professor):
    return TERSubject.objects.create(
        title="Securite Informatique",
        description="Projet Secu",
        domain="Securite",
        professor=professor,
        ter_period=ter_period,
        status=SubjectStatus.VALIDATED,
    )


@pytest.fixture
def subject_draft(ter_period, professor):
    return TERSubject.objects.create(
        title="Sujet Brouillon",
        description="Pas encore valide",
        domain="Autre",
        professor=professor,
        ter_period=ter_period,
        status=SubjectStatus.DRAFT,
    )


@pytest.fixture
def formed_group(student_user, another_student, ter_period):
    group = Group.objects.create(
        name="Groupe Test",
        leader=student_user,
        project_type="TER",
        ter_period=ter_period,
        status=GroupStatus.FORME,
    )
    group.members.add(student_user, another_student)
    return group


def make_client(user):
    client = Client()
    response = client.get("/api/auth/csrf")
    csrf_token = response.json()["csrf_token"]
    client.post(
        "/api/auth/login",
        data={"email": user.email, "password": "testpass123"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    return client, csrf_token


# ==================== POST individual ranking ====================


@pytest.mark.django_db
class TestSubmitIndividualRanking:
    def test_submit_individual_ranking_success(
        self, formed_group, student_user, subject_ia, subject_web
    ):
        client, csrf = make_client(student_user)
        response = client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_ia.id), "rank": 1},
                    {"subject_id": str(subject_web.id), "rank": 2},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group_id"] == str(formed_group.id)
        assert len(data["members_rankings"]) == 1
        assert data["members_rankings"][0]["user_id"] == str(student_user.id)
        assert len(data["members_rankings"][0]["rankings"]) == 2

    def test_submit_partial_ranking(
        self, formed_group, student_user, subject_ia, subject_web, subject_secu
    ):
        """Partial ranking is allowed (not all subjects required)."""
        client, csrf = make_client(student_user)
        response = client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_ia.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200
        rankings = response.json()["members_rankings"][0]["rankings"]
        assert len(rankings) == 1

    def test_submit_replaces_previous_ranking(
        self, formed_group, student_user, subject_ia, subject_web
    ):
        """Submitting again replaces the old ranking."""
        client, csrf = make_client(student_user)
        # First submission
        client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_ia.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        # Second submission with different ranking
        response = client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_web.id), "rank": 1},
                    {"subject_id": str(subject_ia.id), "rank": 2},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 200
        rankings = response.json()["members_rankings"][0]["rankings"]
        assert len(rankings) == 2
        assert rankings[0]["subject_title"] == "Developpement Web"
        assert rankings[0]["rank"] == 1

    def test_submit_forbidden_for_non_member(
        self, formed_group, outsider, subject_ia
    ):
        client, csrf = make_client(outsider)
        response = client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_ia.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 403

    def test_submit_rejects_invalid_subject(
        self, formed_group, student_user, subject_draft
    ):
        """Cannot rank a draft (non-validated) subject."""
        client, csrf = make_client(student_user)
        response = client.post(
            f"/api/ter/rankings/{formed_group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_draft.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 400

    def test_submit_after_deadline(
        self, student_user, professor, ter_period_expired
    ):
        """Cannot submit after subject_selection_end."""
        subject = TERSubject.objects.create(
            title="Sujet Expire",
            description="Test",
            domain="Test",
            professor=professor,
            ter_period=ter_period_expired,
            status=SubjectStatus.VALIDATED,
        )
        group = Group.objects.create(
            name="Groupe Expire",
            leader=student_user,
            project_type="TER",
            ter_period=ter_period_expired,
            status=GroupStatus.FORME,
        )
        group.members.add(student_user)

        client, csrf = make_client(student_user)
        response = client.post(
            f"/api/ter/rankings/{group.id}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 400

    def test_submit_nonexistent_group(self, student_user, subject_ia):
        client, csrf = make_client(student_user)
        response = client.post(
            f"/api/ter/rankings/{uuid4()}/individual",
            data=json.dumps({
                "rankings": [
                    {"subject_id": str(subject_ia.id), "rank": 1},
                ]
            }),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 404


# ==================== GET individual rankings ====================


@pytest.mark.django_db
class TestGetIndividualRankings:
    def test_get_as_group_member(
        self, formed_group, student_user, another_student, subject_ia, subject_web
    ):
        # Both members submit rankings
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_ia, rank=1
        )
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_web, rank=2
        )
        TERIndividualRanking.objects.create(
            group=formed_group, user=another_student, subject=subject_web, rank=1
        )

        client, _ = make_client(student_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/individual")
        assert response.status_code == 200
        data = response.json()
        assert len(data["members_rankings"]) == 2

    def test_get_as_staff(
        self, formed_group, staff_user, student_user, subject_ia
    ):
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_ia, rank=1
        )
        client, _ = make_client(staff_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/individual")
        assert response.status_code == 200

    def test_get_forbidden_for_outsider(self, formed_group, outsider):
        client, _ = make_client(outsider)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/individual")
        assert response.status_code == 403

    def test_get_empty_rankings(self, formed_group, student_user):
        """No rankings submitted yet returns empty list."""
        client, _ = make_client(student_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/individual")
        assert response.status_code == 200
        assert response.json()["members_rankings"] == []


# ==================== GET suggested ranking ====================


@pytest.mark.django_db
class TestGetSuggestedRanking:
    def test_suggested_ranking_aggregation(
        self, formed_group, student_user, another_student, subject_ia, subject_web, subject_secu
    ):
        """Suggested ranking aggregates individual rankings by sum of ranks."""
        # Alice: IA=1, Web=2, Secu=3
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_ia, rank=1
        )
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_web, rank=2
        )
        TERIndividualRanking.objects.create(
            group=formed_group, user=student_user, subject=subject_secu, rank=3
        )
        # Bob: IA=1, Secu=2
        TERIndividualRanking.objects.create(
            group=formed_group, user=another_student, subject=subject_ia, rank=1
        )
        TERIndividualRanking.objects.create(
            group=formed_group, user=another_student, subject=subject_secu, rank=2
        )
        # Bob didn't rank Web => penalty = max_rank + 1 = 3

        client, _ = make_client(student_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/suggested")
        assert response.status_code == 200
        data = response.json()
        assert data["member_count"] == 2
        assert data["members_who_ranked"] == 2

        rankings = data["rankings"]
        # IA: 1+1=2, Secu: 3+2=5, Web: 2+3=5
        # IA should be first
        assert rankings[0]["subject_title"] == "Intelligence Artificielle"
        assert rankings[0]["rank"] == 1

    def test_suggested_empty_when_no_rankings(self, formed_group, student_user):
        client, _ = make_client(student_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/suggested")
        assert response.status_code == 200
        data = response.json()
        assert data["rankings"] == []
        assert data["members_who_ranked"] == 0

    def test_suggested_forbidden_for_outsider(self, formed_group, outsider):
        client, _ = make_client(outsider)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/suggested")
        assert response.status_code == 403

    def test_suggested_accessible_by_staff(self, formed_group, staff_user):
        client, _ = make_client(staff_user)
        response = client.get(f"/api/ter/rankings/{formed_group.id}/suggested")
        assert response.status_code == 200
