"""
TER Period schemas for API requests and responses.
"""

from datetime import date
from uuid import UUID

from ninja import Schema
from pydantic import field_validator, model_validator


class TERPeriodSchema(Schema):
    """Basic schema for TER period list responses."""

    id: UUID
    name: str
    academic_year: str
    status: str
    group_formation_start: str
    group_formation_end: str
    min_group_size: int
    max_group_size: int


class TERPeriodDetailSchema(Schema):
    """Detailed schema for TER period responses."""

    id: UUID
    name: str
    academic_year: str
    status: str
    group_formation_start: str
    group_formation_end: str
    subject_selection_start: str
    subject_selection_end: str
    assignment_date: str
    project_start: str
    project_end: str
    min_group_size: int
    max_group_size: int
    created: str
    modified: str


class TERPeriodCreateSchema(Schema):
    """Schema for creating a TER period."""

    name: str
    academic_year: str
    group_formation_start: date
    group_formation_end: date
    subject_selection_start: date
    subject_selection_end: date
    assignment_date: date
    project_start: date
    project_end: date
    min_group_size: int = 1
    max_group_size: int = 4

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le nom de la periode est requis.")
        if len(v.strip()) < 3:
            raise ValueError("Le nom doit faire au moins 3 caracteres.")
        return v.strip()

    @field_validator("academic_year")
    @classmethod
    def academic_year_format(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("L'annee academique est requise.")
        v = v.strip()
        # Format: 2024-2025
        if len(v) != 9 or v[4] != "-":
            raise ValueError("Format attendu: 2024-2025")
        try:
            year1 = int(v[:4])
            year2 = int(v[5:])
            if year2 != year1 + 1:
                raise ValueError("L'annee de fin doit etre l'annee de debut + 1")
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError("Format attendu: 2024-2025")
            raise
        return v

    @field_validator("min_group_size", "max_group_size")
    @classmethod
    def validate_group_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("La taille du groupe doit etre au moins 1.")
        if v > 10:
            raise ValueError("La taille du groupe ne peut pas depasser 10.")
        return v

    @model_validator(mode="after")
    def validate_dates(self):
        """Validate that dates are in logical order."""
        errors = []

        if self.group_formation_end <= self.group_formation_start:
            errors.append("La fin de formation des groupes doit etre apres le debut.")

        if self.subject_selection_start < self.group_formation_end:
            errors.append("La selection des sujets doit commencer apres la formation des groupes.")

        if self.subject_selection_end <= self.subject_selection_start:
            errors.append("La fin de selection doit etre apres le debut.")

        if self.assignment_date < self.subject_selection_end:
            errors.append("L'affectation doit etre apres la fin de selection.")

        if self.project_start < self.assignment_date:
            errors.append("Le debut du projet doit etre apres l'affectation.")

        if self.project_end <= self.project_start:
            errors.append("La fin du projet doit etre apres le debut.")

        if self.max_group_size < self.min_group_size:
            errors.append("La taille max du groupe doit etre >= taille min.")

        if errors:
            raise ValueError(" ".join(errors))

        return self


class TERPeriodUpdateSchema(Schema):
    """Schema for updating a TER period."""

    name: str | None = None
    group_formation_start: date | None = None
    group_formation_end: date | None = None
    subject_selection_start: date | None = None
    subject_selection_end: date | None = None
    assignment_date: date | None = None
    project_start: date | None = None
    project_end: date | None = None
    min_group_size: int | None = None
    max_group_size: int | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("Le nom ne peut pas etre vide.")
            if len(v.strip()) < 3:
                raise ValueError("Le nom doit faire au moins 3 caracteres.")
            return v.strip()
        return v


class TERPeriodCopySchema(Schema):
    """Schema for copying a TER period to a new academic year."""

    name: str
    academic_year: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Le nom de la periode est requis.")
        if len(v.strip()) < 3:
            raise ValueError("Le nom doit faire au moins 3 caracteres.")
        return v.strip()

    @field_validator("academic_year")
    @classmethod
    def academic_year_format(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("L'annee academique est requise.")
        v = v.strip()
        if len(v) != 9 or v[4] != "-":
            raise ValueError("Format attendu: 2024-2025")
        try:
            year1 = int(v[:4])
            year2 = int(v[5:])
            if year2 != year1 + 1:
                raise ValueError("L'annee de fin doit etre l'annee de debut + 1")
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError("Format attendu: 2024-2025")
            raise
        return v


class TERPeriodStatsSchema(Schema):
    """Statistics for a TER period dashboard."""

    # Enrolled students
    students_enrolled: int  # Total enrolled in period
    students_in_groups: int  # Students who joined a group
    students_solitaires: int  # Enrolled but no group

    # Groups
    groups_total: int  # Total groups created
    groups_complete: int  # Groups with size >= min_group_size
    groups_assigned: int  # Groups with assigned subject

    # Subjects
    subjects_total: int  # All subjects for period
    subjects_validated: int  # Validated subjects available
    subjects_assigned: int  # Total assignments (groups with subjects)
