"""
Stage Rankings API controller.
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
    PermissionDeniedError,
)
from backend_django.core.roles import is_stage_admin
from backend_django.stages.models import OfferStatus, StagePeriod, StageOffer, StageRanking
from backend_django.stages.schemas.rankings import (
    StageRankingCreateSchema,
    StageRankingItemSchema,
    StageRankingListSchema,
)


# ==================== Stage Rankings Controller ====================


@api_controller("/stages/rankings", tags=["Stage Rankings"], permissions=[IsAuthenticated])
class StageRankingController(BaseAPI):
    """API for Stage student rankings."""

    @http_get(
        "/",
        response={200: StageRankingListSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="stage_rankings_get",
    )
    def get_my_rankings(self, request: HttpRequest, stage_period_id: UUID):
        """
        Get the current user's rankings for a stage period.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(StagePeriod, id=stage_period_id)

        # Get rankings
        rankings = StageRanking.objects.filter(
            student=request.user,
            offer__stage_period=period,
        ).select_related("offer").order_by("rank")

        ranking_items = [
            StageRankingItemSchema(
                offer_id=r.offer_id,
                offer_title=r.offer.title,
                company_name=r.offer.company_name,
                rank=r.rank,
            )
            for r in rankings
        ]

        # Get the submitted_at timestamp from the most recent ranking
        submitted_at = None
        if rankings.exists():
            submitted_at = str(rankings.first().modified)

        return 200, StageRankingListSchema(
            student_id=request.user.id,
            stage_period_id=period.id,
            rankings=ranking_items,
            submitted_at=submitted_at,
        )

    @http_get(
        "/{student_id}",
        response={200: StageRankingListSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_rankings_get_student",
    )
    def get_student_rankings(self, request: HttpRequest, student_id: UUID, stage_period_id: UUID):
        """
        Get a student's rankings for a stage period.

        Only staff and the student themselves can view rankings.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Check permissions
        if str(request.user.id) != str(student_id) and not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Vous ne pouvez pas voir les classements d'un autre etudiant."
            ).to_response()

        period = get_object_or_404(StagePeriod, id=stage_period_id)

        # Get rankings
        rankings = StageRanking.objects.filter(
            student_id=student_id,
            offer__stage_period=period,
        ).select_related("offer").order_by("rank")

        ranking_items = [
            StageRankingItemSchema(
                offer_id=r.offer_id,
                offer_title=r.offer.title,
                company_name=r.offer.company_name,
                rank=r.rank,
            )
            for r in rankings
        ]

        submitted_at = None
        if rankings.exists():
            submitted_at = str(rankings.first().modified)

        return 200, StageRankingListSchema(
            student_id=student_id,
            stage_period_id=period.id,
            rankings=ranking_items,
            submitted_at=submitted_at,
        )

    @http_post(
        "/",
        response={200: StageRankingListSchema, 400: ErrorSchema, 401: ErrorSchema},
        url_name="stage_rankings_submit",
    )
    def submit_rankings(self, request: HttpRequest, data: StageRankingCreateSchema):
        """
        Submit rankings for a stage period.

        Students can submit their own rankings.
        All validated offers must be ranked.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        period = get_object_or_404(StagePeriod, id=data.stage_period_id)

        # Get all validated offers for this period
        validated_offers = StageOffer.objects.filter(
            stage_period=period,
            status=OfferStatus.VALIDATED,
        )
        validated_offer_ids = set(str(o.id) for o in validated_offers)

        # Validate all offers exist and are validated
        submitted_offer_ids = set()
        for item in data.rankings:
            offer_id = str(item["offer_id"])
            if offer_id not in validated_offer_ids:
                return BadRequestError(
                    f"L'offre {item['offer_id']} n'existe pas ou n'est pas validee."
                ).to_response()
            submitted_offer_ids.add(offer_id)

        # Check all offers are ranked (exhaustive ranking)
        if submitted_offer_ids != validated_offer_ids:
            missing = validated_offer_ids - submitted_offer_ids
            return BadRequestError(
                f"Toutes les offres validees doivent etre classees. Offres manquantes: {len(missing)}"
            ).to_response()

        # Submit rankings in a transaction
        with transaction.atomic():
            # Delete existing rankings for this period
            StageRanking.objects.filter(
                student=request.user,
                offer__stage_period=period,
            ).delete()

            # Create new rankings
            rankings_to_create = []
            for item in data.rankings:
                rankings_to_create.append(
                    StageRanking(
                        student=request.user,
                        offer_id=item["offer_id"],
                        rank=item["rank"],
                    )
                )

            StageRanking.objects.bulk_create(rankings_to_create)

        # Return the new rankings
        rankings = StageRanking.objects.filter(
            student=request.user,
            offer__stage_period=period,
        ).select_related("offer").order_by("rank")

        ranking_items = [
            StageRankingItemSchema(
                offer_id=r.offer_id,
                offer_title=r.offer.title,
                company_name=r.offer.company_name,
                rank=r.rank,
            )
            for r in rankings
        ]

        return 200, StageRankingListSchema(
            student_id=request.user.id,
            stage_period_id=period.id,
            rankings=ranking_items,
            submitted_at=str(rankings.first().modified) if rankings.exists() else None,
        )
