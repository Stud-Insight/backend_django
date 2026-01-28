"""
Role definitions for Stud'Insight.

Defines the 6 roles used across the platform:
- Étudiant: Students who form groups, rank subjects, submit deliverables
- Respo TER: TER coordinators who manage periods, validate subjects, run algorithms
- Respo Stage: Internship coordinators who manage periods, validate offers
- Encadrant: Academic supervisors who propose subjects, grade students
- Externe: External supervisors (companies) who create internship offers
- Admin: System administrators with full access
"""

from enum import Enum


class Role(str, Enum):
    """
    Enum of available roles in Stud'Insight.

    Values match Django Group names exactly.
    """

    ETUDIANT = "Étudiant"
    RESPO_TER = "Respo TER"
    RESPO_STAGE = "Respo Stage"
    ENCADRANT = "Encadrant"
    EXTERNE = "Externe"
    ADMIN = "Admin"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        """Return choices for Django form fields."""
        return [(role.value, role.value) for role in cls]

    @classmethod
    def values(cls) -> list[str]:
        """Return all role values."""
        return [role.value for role in cls]


# Role descriptions for documentation and admin interfaces
ROLE_DESCRIPTIONS = {
    Role.ETUDIANT: "Étudiant - Forme des groupes, classe les sujets, soumet des rendus",
    Role.RESPO_TER: "Respo TER - Gère les périodes TER, valide les sujets, lance l'algorithme",
    Role.RESPO_STAGE: "Respo Stage - Gère les périodes Stage, valide les offres",
    Role.ENCADRANT: "Encadrant - Propose des sujets, note les étudiants",
    Role.EXTERNE: "Externe - Crée des offres de stage, évalue les stagiaires",
    Role.ADMIN: "Admin - Administration système complète",
}


def get_user_roles(user) -> list[str]:
    """
    Get the list of role names for a user.

    Args:
        user: Django User instance

    Returns:
        List of role names the user belongs to
    """
    if not user or not user.is_authenticated:
        return []

    return list(user.groups.values_list("name", flat=True))


def user_has_role(user, role: Role | str) -> bool:
    """
    Check if a user has a specific role.

    Args:
        user: Django User instance
        role: Role enum value or role name string

    Returns:
        True if user has the role
    """
    if not user or not user.is_authenticated:
        return False

    role_name = role.value if isinstance(role, Role) else role
    return user.groups.filter(name=role_name).exists()


def user_has_any_role(user, roles: list[Role | str]) -> bool:
    """
    Check if a user has any of the specified roles.

    Args:
        user: Django User instance
        roles: List of Role enum values or role name strings

    Returns:
        True if user has at least one of the roles
    """
    if not user or not user.is_authenticated:
        return False

    role_names = [r.value if isinstance(r, Role) else r for r in roles]
    return user.groups.filter(name__in=role_names).exists()


# ============================================================================
# Convenience functions for common permission checks
# ============================================================================


def is_admin(user) -> bool:
    """
    Check if user has admin privileges.

    Returns True for superusers or users with Admin role.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_has_role(user, Role.ADMIN)


def is_admin_or_respo(user) -> bool:
    """
    Check if user has admin or respo privileges.

    Returns True for superusers or users with Admin, Respo TER, or Respo Stage roles.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_has_any_role(user, [Role.ADMIN, Role.RESPO_TER, Role.RESPO_STAGE])


def is_ter_admin(user) -> bool:
    """
    Check if user can administer TER-related features.

    Returns True for superusers or users with Admin or Respo TER roles.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_has_any_role(user, [Role.ADMIN, Role.RESPO_TER])


def is_stage_admin(user) -> bool:
    """
    Check if user can administer Stage-related features.

    Returns True for superusers or users with Admin or Respo Stage roles.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_has_any_role(user, [Role.ADMIN, Role.RESPO_STAGE])
