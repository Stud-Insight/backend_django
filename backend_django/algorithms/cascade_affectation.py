"""
Cascade Affectation Algorithm for handling unassigned entities.

When the stable marriage algorithm leaves some groups/students unassigned,
this module provides fallback assignment strategies.
"""

import logging
from uuid import UUID

from .stable_marriage import AssignmentResult

logger = logging.getLogger(__name__)


def cascade_assignment(
    initial_result: AssignmentResult,
    group_rankings: dict[UUID, list[UUID]],
    subject_capacities: dict[UUID, int],
    assigned_counts: dict[UUID, int] | None = None,
) -> AssignmentResult:
    """
    Try to assign remaining unassigned groups to available subjects.

    Uses a greedy approach:
    1. For each unassigned group, go through their preferences in order
    2. Assign to the first subject that still has capacity
    3. Update capacities and continue

    Args:
        initial_result: Result from stable_marriage algorithm
        group_rankings: Original group preferences
        subject_capacities: Original subject capacities
        assigned_counts: Current assignment counts per subject (optional)

    Returns:
        Updated AssignmentResult with cascade assignments
    """
    if not initial_result.unassigned_groups:
        return initial_result

    # Calculate current assignment counts if not provided
    if assigned_counts is None:
        assigned_counts = {}
        for subject_id in initial_result.assignments.values():
            assigned_counts[subject_id] = assigned_counts.get(subject_id, 0) + 1

    # Copy assignments to modify
    assignments = dict(initial_result.assignments)
    still_unassigned = []

    for group_id in initial_result.unassigned_groups:
        assigned = False
        preferences = group_rankings.get(group_id, [])

        for subject_id in preferences:
            capacity = subject_capacities.get(subject_id, 0)
            current_count = assigned_counts.get(subject_id, 0)

            if current_count < capacity:
                # Assign group to this subject
                assignments[group_id] = subject_id
                assigned_counts[subject_id] = current_count + 1
                assigned = True
                logger.info(
                    "CASCADE: Group %s assigned to subject %s (preference #%d)",
                    group_id,
                    subject_id,
                    preferences.index(subject_id) + 1,
                )
                break

        if not assigned:
            still_unassigned.append(group_id)
            logger.warning(
                "CASCADE: Group %s could not be assigned (no capacity)",
                group_id,
            )

    # Recalculate average rank
    ranks = []
    for group_id, subject_id in assignments.items():
        prefs = group_rankings.get(group_id, [])
        try:
            rank = prefs.index(subject_id) + 1
            ranks.append(rank)
        except ValueError:
            pass

    average_rank = sum(ranks) / len(ranks) if ranks else None

    return AssignmentResult(
        assignments=assignments,
        unassigned_groups=still_unassigned,
        total_groups=initial_result.total_groups,
        assigned_count=len(assignments),
        average_rank=average_rank,
    )


def force_assignment(
    unassigned_groups: list[UUID],
    subject_capacities: dict[UUID, int],
    assigned_counts: dict[UUID, int],
) -> dict[UUID, UUID]:
    """
    Force assignment of remaining groups to subjects with capacity.

    This is a last resort when cascade assignment fails.
    Ignores preferences and just fills available slots.

    Args:
        unassigned_groups: Groups that need assignment
        subject_capacities: Subject capacities
        assigned_counts: Current assignment counts

    Returns:
        Dict of forced assignments (group_id -> subject_id)
    """
    forced = {}

    # Find subjects with remaining capacity
    available_subjects = []
    for subject_id, capacity in subject_capacities.items():
        current = assigned_counts.get(subject_id, 0)
        remaining = capacity - current
        if remaining > 0:
            available_subjects.extend([subject_id] * remaining)

    # Assign groups to available slots
    for i, group_id in enumerate(unassigned_groups):
        if i < len(available_subjects):
            subject_id = available_subjects[i]
            forced[group_id] = subject_id
            logger.warning(
                "FORCED: Group %s assigned to subject %s (no preference match)",
                group_id,
                subject_id,
            )

    return forced
