"""
Stage Offers API controller.
"""

from uuid import UUID

from django.db import models
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_delete, http_get, http_post, http_put

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    BadRequestError,
    ErrorSchema,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
)
from backend_django.core.roles import is_stage_admin
from backend_django.stages.models import OfferStatus, PeriodStatus, StageFavorite, StageOffer, StagePeriod
from backend_django.stages.schemas.offers import (
    StageFavoriteSchema,
    StageOfferCreateSchema,
    StageOfferDetailSchema,
    StageOfferListSchema,
    StageOfferRejectSchema,
    StageOfferUpdateSchema,
    UserMinimalSchema,
)
from backend_django.users.models import User


# ==================== Helper Functions ====================


def user_to_minimal_schema(user: User | None) -> UserMinimalSchema | None:
    """Convert User to minimal schema."""
    if not user:
        return None
    return UserMinimalSchema(
        id=user.id,
        email=user.email,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )


def offer_to_list_schema(offer: StageOffer) -> StageOfferListSchema:
    """Convert StageOffer to list schema."""
    return StageOfferListSchema(
        id=offer.id,
        title=offer.title,
        company_name=offer.company_name,
        location=offer.location,
        domain=offer.domain,
        supervisor=user_to_minimal_schema(offer.supervisor),
        status=offer.status,
        max_students=offer.max_students,
        stage_period_id=offer.stage_period_id,
        created=str(offer.created),
    )


def offer_to_detail_schema(offer: StageOffer, is_favorite: bool = False) -> StageOfferDetailSchema:
    """Convert StageOffer to detailed schema."""
    return StageOfferDetailSchema(
        id=offer.id,
        title=offer.title,
        description=offer.description,
        company_name=offer.company_name,
        location=offer.location,
        domain=offer.domain,
        prerequisites=offer.prerequisites,
        supervisor=user_to_minimal_schema(offer.supervisor),
        max_students=offer.max_students,
        status=offer.status,
        rejection_reason=offer.rejection_reason,
        stage_period_id=offer.stage_period_id,
        created=str(offer.created),
        modified=str(offer.modified),
        is_favorite=is_favorite,
    )


# ==================== Stage Offers Controller ====================


@api_controller("/stages/offers", tags=["Stage Offers"], permissions=[IsAuthenticated])
class StageOfferController(BaseAPI):
    """API for Stage offers."""

    @http_get(
        "/",
        response={200: list[StageOfferListSchema], 401: ErrorSchema},
        url_name="stage_offers_list",
    )
    def list_offers(
        self,
        request: HttpRequest,
        stage_period_id: UUID | None = None,
        status: str | None = None,
        domain: str | None = None,
        company: str | None = None,
    ):
        """
        List Stage offers.

        Optional filters:
        - stage_period_id: Filter by Stage period
        - status: Filter by status (draft, submitted, validated, rejected)
        - domain: Filter by domain
        - company: Filter by company name
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offers = StageOffer.objects.select_related("supervisor", "stage_period").all()

        # Non-staff users only see validated offers (and their own drafts/submitted)
        if not is_stage_admin(request.user):
            offers = offers.filter(
                models.Q(status=OfferStatus.VALIDATED) |
                models.Q(supervisor=request.user)
            )
        elif status:
            offers = offers.filter(status=status)

        if stage_period_id:
            offers = offers.filter(stage_period_id=stage_period_id)

        if domain:
            offers = offers.filter(domain__icontains=domain)

        if company:
            offers = offers.filter(company_name__icontains=company)

        offers = offers.order_by("-created")

        return 200, [offer_to_list_schema(o) for o in offers]

    @http_get(
        "/{offer_id}",
        response={200: StageOfferDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_detail",
    )
    def get_offer(self, request: HttpRequest, offer_id: UUID):
        """Get Stage offer details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(
            StageOffer.objects.select_related("supervisor", "stage_period"),
            id=offer_id
        )

        # Non-staff/non-owners can only see validated offers
        if not is_stage_admin(request.user) and not offer.can_be_managed_by(request.user):
            if offer.status != OfferStatus.VALIDATED:
                return NotFoundError("Offre de stage non trouvee.").to_response()

        # Check if user has favorited this offer
        is_favorite = StageFavorite.objects.filter(
            student=request.user,
            offer=offer,
        ).exists()

        return 200, offer_to_detail_schema(offer, is_favorite=is_favorite)

    @http_post(
        "/",
        response={201: StageOfferDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="stage_offers_create",
    )
    def create_offer(self, request: HttpRequest, data: StageOfferCreateSchema):
        """
        Create a new Stage offer.

        External supervisors and staff can create offers.
        New offers are created with status 'draft'.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Check Stage period exists and is open
        stage_period = get_object_or_404(StagePeriod, id=data.stage_period_id)
        if stage_period.status != PeriodStatus.OPEN and not is_stage_admin(request.user):
            return BadRequestError(
                "La periode de stage n'est pas ouverte."
            ).to_response()

        offer = StageOffer.objects.create(
            stage_period=stage_period,
            title=data.title,
            description=data.description,
            company_name=data.company_name,
            location=data.location,
            domain=data.domain,
            prerequisites=data.prerequisites,
            supervisor=request.user,
            max_students=data.max_students,
            status=OfferStatus.DRAFT,
        )

        return 201, offer_to_detail_schema(offer)

    @http_put(
        "/{offer_id}",
        response={200: StageOfferDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_update",
    )
    def update_offer(
        self, request: HttpRequest, offer_id: UUID, data: StageOfferUpdateSchema
    ):
        """
        Update a Stage offer.

        Only owner/staff can update. Only draft/rejected offers can be edited.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        if not offer.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour modifier cette offre."
            ).to_response()

        # Only draft or rejected offers can be edited
        if offer.status not in [OfferStatus.DRAFT, OfferStatus.REJECTED]:
            return BadRequestError(
                "Seules les offres en brouillon ou rejetees peuvent etre modifiees."
            ).to_response()

        if data.title is not None:
            offer.title = data.title
        if data.description is not None:
            offer.description = data.description
        if data.company_name is not None:
            offer.company_name = data.company_name
        if data.location is not None:
            offer.location = data.location
        if data.domain is not None:
            offer.domain = data.domain
        if data.prerequisites is not None:
            offer.prerequisites = data.prerequisites
        if data.max_students is not None:
            offer.max_students = data.max_students

        # Reset to draft if was rejected
        if offer.status == OfferStatus.REJECTED:
            offer.status = OfferStatus.DRAFT
            offer.rejection_reason = ""

        offer.save()

        return 200, offer_to_detail_schema(offer)

    @http_post(
        "/{offer_id}/submit",
        response={200: StageOfferDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_submit",
    )
    def submit_offer(self, request: HttpRequest, offer_id: UUID):
        """
        Submit a Stage offer for validation.

        Transitions from draft to submitted.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        if not offer.can_be_managed_by(request.user):
            return PermissionDeniedError(
                "Vous n'avez pas les droits pour soumettre cette offre."
            ).to_response()

        if offer.status != OfferStatus.DRAFT:
            return BadRequestError(
                f"Impossible de soumettre une offre avec le statut '{offer.status}'."
            ).to_response()

        offer.status = OfferStatus.SUBMITTED
        offer.save()

        return 200, offer_to_detail_schema(offer)

    @http_post(
        "/{offer_id}/validate",
        response={200: StageOfferDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_validate",
    )
    def validate_offer(self, request: HttpRequest, offer_id: UUID):
        """
        Validate a Stage offer.

        Only staff (Respo Stage) can validate offers.
        Transitions from submitted to validated.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent valider des offres."
            ).to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        if offer.status != OfferStatus.SUBMITTED:
            return BadRequestError(
                f"Impossible de valider une offre avec le statut '{offer.status}'."
            ).to_response()

        offer.status = OfferStatus.VALIDATED
        offer.save()

        return 200, offer_to_detail_schema(offer)

    @http_post(
        "/{offer_id}/reject",
        response={200: StageOfferDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_reject",
    )
    def reject_offer(self, request: HttpRequest, offer_id: UUID, data: StageOfferRejectSchema):
        """
        Reject a Stage offer.

        Only staff (Respo Stage) can reject offers.
        Requires a reason for rejection.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        if not is_stage_admin(request.user):
            return PermissionDeniedError(
                "Seuls les responsables Stage peuvent rejeter des offres."
            ).to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        if offer.status != OfferStatus.SUBMITTED:
            return BadRequestError(
                f"Impossible de rejeter une offre avec le statut '{offer.status}'."
            ).to_response()

        offer.status = OfferStatus.REJECTED
        offer.rejection_reason = data.reason
        offer.save()

        return 200, offer_to_detail_schema(offer)

    @http_post(
        "/{offer_id}/favorite",
        response={201: StageFavoriteSchema, 400: ErrorSchema, 401: ErrorSchema, 404: ErrorSchema, 409: ErrorSchema},
        url_name="stage_offers_add_favorite",
    )
    def add_favorite(self, request: HttpRequest, offer_id: UUID):
        """
        Add a Stage offer to favorites.

        Students can mark validated offers as favorites.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        offer = get_object_or_404(StageOffer, id=offer_id)

        # Only validated offers can be favorited
        if offer.status != OfferStatus.VALIDATED:
            return BadRequestError(
                "Seules les offres validees peuvent etre mises en favoris."
            ).to_response()

        # Check if already favorited
        if StageFavorite.objects.filter(student=request.user, offer=offer).exists():
            return 409, {"message": "Cette offre est deja dans vos favoris."}

        favorite = StageFavorite.objects.create(
            student=request.user,
            offer=offer,
        )

        return 201, StageFavoriteSchema(
            id=favorite.id,
            student_id=favorite.student_id,
            offer_id=favorite.offer_id,
            created=str(favorite.created),
        )

    @http_delete(
        "/{offer_id}/favorite",
        response={204: None, 401: ErrorSchema, 404: ErrorSchema},
        url_name="stage_offers_remove_favorite",
    )
    def remove_favorite(self, request: HttpRequest, offer_id: UUID):
        """
        Remove a Stage offer from favorites.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        favorite = get_object_or_404(
            StageFavorite,
            student=request.user,
            offer_id=offer_id,
        )

        favorite.delete()

        return 204, None
