"""
TER Student API controller.

Provides endpoints for students to view their TER context.
"""

from uuid import UUID

from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja_extra import api_controller, http_get

from backend_django.core.api import BaseAPI, IsAuthenticated
from backend_django.core.exceptions import (
    ErrorSchema,
    NotAuthenticatedError,
)
from backend_django.groups.models import Group, GroupStatus
from backend_django.groups.schemas.groups import GroupDetailSchema, TERPeriodSchema, UserMinimalSchema
from backend_django.ter.models import PeriodStatus, TERPeriod, TERSubject
from backend_django.ter.schemas.periods import TERPeriodDetailSchema
from backend_django.ter.schemas.student import MyTERSchema
from backend_django.ter.schemas.subjects import TERSubjectListSchema


# ==================== Helper Functions ====================


def ter_period_to_detail_schema(period: TERPeriod) -> TERPeriodDetailSchema:
    """Convert TERPeriod to detailed schema."""
    return TERPeriodDetailSchema(
        id=period.id,
        name=period.name,
        academic_year=period.academic_year,
        status=period.status,
        group_formation_start=str(period.group_formation_start),
        group_formation_end=str(period.group_formation_end),
        subject_selection_start=str(period.subject_selection_start),
        subject_selection_end=str(period.subject_selection_end),
        assignment_date=str(period.assignment_date),
        project_start=str(period.project_start),
        project_end=str(period.project_end),
        min_group_size=period.min_group_size,
        max_group_size=period.max_group_size,
        created=str(period.created),
        modified=str(period.modified),
    )


def ter_period_to_schema(period: TERPeriod) -> TERPeriodSchema:
    """Convert TERPeriod to basic schema."""
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


def group_to_detail_schema(group: Group) -> GroupDetailSchema:
    """Convert Group to detail schema."""
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
        stage_period=None,  # This endpoint is TER-only
        assigned_subject_id=group.assigned_subject_id,
    )


def user_to_minimal_schema(user) -> UserMinimalSchema | None:
    """Convert User to minimal schema."""
    if not user:
        return None
    return UserMinimalSchema(
        id=user.id,
        email=user.email,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
    )


def subject_to_list_schema(subject: TERSubject) -> TERSubjectListSchema:
    """Convert TERSubject to list schema."""
    return TERSubjectListSchema(
        id=subject.id,
        title=subject.title,
        description=subject.description,
        domain=subject.domain,
        tags=subject.tags or [],
        taches=subject.taches or [],
        professor=user_to_minimal_schema(subject.professor),
        status=subject.status,
        max_groups=subject.max_groups,
        min_group_size=subject.min_group_size,
        max_group_size=subject.max_group_size,
        ter_period_id=subject.ter_period_id,
        created=str(subject.created),
    )


# ==================== TER Student Controller ====================


@api_controller("/ter", tags=["TER Student"], permissions=[IsAuthenticated])
class TERStudentController(BaseAPI):
    """API for student TER context."""

    @http_get(
        "/my",
        response={200: MyTERSchema, 401: ErrorSchema},
        url_name="ter_my",
    )
    def get_my_ter(
        self,
        request: HttpRequest,
        ter_period_id: UUID | None = None,
    ):
        """
        Get the complete TER context for the connected student.

        Returns:
        - ter_period: The active TER period where the student is enrolled
        - group: The student's group in that period (if any)
        - subject: The subject assigned to the group (if any)
        - status: A status string summarizing the student's current state:
            - "no_period": Student is not enrolled in any open TER period
            - "no_group": Student is enrolled but has no group
            - "group_forming": Student is in a group that is still open (ouvert)
            - "group_formed": Student is in a formed group (forme)
            - "subject_assigned": Student's group has an assigned subject (cloture)

        Query params:
        - ter_period_id: Optional UUID to query a specific period
        """
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        user = request.user

        # 1. Find the TER period
        if ter_period_id:
            period = get_object_or_404(TERPeriod, id=ter_period_id)
        else:
            # Find an open period where the student is enrolled
            period = TERPeriod.objects.filter(
                status=PeriodStatus.OPEN,
                enrolled_students=user,
            ).first()

        if not period:
            return 200, MyTERSchema(
                ter_period=None,
                group=None,
                subject=None,
                status="no_period",
            )

        # 2. Find the student's group in this period
        group = Group.objects.filter(
            ter_period=period,
            members=user,
        ).select_related(
            "leader",
            "ter_period",
            "assigned_subject",
            "assigned_subject__professor",
        ).prefetch_related("members").first()

        if not group:
            return 200, MyTERSchema(
                ter_period=ter_period_to_detail_schema(period),
                group=None,
                subject=None,
                status="no_group",
            )

        # 3. Determine the status based on group state
        if group.assigned_subject:
            status = "subject_assigned"
        elif group.status == GroupStatus.FORME:
            status = "group_formed"
        else:
            status = "group_forming"

        # 4. Build the response
        return 200, MyTERSchema(
            ter_period=ter_period_to_detail_schema(period),
            group=group_to_detail_schema(group),
            subject=subject_to_list_schema(group.assigned_subject) if group.assigned_subject else None,
            status=status,
        )
