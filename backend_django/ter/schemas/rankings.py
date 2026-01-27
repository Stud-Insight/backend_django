"""
TER Ranking schemas for API requests and responses.
"""

from uuid import UUID

from ninja import Schema
from pydantic import field_validator, model_validator


class TERRankingItemSchema(Schema):
    """Schema for a single ranking item."""

    subject_id: UUID
    subject_title: str
    rank: int


class TERRankingListSchema(Schema):
    """Schema for ranking list response."""

    group_id: UUID
    group_name: str
    ter_period_id: UUID
    rankings: list[TERRankingItemSchema]
    submitted_at: str | None


class TERRankingCreateSchema(Schema):
    """Schema for submitting group rankings."""

    rankings: list[dict]  # List of {subject_id: UUID, rank: int}

    @field_validator("rankings")
    @classmethod
    def validate_rankings(cls, v: list) -> list:
        if not v:
            raise ValueError("Le classement ne peut pas etre vide.")
        if len(v) < 1:
            raise ValueError("Vous devez classer au moins 1 sujet.")

        ranks = []
        subject_ids = []
        for item in v:
            if "subject_id" not in item or "rank" not in item:
                raise ValueError("Chaque element doit avoir 'subject_id' et 'rank'.")
            rank = item["rank"]
            if rank < 1:
                raise ValueError("Les rangs doivent commencer a 1.")
            ranks.append(rank)
            subject_ids.append(str(item["subject_id"]))

        # Check for duplicate ranks
        if len(ranks) != len(set(ranks)):
            raise ValueError("Les rangs doivent etre uniques.")

        # Check for duplicate subjects
        if len(subject_ids) != len(set(subject_ids)):
            raise ValueError("Un sujet ne peut apparaitre qu'une seule fois.")

        # Check ranks are consecutive starting from 1
        expected_ranks = list(range(1, len(ranks) + 1))
        if sorted(ranks) != expected_ranks:
            raise ValueError("Les rangs doivent etre consecutifs (1, 2, 3, ...).")

        return v
