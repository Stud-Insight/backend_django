"""TER schemas for API requests and responses."""

from .periods import (
    TERPeriodCopySchema,
    TERPeriodCreateSchema,
    TERPeriodDetailSchema,
    TERPeriodSchema,
    TERPeriodUpdateSchema,
)
from .rankings import (
    TERRankingCreateSchema,
    TERRankingItemSchema,
    TERRankingListSchema,
)
from .subjects import (
    TERFavoriteSchema,
    TERSubjectCreateSchema,
    TERSubjectDetailSchema,
    TERSubjectListSchema,
    TERSubjectRejectSchema,
    TERSubjectUpdateSchema,
)

__all__ = [
    # Periods
    "TERPeriodSchema",
    "TERPeriodDetailSchema",
    "TERPeriodCreateSchema",
    "TERPeriodUpdateSchema",
    "TERPeriodCopySchema",
    # Subjects
    "TERSubjectListSchema",
    "TERSubjectDetailSchema",
    "TERSubjectCreateSchema",
    "TERSubjectUpdateSchema",
    "TERFavoriteSchema",
    # Rankings
    "TERRankingItemSchema",
    "TERRankingListSchema",
    "TERRankingCreateSchema",
]
