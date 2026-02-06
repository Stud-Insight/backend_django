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
from .deliverables import (
    FILE_SIZE_LIMIT_BYTES,
    FILE_SIZE_LIMIT_MB,
    TERDeliverableListSchema,
    TERDeliverableSchema,
    TERDeliverableUpdateSchema,
    TERDeliverableUploadResponse,
    TERDeliverableUploadSchema,
    UploadStatusResponse,
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
    # Deliverables
    "TERDeliverableSchema",
    "TERDeliverableListSchema",
    "TERDeliverableUploadSchema",
    "TERDeliverableUploadResponse",
    "TERDeliverableUpdateSchema",
    "UploadStatusResponse",
    "FILE_SIZE_LIMIT_MB",
    "FILE_SIZE_LIMIT_BYTES",
]
