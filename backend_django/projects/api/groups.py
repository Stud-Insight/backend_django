"""
Groups API controller.
"""

from datetime import date
from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller
from ninja_extra import http_get
from ninja_extra import http_post

from backend_django.core.api import BaseAPI
from backend_django.core.api import IsAuthenticated
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import NotFoundError
from backend_django.core.exceptions import PermissionDeniedError
from backend_django.projects.models import AcademicProjectType
from backend_django.projects.models import GroupStatus
from backend_django.projects.models import PeriodStatus
from backend_django.projects.models import StagePeriod
from backend_django.projects.models import StudentGroup
from backend_django.projects.models import TERPeriod
from backend_django.projects.schemas.groups import GroupCreateSchema
from backend_django.projects.schemas.groups import GroupDetailSchema
from backend_django.projects.schemas.groups import GroupListSchema
from backend_django.projects.schemas.groups import StagePeriodSchema
from backend_django.projects.schemas.groups import TERPeriodSchema
from backend_django.projects.schemas.projects import MessageSchema
from backend_django.projects.schemas.projects import UserMinimalSchema


def ter_period_to_schema(period: TERPeriod) -> TERPeriodSchema:
    """Convert TERPeriod to schema."""
    return TERPeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        group_formation_start=str(period.group_formation_start),
        group_formation_end=str(period.group_formation_end),
        min_group_size=period.min_group_size,
        max_group_size=period.max_group_size,
    )


def stage_period_to_schema(period: StagePeriod) -> StagePeriodSchema:
    """Convert StagePeriod to schema."""
    return StagePeriodSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        application_start=str(period.application_start),
        application_end=str(period.application_end),
    )


def group_to_list_schema(group: StudentGroup) -> GroupListSchema:
    """Convert StudentGroup to list schema."""
    return GroupListSchema(
        id=group.id,
        name=group.name,
        leader=UserMinimalSchema.from_user(group.leader),
        member_count=group.member_count,
        status=group.status,
        project_type=group.project_type,
        created=group.created,
    )


def group_to_detail_schema(group: StudentGroup) -> GroupDetailSchema:
    """Convert StudentGroup to detail schema."""
    members = [UserMinimalSchema.from_user(m) for m in group.members.all()]
    return GroupDetailSchema(
        id=group.id,
        name=group.name,
        leader=UserMinimalSchema.from_user(group.leader),
        member_count=group.member_count,
        status=group.status,
        project_type=group.project_type,
        created=group.created,
        members=members,
        ter_period=ter_period_to_schema(group.ter_period) if group.ter_period else None,
        stage_period=stage_period_to_schema(group.stage_period) if group.stage_period else None,
        assigned_proposal_id=group.assigned_proposal_id,
    )


@api_controller("/groups", tags=["Groups"], permissions=[IsAuthenticated])
class GroupController(BaseAPI):
    """CRUD operations for student groups."""

    @http_get(
        "/",
        response={200: list[GroupListSchema], 401: ErrorSchema},
        url_name="groups_list",
    )
    def list_groups(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
        stage_period_id: UUID | None = None,
        status: str | None = None,
    ):
        """List groups with optional filtering."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        groups = StudentGroup.objects.select_related("leader", "ter_period", "stage_period")

        if ter_period_id:
            groups = groups.filter(ter_period_id=ter_period_id)
        if stage_period_id:
            groups = groups.filter(stage_period_id=stage_period_id)
        if status:
            groups = groups.filter(status=status)

        groups = groups.order_by("-created")

        return 200, [group_to_list_schema(g) for g in groups]

    @http_get(
        "/my",
        response={200: list[GroupListSchema], 401: ErrorSchema},
        url_name="groups_my",
    )
    def my_groups(self, request: HttpRequest):
        """Get groups where current user is a member."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        groups = StudentGroup.objects.filter(
            members=request.user
        ).select_related("leader", "ter_period", "stage_period").order_by("-created")

        return 200, [group_to_list_schema(g) for g in groups]

    @http_get(
        "/{group_id}",
        response={200: GroupDetailSchema, 401: ErrorSchema, 404: ErrorSchema},
        url_name="groups_detail",
    )
    def get_group(self, request: HttpRequest, group_id: UUID):
        """Get group details."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        group = get_object_or_404(
            StudentGroup.objects.select_related("leader", "ter_period", "stage_period").prefetch_related("members"),
            id=group_id,
        )

        return 200, group_to_detail_schema(group)

    @http_post(
        "/",
        response={201: GroupDetailSchema, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema},
        url_name="groups_create",
    )
    def create_group(self, request: HttpRequest, data: GroupCreateSchema):
        """
        Create a new group for TER.

        The current user becomes the leader and first member.
        Requires an active TER period in formation phase.
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        # Validate that exactly one period is specified
        if data.ter_period_id and data.stage_period_id:
            return BadRequestError("Spécifiez soit une période TER soit une période Stage, pas les deux.").to_response()

        if not data.ter_period_id and not data.stage_period_id:
            return BadRequestError("Vous devez spécifier une période TER ou Stage.").to_response()

        ter_period = None
        stage_period = None
        project_type = None

        if data.ter_period_id:
            # TER group creation
            ter_period = TERPeriod.objects.filter(id=data.ter_period_id).first()
            if not ter_period:
                return NotFoundError("Période TER non trouvée.").to_response()

            # Check period is open
            if ter_period.status != PeriodStatus.OPEN:
                return BadRequestError("La période TER n'est pas ouverte.").to_response()

            # Check we're in formation phase
            today = date.today()
            if not (ter_period.group_formation_start <= today <= ter_period.group_formation_end):
                return BadRequestError("La période de formation des groupes est terminée.").to_response()

            # Check user doesn't already lead a group for this period
            existing_group = StudentGroup.objects.filter(
                leader=request.user,
                ter_period=ter_period,
            ).first()
            if existing_group:
                return BadRequestError("Vous êtes déjà leader d'un groupe pour cette période TER.").to_response()

            project_type = AcademicProjectType.SRW

        elif data.stage_period_id:
            # Stage group creation
            stage_period = StagePeriod.objects.filter(id=data.stage_period_id).first()
            if not stage_period:
                return NotFoundError("Période Stage non trouvée.").to_response()

            # Check period is open
            if stage_period.status != PeriodStatus.OPEN:
                return BadRequestError("La période Stage n'est pas ouverte.").to_response()

            # Check user doesn't already lead a group for this period
            existing_group = StudentGroup.objects.filter(
                leader=request.user,
                stage_period=stage_period,
            ).first()
            if existing_group:
                return BadRequestError("Vous êtes déjà leader d'un groupe pour cette période Stage.").to_response()

            project_type = AcademicProjectType.INTERNSHIP

        # Create the group
        group = StudentGroup.objects.create(
            name=data.name,
            leader=request.user,
            project_type=project_type,
            ter_period=ter_period,
            stage_period=stage_period,
        )

        # Reload with related data
        group = StudentGroup.objects.select_related(
            "leader", "ter_period", "stage_period"
        ).prefetch_related("members").get(id=group.id)

        return 201, group_to_detail_schema(group)
