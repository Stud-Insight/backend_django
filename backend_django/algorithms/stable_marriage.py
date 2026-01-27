"""
Stable Marriage Algorithm (Gale-Shapley) for TER and Stage assignments.

Uses the `matching` library (version 1.4.3) for robust implementation.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class AssignmentResult:
    """Result of the assignment algorithm."""

    # group_id -> subject_id mappings
    assignments: dict[UUID, UUID]
    # Groups that couldn't be assigned
    unassigned_groups: list[UUID]
    # Statistics
    total_groups: int
    assigned_count: int
    average_rank: float | None  # Average preference rank achieved


def run_ter_assignment(
    group_rankings: dict[UUID, list[UUID]],
    subject_capacities: dict[UUID, int],
) -> AssignmentResult:
    """
    Run the Gale-Shapley stable matching algorithm for TER assignments.

    Args:
        group_rankings: Dict mapping group_id to ordered list of subject_ids
                       (index 0 = most preferred)
        subject_capacities: Dict mapping subject_id to max number of groups

    Returns:
        AssignmentResult with assignments and statistics
    """
    try:
        from matching.games import HospitalResident
    except ImportError:
        logger.error("matching library not installed. Run: pip install matching==1.4.3")
        raise ImportError("matching library required for assignment algorithm")

    if not group_rankings:
        return AssignmentResult(
            assignments={},
            unassigned_groups=[],
            total_groups=0,
            assigned_count=0,
            average_rank=None,
        )

    # Convert UUIDs to strings for matching library
    group_prefs = {
        str(g_id): [str(s_id) for s_id in s_ids]
        for g_id, s_ids in group_rankings.items()
    }

    # Build subject preferences (subjects rank groups by their ranking order)
    # This gives priority to groups that ranked the subject higher
    subject_prefs: dict[str, list[str]] = defaultdict(list)
    for group_id, subjects in group_rankings.items():
        for rank, subject_id in enumerate(subjects):
            subject_prefs[str(subject_id)].append((rank, str(group_id)))

    # Sort by rank (lower rank = higher preference for the subject)
    for subject_id in subject_prefs:
        subject_prefs[subject_id] = [
            g_id for _, g_id in sorted(subject_prefs[subject_id])
        ]

    # Convert capacities
    capacities = {str(s_id): cap for s_id, cap in subject_capacities.items()}

    # Run Hospital-Resident matching (subjects=hospitals, groups=residents)
    game = HospitalResident.create_from_dictionaries(
        resident_prefs=group_prefs,
        hospital_prefs=dict(subject_prefs),
        capacities=capacities,
    )

    # Solve using optimal algorithm (resident-optimal)
    matching = game.solve(optimal="resident")

    # Extract assignments
    assignments = {}
    for subject, groups in matching.items():
        for group in groups:
            assignments[UUID(group.name)] = UUID(subject.name)

    # Find unassigned groups
    all_groups = set(group_rankings.keys())
    assigned_groups = set(assignments.keys())
    unassigned_groups = list(all_groups - assigned_groups)

    # Calculate average rank achieved
    ranks = []
    for group_id, subject_id in assignments.items():
        prefs = group_rankings[group_id]
        try:
            rank = prefs.index(subject_id) + 1  # 1-indexed
            ranks.append(rank)
        except ValueError:
            pass

    average_rank = sum(ranks) / len(ranks) if ranks else None

    result = AssignmentResult(
        assignments=assignments,
        unassigned_groups=unassigned_groups,
        total_groups=len(group_rankings),
        assigned_count=len(assignments),
        average_rank=average_rank,
    )

    logger.info(
        "TER Assignment completed: %d/%d groups assigned, avg rank: %.2f",
        result.assigned_count,
        result.total_groups,
        result.average_rank or 0,
    )

    return result


def run_stage_assignment(
    student_rankings: dict[UUID, list[UUID]],
    offer_capacities: dict[UUID, int],
) -> AssignmentResult:
    """
    Run the Gale-Shapley stable matching algorithm for Stage assignments.

    Similar to TER but with individual students instead of groups.

    Args:
        student_rankings: Dict mapping student_id to ordered list of offer_ids
                         (index 0 = most preferred)
        offer_capacities: Dict mapping offer_id to max number of students

    Returns:
        AssignmentResult with assignments and statistics
    """
    # Same implementation as TER, just different entity names
    return run_ter_assignment(
        group_rankings=student_rankings,
        subject_capacities=offer_capacities,
    )
