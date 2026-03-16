"""
Pre-Assignment Group Balancing Algorithm.

Handles the balancing of incomplete groups and solo students before
the stable marriage assignment algorithm runs.

This module provides functionality to:
- Identify problematic entities (solo students, incomplete groups)
- Calculate preference similarity between entities
- Merge solo students into groups
- Merge incomplete groups together
- Fill remaining gaps with round-robin assignment
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from django.db import transaction
from django.db.models import Count

if TYPE_CHECKING:
    from backend_django.groups.models import Group
    from backend_django.ter.models import TERPeriod
    from backend_django.users.models import User

logger = logging.getLogger(__name__)


@dataclass
class ProblematicEntities:
    """Container for entities that need balancing."""

    solo_students: list[UUID]  # Students enrolled but not in any group
    incomplete_groups: list[UUID]  # Groups with member_count < min_group_size
    solo_groups: list[UUID]  # Groups with exactly 1 member

    def __bool__(self) -> bool:
        """Return True if there are any problematic entities."""
        return bool(self.solo_students or self.incomplete_groups or self.solo_groups)


@dataclass
class MergeOperation:
    """Record of a single merge operation."""

    operation_type: str  # "student_to_group", "merge_groups"
    entity_a_id: UUID
    entity_b_id: UUID
    similarity_score: float
    reason: str = ""


@dataclass
class BalancingResult:
    """Result of the balancing algorithm."""

    operations: list[MergeOperation] = field(default_factory=list)
    students_assigned: int = 0
    groups_merged: int = 0
    groups_auto_formed: int = 0
    warnings: list[str] = field(default_factory=list)
    remaining_solo_students: list[UUID] = field(default_factory=list)
    remaining_incomplete_groups: list[UUID] = field(default_factory=list)
    success: bool = True
    message: str = ""


def identify_problematic_entities(period: "TERPeriod") -> ProblematicEntities:
    """
    Identify students and groups that need attention before assignment.

    Args:
        period: The TERPeriod to analyze

    Returns:
        ProblematicEntities containing lists of UUIDs
    """
    from backend_django.groups.models import Group, GroupStatus
    from backend_django.users.models import User

    # Get all enrolled students
    enrolled_ids = set(period.enrolled_students.values_list("id", flat=True))

    # Get all groups for this period
    groups = Group.objects.filter(ter_period=period).annotate(
        members_count=Count("members")  # Use different name to avoid property conflict
    )

    # Students in groups (any group for this period)
    students_in_groups_ids = set(
        User.objects.filter(student_groups__ter_period=period)
        .distinct()
        .values_list("id", flat=True)
    )

    # Solo students: enrolled but not in any group
    solo_students = list(enrolled_ids - students_in_groups_ids)

    # Incomplete groups: members_count < min_group_size and still "ouvert"
    incomplete_groups = []
    solo_groups = []

    for group in groups:
        if group.status == GroupStatus.OUVERT:
            if group.members_count < period.min_group_size:
                incomplete_groups.append(group.id)
                if group.members_count == 1:
                    solo_groups.append(group.id)

    logger.info(
        "BALANCING: Period %s - %d solo students, %d incomplete groups (%d solo groups)",
        period.id,
        len(solo_students),
        len(incomplete_groups),
        len(solo_groups),
    )

    return ProblematicEntities(
        solo_students=solo_students,
        incomplete_groups=incomplete_groups,
        solo_groups=solo_groups,
    )


def get_student_preferences(student_id: UUID, period: "TERPeriod") -> dict[UUID, int]:
    """
    Get a student's subject preferences from TERIndividualRanking.

    Args:
        student_id: The student's UUID
        period: The TERPeriod

    Returns:
        Dict mapping subject_id to preference rank (1 = most preferred)
    """
    from backend_django.groups.models import Group
    from backend_django.ter.models import TERIndividualRanking

    group = Group.objects.filter(
        ter_period=period, members__id=student_id
    ).first()

    if not group:
        return {}

    rankings = TERIndividualRanking.objects.filter(
        user_id=student_id, group=group
    ).values_list("subject_id", "rank")

    return dict(rankings)


def get_group_preferences(group_id: UUID, period: "TERPeriod") -> dict[UUID, int]:
    """
    Get a group's subject preferences from TERRanking.

    Args:
        group_id: The group's UUID
        period: The TERPeriod

    Returns:
        Dict mapping subject_id to rank (1 = most preferred)
    """
    from backend_django.ter.models import TERRanking

    rankings = TERRanking.objects.filter(
        group_id=group_id, subject__ter_period=period
    ).values_list("subject_id", "rank")

    return dict(rankings)


def calculate_similarity_score(
    prefs_a: dict[UUID, int], prefs_b: dict[UUID, int]
) -> float:
    """
    Calculate similarity between two preference sets.

    Returns 0.0 - 1.0 (1.0 = perfect match)

    - Both have preferences: weighted overlap of ranked subjects
    - One has preferences: 0.3 (partial match potential)
    - Neither has preferences: 0.5 (neutral)

    Args:
        prefs_a: First entity's preferences {subject_id: rank}
        prefs_b: Second entity's preferences {subject_id: rank}

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not prefs_a and not prefs_b:
        return 0.5  # Both have no preferences - neutral

    if not prefs_a or not prefs_b:
        return 0.3  # One has preferences - slight preference to match with them

    # Find common subjects
    common = set(prefs_a.keys()) & set(prefs_b.keys())

    if not common:
        return 0.0  # No overlap in preferences

    # Calculate weighted overlap score
    # Higher weight for subjects ranked highly by both
    max_rank = max(max(prefs_a.values()), max(prefs_b.values()))
    score = 0.0

    for subject_id in common:
        rank_a = prefs_a[subject_id]
        rank_b = prefs_b[subject_id]

        # Similarity based on rank difference (closer ranks = higher similarity)
        rank_similarity = 1 - abs(rank_a - rank_b) / max_rank

        # Weight by average position (top choices matter more)
        avg_rank = (rank_a + rank_b) / 2
        position_weight = 1 / avg_rank

        score += rank_similarity * position_weight

    # Normalize by number of common subjects
    return min(score / len(common), 1.0)


def get_entity_preferences(
    entity_id: UUID, entity_type: str, period: "TERPeriod"
) -> dict[UUID, int]:
    """
    Get preferences for an entity (student or group).

    Args:
        entity_id: The entity's UUID
        entity_type: "student" or "group"
        period: The TERPeriod

    Returns:
        Dict mapping subject_id to rank
    """
    if entity_type == "student":
        return get_student_preferences(entity_id, period)
    elif entity_type == "group":
        return get_group_preferences(entity_id, period)
    return {}


def find_best_match(
    entity_id: UUID,
    entity_type: str,
    candidates: list[tuple[UUID, str]],
    period: "TERPeriod",
) -> tuple[UUID | None, float]:
    """
    Find the best matching candidate for an entity.

    Args:
        entity_id: The entity looking for a match
        entity_type: "student" or "group"
        candidates: List of (candidate_id, candidate_type) tuples
        period: The TERPeriod

    Returns:
        Tuple of (best_candidate_id, similarity_score) or (None, 0.0)
    """
    prefs_a = get_entity_preferences(entity_id, entity_type, period)

    best_match = None
    best_score = -1.0

    for candidate_id, candidate_type in candidates:
        prefs_b = get_entity_preferences(candidate_id, candidate_type, period)
        score = calculate_similarity_score(prefs_a, prefs_b)

        if score > best_score:
            best_score = score
            best_match = candidate_id

    return best_match, best_score


def add_student_to_group(
    student_id: UUID, group_id: UUID, period: "TERPeriod", reason: str = ""
) -> MergeOperation:
    """
    Add a student to a group.

    Args:
        student_id: The student's UUID
        group_id: The target group's UUID
        period: The TERPeriod
        reason: Reason for the operation

    Returns:
        MergeOperation record
    """
    from backend_django.groups.models import Group
    from backend_django.users.models import User

    student = User.objects.get(id=student_id)
    group = Group.objects.get(id=group_id)

    # Add student to group members
    group.members.add(student)

    # Calculate similarity for the record
    student_prefs = get_student_preferences(student_id, period)
    group_prefs = get_group_preferences(group_id, period)
    similarity = calculate_similarity_score(student_prefs, group_prefs)

    logger.info(
        "BALANCING: Added student %s to group %s (similarity: %.2f)",
        student_id,
        group_id,
        similarity,
    )

    return MergeOperation(
        operation_type="student_to_group",
        entity_a_id=student_id,
        entity_b_id=group_id,
        similarity_score=similarity,
        reason=reason or "Automatic balancing - student to group",
    )


def merge_groups(
    group_a_id: UUID,
    group_b_id: UUID,
    period: "TERPeriod",
    keep_group_id: UUID | None = None,
    reason: str = "",
) -> MergeOperation:
    """
    Merge two groups, keeping one and dissolving the other.

    The surviving group keeps its rankings. The dissolved group's members
    are moved to the surviving group and its rankings are deleted.

    Args:
        group_a_id: First group's UUID
        group_b_id: Second group's UUID
        period: The TERPeriod
        keep_group_id: Which group to keep (defaults to group_a)
        reason: Reason for the operation

    Returns:
        MergeOperation record
    """
    from backend_django.groups.models import Group, GroupInvitation, InvitationStatus
    from backend_django.ter.models import TERRanking

    # Lock both groups in consistent order to prevent deadlocks
    ordered_ids = sorted([group_a_id, group_b_id])
    groups = {
        g.id: g
        for g in Group.objects.select_for_update().filter(id__in=ordered_ids).order_by("id")
    }
    group_a = groups[group_a_id]
    group_b = groups[group_b_id]

    # Determine which group to keep
    if keep_group_id:
        keep_group = groups[keep_group_id]
        dissolve_group = groups[group_a_id if keep_group_id == group_b_id else group_b_id]
    else:
        # Default: keep the group with more members, or group_a on tie
        if group_b.member_count > group_a.member_count:
            keep_group = group_b
            dissolve_group = group_a
        else:
            keep_group = group_a
            dissolve_group = group_b

    # Calculate similarity for the record
    prefs_a = get_group_preferences(group_a_id, period)
    prefs_b = get_group_preferences(group_b_id, period)
    similarity = calculate_similarity_score(prefs_a, prefs_b)

    # Move members from dissolve_group to keep_group
    members_to_move = list(dissolve_group.members.all())
    for member in members_to_move:
        keep_group.members.add(member)

    # Cancel pending invitations for the dissolved group
    GroupInvitation.objects.filter(
        group=dissolve_group, status=InvitationStatus.PENDING
    ).update(status=InvitationStatus.CANCELLED)

    # Delete rankings for the dissolved group (keep_group's rankings survive)
    TERRanking.objects.filter(group=dissolve_group).delete()

    # Delete the dissolved group
    dissolve_group.delete()

    logger.info(
        "BALANCING: Merged groups %s and %s → kept %s (similarity: %.2f)",
        group_a_id,
        group_b_id,
        keep_group.id,
        similarity,
    )

    return MergeOperation(
        operation_type="merge_groups",
        entity_a_id=group_a_id,
        entity_b_id=group_b_id,
        similarity_score=similarity,
        reason=reason or f"Automatic balancing - merged into {keep_group.name}",
    )


def run_balancing(
    period: "TERPeriod",
    merge_solo_students: bool = True,
    merge_incomplete_groups: bool = True,
    auto_form_groups: bool = True,
    dry_run: bool = False,
) -> BalancingResult:
    """
    Run the full balancing algorithm for a TER period.

    Steps:
    1. Identify problematic entities
    2. Merge solo students into incomplete groups (best match by similarity)
    3. Merge solo groups together
    4. Fill remaining incomplete groups with unassigned students (round-robin)
    5. Auto-form groups that meet min_group_size

    Args:
        period: The TERPeriod to balance
        merge_solo_students: Whether to merge solo students into groups
        merge_incomplete_groups: Whether to merge incomplete groups
        auto_form_groups: Whether to auto-form groups after balancing
        dry_run: If True, don't actually perform operations

    Returns:
        BalancingResult with all operations and statistics
    """
    from backend_django.groups.models import Group, GroupStatus

    result = BalancingResult()

    # Step 1: Identify problematic entities
    entities = identify_problematic_entities(period)

    if not entities:
        result.message = "Aucune entite a equilibrer."
        return result

    if dry_run:
        result.remaining_solo_students = entities.solo_students
        result.remaining_incomplete_groups = entities.incomplete_groups
        result.message = (
            f"Apercu: {len(entities.solo_students)} etudiants solo, "
            f"{len(entities.incomplete_groups)} groupes incomplets."
        )
        return result

    with transaction.atomic():
        # Track remaining entities
        remaining_solo_students = list(entities.solo_students)
        remaining_incomplete_groups = set(entities.incomplete_groups)

        # Step 2: Merge solo students into incomplete groups
        if merge_solo_students and remaining_solo_students:
            result = _merge_solo_students_into_groups(
                result,
                remaining_solo_students,
                remaining_incomplete_groups,
                period,
            )

        # Step 3: Merge solo groups together
        if merge_incomplete_groups:
            # Re-identify solo groups (some may have been filled)
            solo_groups = [
                g.id
                for g in Group.objects.filter(
                    id__in=remaining_incomplete_groups
                ).annotate(mc=Count("members"))
                if g.mc == 1
            ]

            if solo_groups:
                result = _merge_solo_groups(
                    result, solo_groups, period
                )

        # Step 4: Round-robin fill remaining incomplete groups
        if remaining_solo_students and remaining_incomplete_groups:
            result = _round_robin_fill(
                result,
                remaining_solo_students,
                remaining_incomplete_groups,
                period,
            )

        # Step 5: Auto-form groups meeting min_group_size
        if auto_form_groups:
            # Re-fetch groups to get updated member counts
            for group in Group.objects.filter(ter_period=period, status=GroupStatus.OUVERT):
                if group.member_count >= period.min_group_size:
                    group.form_group()
                    group.save(update_fields=["status"])
                    result.groups_auto_formed += 1
                    logger.info("BALANCING: Auto-formed group %s", group.id)

        # Update remaining entities
        final_entities = identify_problematic_entities(period)
        result.remaining_solo_students = final_entities.solo_students
        result.remaining_incomplete_groups = final_entities.incomplete_groups

        if result.remaining_solo_students or result.remaining_incomplete_groups:
            result.warnings.append(
                f"{len(result.remaining_solo_students)} etudiants solo et "
                f"{len(result.remaining_incomplete_groups)} groupes incomplets restants."
            )

    result.success = True
    result.message = (
        f"Equilibrage termine: {result.students_assigned} etudiants assignes, "
        f"{result.groups_merged} groupes fusionnes, "
        f"{result.groups_auto_formed} groupes formes."
    )

    return result


def _merge_solo_students_into_groups(
    result: BalancingResult,
    solo_students: list[UUID],
    incomplete_groups: set[UUID],
    period: "TERPeriod",
) -> BalancingResult:
    """Merge solo students into incomplete groups by best match."""
    from backend_django.groups.models import Group

    for student_id in list(solo_students):
        # Build candidate list (groups that can accept members)
        candidates = []
        for group_id in incomplete_groups:
            group = Group.objects.annotate(mc=Count("members")).get(id=group_id)
            if group.mc < period.max_group_size:
                candidates.append((group_id, "group"))

        if not candidates:
            break

        # Find best match
        best_group_id, score = find_best_match(student_id, "student", candidates, period)

        if best_group_id:
            operation = add_student_to_group(
                student_id, best_group_id, period,
                reason=f"Similarity score: {score:.2f}"
            )
            result.operations.append(operation)
            result.students_assigned += 1
            solo_students.remove(student_id)

            # Check if group is now complete
            group = Group.objects.annotate(mc=Count("members")).get(id=best_group_id)
            if group.mc >= period.min_group_size:
                incomplete_groups.discard(best_group_id)

    return result


def _merge_solo_groups(
    result: BalancingResult,
    solo_groups: list[UUID],
    period: "TERPeriod",
) -> BalancingResult:
    """Merge solo groups (1 member each) by best match."""
    remaining_solo = list(solo_groups)

    while len(remaining_solo) >= 2:
        # Take first group and find its best match
        group_a_id = remaining_solo[0]
        candidates = [(gid, "group") for gid in remaining_solo[1:]]

        best_group_id, score = find_best_match(group_a_id, "group", candidates, period)

        if best_group_id:
            operation = merge_groups(
                group_a_id, best_group_id, period,
                reason=f"Similarity score: {score:.2f}"
            )
            result.operations.append(operation)
            result.groups_merged += 1

            # Remove merged groups from remaining
            remaining_solo.remove(group_a_id)
            remaining_solo.remove(best_group_id)
        else:
            # No match found, remove from consideration
            remaining_solo.remove(group_a_id)

    return result


def _round_robin_fill(
    result: BalancingResult,
    solo_students: list[UUID],
    incomplete_groups: set[UUID],
    period: "TERPeriod",
) -> BalancingResult:
    """Fill remaining incomplete groups with solo students round-robin style."""
    from backend_django.groups.models import Group

    # Sort groups by member count (fill smallest first)
    group_ids = list(
        Group.objects.filter(id__in=incomplete_groups)
        .annotate(mc=Count("members"))
        .order_by("mc")
        .values_list("id", flat=True)
    )

    student_idx = 0
    for group_id in group_ids:
        # Re-fetch group to get current member count
        group = Group.objects.get(id=group_id)
        while (
            group.member_count < period.min_group_size
            and student_idx < len(solo_students)
        ):
            # Check max_group_size constraint
            if group.member_count >= period.max_group_size:
                break

            student_id = solo_students[student_idx]
            operation = add_student_to_group(
                student_id, group_id, period,
                reason="Round-robin fill"
            )
            result.operations.append(operation)
            result.students_assigned += 1
            student_idx += 1
            # Re-fetch group to get updated member count
            group = Group.objects.get(id=group_id)

    # Remove assigned students from solo_students list
    del solo_students[:student_idx]

    return result


def preview_balancing(period: "TERPeriod") -> dict:
    """
    Preview what balancing would do without making changes.

    Args:
        period: The TERPeriod to analyze

    Returns:
        Dict with preview information
    """
    entities = identify_problematic_entities(period)

    # Calculate potential matches
    potential_matches = []

    # Student to group matches
    for student_id in entities.solo_students[:5]:  # Sample first 5
        candidates = [(gid, "group") for gid in entities.incomplete_groups]
        best_match, score = find_best_match(student_id, "student", candidates, period)
        if best_match:
            potential_matches.append({
                "type": "student_to_group",
                "student_id": str(student_id),
                "group_id": str(best_match),
                "similarity": round(score, 2),
            })

    # Group to group matches
    for i, group_a_id in enumerate(entities.solo_groups[:5]):  # Sample first 5
        candidates = [(gid, "group") for gid in entities.solo_groups[i + 1:]]
        best_match, score = find_best_match(group_a_id, "group", candidates, period)
        if best_match:
            potential_matches.append({
                "type": "merge_groups",
                "group_a_id": str(group_a_id),
                "group_b_id": str(best_match),
                "similarity": round(score, 2),
            })

    return {
        "solo_students_count": len(entities.solo_students),
        "incomplete_groups_count": len(entities.incomplete_groups),
        "solo_groups_count": len(entities.solo_groups),
        "potential_matches_sample": potential_matches,
        "min_group_size": period.min_group_size,
        "max_group_size": period.max_group_size,
    }
