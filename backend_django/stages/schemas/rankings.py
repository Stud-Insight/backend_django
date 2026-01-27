"""
Stage Ranking schemas for API requests and responses.
"""

from uuid import UUID

from ninja import Schema
from pydantic import field_validator


class StageRankingItemSchema(Schema):
    """Schema for a single ranking item."""

    offer_id: UUID
    offer_title: str
    company_name: str
    rank: int


class StageRankingListSchema(Schema):
    """Schema for ranking list response."""

    student_id: UUID
    stage_period_id: UUID
    rankings: list[StageRankingItemSchema]
    submitted_at: str | None


class StageRankingCreateSchema(Schema):
    """Schema for submitting student rankings."""

    stage_period_id: UUID
    rankings: list[dict]  # List of {offer_id: UUID, rank: int}

    @field_validator("rankings")
    @classmethod
    def validate_rankings(cls, v: list) -> list:
        if not v:
            raise ValueError("Le classement ne peut pas etre vide.")
        if len(v) < 1:
            raise ValueError("Vous devez classer au moins 1 offre.")

        ranks = []
        offer_ids = []
        for item in v:
            if "offer_id" not in item or "rank" not in item:
                raise ValueError("Chaque element doit avoir 'offer_id' et 'rank'.")
            rank = item["rank"]
            if rank < 1:
                raise ValueError("Les rangs doivent commencer a 1.")
            ranks.append(rank)
            offer_ids.append(str(item["offer_id"]))

        # Check for duplicate ranks
        if len(ranks) != len(set(ranks)):
            raise ValueError("Les rangs doivent etre uniques.")

        # Check for duplicate offers
        if len(offer_ids) != len(set(offer_ids)):
            raise ValueError("Une offre ne peut apparaitre qu'une seule fois.")

        # Check ranks are consecutive starting from 1
        expected_ranks = list(range(1, len(ranks) + 1))
        if sorted(ranks) != expected_ranks:
            raise ValueError("Les rangs doivent etre consecutifs (1, 2, 3, ...).")

        return v
