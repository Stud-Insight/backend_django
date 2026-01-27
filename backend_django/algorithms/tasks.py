"""
Celery tasks for running assignment algorithms asynchronously.
"""

import logging
from uuid import UUID

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def run_ter_assignment_task(self, ter_period_id: str) -> dict:
    """
    Run the TER assignment algorithm for a period.

    This task:
    1. Gathers all rankings from groups
    2. Runs the stable marriage algorithm
    3. Applies cascade assignment for unassigned groups
    4. Updates the database with assignments
    5. Transitions groups to 'cloture' status

    Args:
        ter_period_id: UUID of the TER period

    Returns:
        Dict with assignment results and statistics
    """
    from backend_django.groups.models import Group, GroupStatus
    from backend_django.ter.models import SubjectStatus, TERPeriod, TERRanking, TERSubject

    from .cascade_affectation import cascade_assignment
    from .stable_marriage import run_ter_assignment

    period_uuid = UUID(ter_period_id)

    try:
        with transaction.atomic():
            # Get TER period
            period = TERPeriod.objects.get(id=period_uuid)
            logger.info("Starting TER assignment for period: %s", period.name)

            # Get all formed groups with rankings
            groups = Group.objects.filter(
                ter_period=period,
                status=GroupStatus.FORME,
            )

            # Get validated subjects
            subjects = TERSubject.objects.filter(
                ter_period=period,
                status=SubjectStatus.VALIDATED,
            )

            # Build group rankings dict
            group_rankings: dict[UUID, list[UUID]] = {}
            for group in groups:
                rankings = TERRanking.objects.filter(group=group).order_by("rank")
                group_rankings[group.id] = [r.subject_id for r in rankings]

            # Build subject capacities dict
            subject_capacities: dict[UUID, int] = {
                s.id: s.max_groups for s in subjects
            }

            # Skip if no rankings
            if not group_rankings:
                logger.warning("No rankings found for TER period: %s", period.name)
                return {
                    "success": True,
                    "message": "No rankings to process",
                    "total_groups": 0,
                    "assigned": 0,
                    "unassigned": 0,
                }

            # Run stable marriage algorithm
            result = run_ter_assignment(group_rankings, subject_capacities)

            # Apply cascade assignment for unassigned groups
            if result.unassigned_groups:
                assigned_counts = {}
                for subject_id in result.assignments.values():
                    assigned_counts[subject_id] = assigned_counts.get(subject_id, 0) + 1

                result = cascade_assignment(
                    result,
                    group_rankings,
                    subject_capacities,
                    assigned_counts,
                )

            # Apply assignments to database
            for group_id, subject_id in result.assignments.items():
                group = Group.objects.get(id=group_id)
                group.assigned_subject_id = subject_id
                group.close_group()  # Transition to cloture
                group.save()

            logger.info(
                "TER assignment completed for %s: %d/%d assigned, avg rank: %.2f",
                period.name,
                result.assigned_count,
                result.total_groups,
                result.average_rank or 0,
            )

            return {
                "success": True,
                "message": "Assignment completed",
                "total_groups": result.total_groups,
                "assigned": result.assigned_count,
                "unassigned": len(result.unassigned_groups),
                "average_rank": result.average_rank,
                "unassigned_group_ids": [str(g) for g in result.unassigned_groups],
            }

    except TERPeriod.DoesNotExist:
        logger.error("TER period not found: %s", ter_period_id)
        return {
            "success": False,
            "message": f"TER period not found: {ter_period_id}",
        }
    except Exception as e:
        logger.exception("Error running TER assignment: %s", e)
        # Retry on failure
        raise self.retry(exc=e, countdown=60)


@shared_task(bind=True, max_retries=3)
def run_stage_assignment_task(self, stage_period_id: str) -> dict:
    """
    Run the Stage assignment algorithm for a period.

    This task:
    1. Gathers all rankings from students
    2. Runs the stable marriage algorithm
    3. Applies cascade assignment for unassigned students
    4. Updates the database with assignments

    Args:
        stage_period_id: UUID of the Stage period

    Returns:
        Dict with assignment results and statistics
    """
    from backend_django.stages.models import OfferStatus, StageOffer, StagePeriod, StageRanking

    from .cascade_affectation import cascade_assignment
    from .stable_marriage import run_stage_assignment

    period_uuid = UUID(stage_period_id)

    try:
        with transaction.atomic():
            # Get Stage period
            period = StagePeriod.objects.get(id=period_uuid)
            logger.info("Starting Stage assignment for period: %s", period.name)

            # Get validated offers
            offers = StageOffer.objects.filter(
                stage_period=period,
                status=OfferStatus.VALIDATED,
            )

            # Get all student rankings
            student_rankings: dict[UUID, list[UUID]] = {}
            rankings = StageRanking.objects.filter(
                offer__stage_period=period
            ).order_by("student_id", "rank")

            current_student = None
            current_rankings = []
            for ranking in rankings:
                if ranking.student_id != current_student:
                    if current_student is not None:
                        student_rankings[current_student] = current_rankings
                    current_student = ranking.student_id
                    current_rankings = []
                current_rankings.append(ranking.offer_id)

            if current_student is not None:
                student_rankings[current_student] = current_rankings

            # Build offer capacities dict
            offer_capacities: dict[UUID, int] = {
                o.id: o.max_students for o in offers
            }

            # Skip if no rankings
            if not student_rankings:
                logger.warning("No rankings found for Stage period: %s", period.name)
                return {
                    "success": True,
                    "message": "No rankings to process",
                    "total_students": 0,
                    "assigned": 0,
                    "unassigned": 0,
                }

            # Run stable marriage algorithm
            result = run_stage_assignment(student_rankings, offer_capacities)

            # Apply cascade assignment for unassigned students
            if result.unassigned_groups:  # unassigned_groups = unassigned students here
                assigned_counts = {}
                for offer_id in result.assignments.values():
                    assigned_counts[offer_id] = assigned_counts.get(offer_id, 0) + 1

                result = cascade_assignment(
                    result,
                    student_rankings,
                    offer_capacities,
                    assigned_counts,
                )

            # TODO: Apply assignments to database
            # This would create AcademicProject records linking students to offers
            # Implementation depends on the exact data model requirements

            logger.info(
                "Stage assignment completed for %s: %d/%d assigned, avg rank: %.2f",
                period.name,
                result.assigned_count,
                result.total_groups,  # total_groups = total_students here
                result.average_rank or 0,
            )

            return {
                "success": True,
                "message": "Assignment completed",
                "total_students": result.total_groups,
                "assigned": result.assigned_count,
                "unassigned": len(result.unassigned_groups),
                "average_rank": result.average_rank,
                "unassigned_student_ids": [str(s) for s in result.unassigned_groups],
            }

    except StagePeriod.DoesNotExist:
        logger.error("Stage period not found: %s", stage_period_id)
        return {
            "success": False,
            "message": f"Stage period not found: {stage_period_id}",
        }
    except Exception as e:
        logger.exception("Error running Stage assignment: %s", e)
        # Retry on failure
        raise self.retry(exc=e, countdown=60)
