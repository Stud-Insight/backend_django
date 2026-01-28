"""
TER Rankings API controller.
"""

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
from backend_django.ter.models import SubjectStatus, TERRanking, TERSubject
from backend_django.ter.schemas.rankings import (
    TERRankingCreateSchema,
    TERRankingItemSchema,
    TERRankingListSchema,
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
