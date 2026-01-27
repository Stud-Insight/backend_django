"""
Stage Period schemas for API requests and responses.
"""

from datetime import date
from uuid import UUID

from ninja import Schema
from pydantic import field_validator, model_validator


class StagePeriodSchema(Schema):
    """Basic schema for Stage period list responses."""

    id: UUID
    name: str
    academic_year: str
    status: str
    application_start: str
    application_end: str


class StagePeriodDetailSchema(Schema):
    """Detailed schema for Stage period responses."""

    id: UUID
    name: str
    academic_year: str
    status: str
    offer_submission_start: str
    offer_submission_end: str
    application_start: str
    application_end: str
    internship_start: str
    internship_end: str
    created: str
    modified: str


class StagePeriodCreateSchema(Schema):
    """Schema for creating a Stage period."""

    name: str
    academic_year: str
    offer_submission_start: date
    offer_submission_end: date
    application_start: date
    application_end: date
    internship_start: date
    internship_end: date

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

    @model_validator(mode="after")
    def validate_dates(self):
        """Validate that dates are in logical order."""
        errors = []

        if self.offer_submission_end <= self.offer_submission_start:
            errors.append("La fin de soumission des offres doit etre apres le debut.")

        if self.application_start < self.offer_submission_end:
            errors.append("Les candidatures doivent commencer apres la fin de soumission des offres.")

        if self.application_end <= self.application_start:
            errors.append("La fin des candidatures doit etre apres le debut.")

        if self.internship_start < self.application_end:
            errors.append("Le stage doit commencer apres la fin des candidatures.")

        if self.internship_end <= self.internship_start:
            errors.append("La fin du stage doit etre apres le debut.")

        if errors:
            raise ValueError(" ".join(errors))

        return self


class StagePeriodUpdateSchema(Schema):
    """Schema for updating a Stage period."""

    name: str | None = None
    offer_submission_start: date | None = None
    offer_submission_end: date | None = None
    application_start: date | None = None
    application_end: date | None = None
    internship_start: date | None = None
    internship_end: date | None = None

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
