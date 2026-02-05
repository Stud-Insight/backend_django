"""TER schemas for API requests and responses."""

from .balancing import (
    BalanceGroupsRequestSchema,
    BalanceGroupsResponseSchema,
    BalancingOperationListSchema,
    BalancingOperationSchema,
    BalancingPreviewSchema,
    ForceAssignRequestSchema,
    ForceFormRequestSchema,
    MergeGroupsRequestSchema,
    MergeOperationSchema,
    MoveStudentRequestSchema,
    RevertAssignmentRequestSchema,
)
from .periods import (
    TERPeriodCopySchema,
    TERPeriodCreateSchema,
    TERPeriodDetailSchema,
    TERPeriodSchema,
    TERPeriodStatsSchema,
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
    "TERPeriodStatsSchema",
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
    # Balancing
    "MergeOperationSchema",
    "BalancingPreviewSchema",
    "BalanceGroupsRequestSchema",
    "BalanceGroupsResponseSchema",
    "MoveStudentRequestSchema",
    "MergeGroupsRequestSchema",
    "ForceAssignRequestSchema",
    "ForceFormRequestSchema",
    "RevertAssignmentRequestSchema",
    "BalancingOperationSchema",
    "BalancingOperationListSchema",
]
