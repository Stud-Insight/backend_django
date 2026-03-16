"""
TER Rankings API controller.
"""

from datetime import date
from uuid import UUID

from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get, http_post

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_ter_admin
from backend_django.groups.models import Group, GroupStatus
from backend_django.ter.models import SubjectStatus, TERIndividualRanking, TERRanking, TERSubject
from backend_django.ter.schemas.rankings import (
    TERIndividualRankingCreateSchema,
    TERIndividualRankingListSchema,
    TERIndividualRankingUserSchema,
    TERRankingCreateSchema,
    TERRankingItemSchema,
    TERRankingListSchema,
    TERSuggestedRankingSchema,
)


# ==================== TER Rankings Controller ====================


@api_controller("/ter/rankings", tags=["TER Rankings"], permissions=[IsAuthenticated])
class TERRankingController(BaseAPI):
    """API for TER group rankings."""

    @http_get(
        "/{group_id}",
        response={200: TERRankingListSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_rankings_get",
    )
    def get_rankings(self, request: HttpRequest, group_id: UUID):
        """
        Get the rankings for a group.

        Only group members and staff can view rankings.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Check permissions
        if not group.is_member(request.user) and not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Vous n'etes pas membre de ce groupe."
            ).to_response()

        # Get rankings
        rankings = TERRanking.objects.filter(group=group).select_related("subject").order_by("rank")

        ranking_items = [
            TERRankingItemSchema(
                subject_id=r.subject_id,
                subject_title=r.subject.title,
                rank=r.rank,
            )
            for r in rankings
        ]

        # Get the submitted_at timestamp from the most recent ranking
        submitted_at = None
        if rankings.exists():
            submitted_at = str(rankings.first().modified)

        return 200, TERRankingListSchema(
            group_id=group.id,
            group_name=group.name,
            ter_period_id=group.ter_period_id,
            rankings=ranking_items,
            submitted_at=submitted_at,
        )

    @http_post(
        "/{group_id}",
        response={200: TERRankingListSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_rankings_submit",
    )
    def submit_rankings(self, request: HttpRequest, group_id: UUID, data: TERRankingCreateSchema):
        """
        Submit rankings for a group.

        Only the group leader can submit rankings.
        The group must be in 'forme' status.
        All validated subjects must be ranked.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        # Only leader can submit rankings
        if not group.is_leader(request.user):
            return PermissionDeniedError(
                "Seul le chef de groupe peut soumettre le classement."
            ).to_response()

        # Group must be formed
        if group.status != GroupStatus.FORME:
            return BadRequestError(
                "Le groupe doit etre forme pour soumettre un classement."
            ).to_response()

        # Check group has a TER period
        if not group.ter_period:
            return BadRequestError(
                "Ce groupe n'est pas lie a une periode TER."
            ).to_response()

        # 4.3: Check ranking deadline has not passed
        today = date.today()
        if today > group.ter_period.subject_selection_end:
            return BadRequestError(
                "La periode de classement est terminee. "
                f"Date limite: {group.ter_period.subject_selection_end.strftime('%d/%m/%Y')}."
            ).to_response()

        # Get all validated subjects for this period
        validated_subjects = TERSubject.objects.filter(
            ter_period=group.ter_period,
            status=SubjectStatus.VALIDATED,
        )
        validated_subject_ids = set(str(s.id) for s in validated_subjects)

        # Validate all subjects exist and are validated
        submitted_subject_ids = set()
        for item in data.rankings:
            subject_id = str(item["subject_id"])
            if subject_id not in validated_subject_ids:
                return BadRequestError(
                    f"Le sujet {item['subject_id']} n'existe pas ou n'est pas valide."
                ).to_response()
            submitted_subject_ids.add(subject_id)

        # Check all subjects are ranked (exhaustive ranking)
        if submitted_subject_ids != validated_subject_ids:
            missing = validated_subject_ids - submitted_subject_ids
            return BadRequestError(
                f"Tous les sujets valides doivent etre classes. Sujets manquants: {len(missing)}"
            ).to_response()

        # Submit rankings in a transaction
        with transaction.atomic():
            # Delete existing rankings
            TERRanking.objects.filter(group=group).delete()

            # Create new rankings
            rankings_to_create = []
            for item in data.rankings:
                rankings_to_create.append(
                    TERRanking(
                        group=group,
                        subject_id=item["subject_id"],
                        rank=item["rank"],
                    )
                )

            TERRanking.objects.bulk_create(rankings_to_create)

        # Return the new rankings
        rankings = TERRanking.objects.filter(group=group).select_related("subject").order_by("rank")

        ranking_items = [
            TERRankingItemSchema(
                subject_id=r.subject_id,
                subject_title=r.subject.title,
                rank=r.rank,
            )
            for r in rankings
        ]

        return 200, TERRankingListSchema(
            group_id=group.id,
            group_name=group.name,
            ter_period_id=group.ter_period_id,
            rankings=ranking_items,
            submitted_at=str(rankings.first().modified) if rankings.exists() else None,
        )

    # ==================== Individual Rankings ====================

    @http_post(
        "/{group_id}/individual",
        response={200: TERIndividualRankingListSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_rankings_individual_submit",
    )
    def submit_individual_ranking(self, request: HttpRequest, group_id: UUID, data: TERIndividualRankingCreateSchema):
        """
        Submit a personal ranking for the current user.

        Any group member can submit their individual ranking.
        Partial rankings are allowed (not all subjects need to be ranked).
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        if not group.is_member(request.user):
            return PermissionDeniedError(
                "Vous n'etes pas membre de ce groupe."
            ).to_response()

        if not group.ter_period:
            return BadRequestError(
                "Ce groupe n'est pas lie a une periode TER."
            ).to_response()

        today = date.today()
        if today > group.ter_period.subject_selection_end:
            return BadRequestError(
                "La periode de classement est terminee. "
                f"Date limite: {group.ter_period.subject_selection_end.strftime('%d/%m/%Y')}."
            ).to_response()

        # Validate subjects exist and are validated
        validated_subject_ids = set(
            str(s.id) for s in TERSubject.objects.filter(
                ter_period=group.ter_period,
                status=SubjectStatus.VALIDATED,
            )
        )

        for item in data.rankings:
            subject_id = str(item["subject_id"])
            if subject_id not in validated_subject_ids:
                return BadRequestError(
                    f"Le sujet {item['subject_id']} n'existe pas ou n'est pas valide."
                ).to_response()

        with transaction.atomic():
            TERIndividualRanking.objects.filter(group=group, user=request.user).delete()

            TERIndividualRanking.objects.bulk_create([
                TERIndividualRanking(
                    group=group,
                    user=request.user,
                    subject_id=item["subject_id"],
                    rank=item["rank"],
                )
                for item in data.rankings
            ])

        return 200, self._build_individual_response(group)

    @http_get(
        "/{group_id}/individual",
        response={200: TERIndividualRankingListSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_rankings_individual_get",
    )
    def get_individual_rankings(self, request: HttpRequest, group_id: UUID):
        """
        View all group members' individual rankings.

        Visible to all group members and TER admins.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        if not group.is_member(request.user) and not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Vous n'etes pas membre de ce groupe."
            ).to_response()

        return 200, self._build_individual_response(group)

    @http_get(
        "/{group_id}/suggested",
        response={200: TERSuggestedRankingSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="ter_rankings_suggested",
    )
    def get_suggested_ranking(self, request: HttpRequest, group_id: UUID):
        """
        Get a suggested group ranking based on aggregated individual rankings.

        For each subject, sums all members' ranks. Members who didn't rank
        a subject get a penalty of (their max rank + 1). Lower total = more preferred.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(Group, id=group_id)

        if not group.is_member(request.user) and not is_ter_admin(request.user):
            return PermissionDeniedError(
                "Vous n'etes pas membre de ce groupe."
            ).to_response()

        all_rankings = TERIndividualRanking.objects.filter(
            group=group
        ).select_related("subject", "user")

        # Group rankings by user
        user_rankings: dict[UUID, dict[UUID, int]] = {}
        user_max_rank: dict[UUID, int] = {}
        for r in all_rankings:
            user_rankings.setdefault(r.user_id, {})[r.subject_id] = r.rank
            user_max_rank[r.user_id] = max(user_max_rank.get(r.user_id, 0), r.rank)

        members_who_ranked = len(user_rankings)

        if members_who_ranked == 0:
            return 200, TERSuggestedRankingSchema(
                group_id=group.id,
                group_name=group.name,
                rankings=[],
                member_count=group.member_count,
                members_who_ranked=0,
            )

        # Collect all ranked subjects
        all_subjects: dict[UUID, str] = {}
        for r in all_rankings:
            all_subjects[r.subject_id] = r.subject.title

        # Compute score per subject
        subject_scores: dict[UUID, float] = {}
        subject_vote_count: dict[UUID, int] = {}
        for subject_id in all_subjects:
            total = 0
            votes = 0
            for user_id, rankings in user_rankings.items():
                if subject_id in rankings:
                    total += rankings[subject_id]
                    votes += 1
                else:
                    total += user_max_rank[user_id] + 1
            subject_scores[subject_id] = total
            subject_vote_count[subject_id] = votes

        # Sort: lower score first, then more votes, then alphabetical
        sorted_subjects = sorted(
            all_subjects.keys(),
            key=lambda sid: (subject_scores[sid], -subject_vote_count[sid], all_subjects[sid]),
        )

        ranking_items = [
            TERRankingItemSchema(
                subject_id=sid,
                subject_title=all_subjects[sid],
                rank=i + 1,
            )
            for i, sid in enumerate(sorted_subjects)
        ]

        return 200, TERSuggestedRankingSchema(
            group_id=group.id,
            group_name=group.name,
            rankings=ranking_items,
            member_count=group.member_count,
            members_who_ranked=members_who_ranked,
        )

    def _build_individual_response(self, group: Group) -> TERIndividualRankingListSchema:
        """Build the individual rankings response for a group."""
        all_rankings = TERIndividualRanking.objects.filter(
            group=group
        ).select_related("subject", "user").order_by("user__last_name", "user__first_name", "rank")

        # Group by user
        users_data: dict[UUID, TERIndividualRankingUserSchema] = {}
        for r in all_rankings:
            if r.user_id not in users_data:
                users_data[r.user_id] = TERIndividualRankingUserSchema(
                    user_id=r.user_id,
                    user_email=r.user.email,
                    user_first_name=r.user.first_name,
                    user_last_name=r.user.last_name,
                    rankings=[],
                )
            users_data[r.user_id].rankings.append(
                TERRankingItemSchema(
                    subject_id=r.subject_id,
                    subject_title=r.subject.title,
                    rank=r.rank,
                )
            )

        return TERIndividualRankingListSchema(
            group_id=group.id,
            group_name=group.name,
            members_rankings=list(users_data.values()),
        )
