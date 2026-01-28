"""
Project schemas - exports attachment and group schemas.

Legacy AcademicProject and Proposal schemas have been removed.
Use TER schemas (backend_django.ter.schemas) for TER workflows.
Use Stage schemas (backend_django.stages.schemas) for Stage workflows.
"""

# Attachments
from backend_django.projects.schemas.attachments import AttachmentSchema
from backend_django.projects.schemas.attachments import AttachmentUploadResponse

# Groups
from backend_django.projects.schemas.groups import GroupCreateSchema
from backend_django.projects.schemas.groups import GroupDetailSchema
from backend_django.projects.schemas.groups import GroupListSchema
from backend_django.projects.schemas.groups import GroupUpdateSchema
from backend_django.projects.schemas.groups import InvitationCreateSchema
from backend_django.projects.schemas.groups import InvitationResponseSchema
from backend_django.projects.schemas.groups import InvitationSchema
from backend_django.projects.schemas.groups import StagePeriodSchema
from backend_django.projects.schemas.groups import TERPeriodSchema
from backend_django.projects.schemas.groups import TransferLeadershipSchema

# Re-export TER schemas for convenience
from backend_django.ter.schemas import (
    TERFavoriteSchema,
    TERPeriodCopySchema,
    TERPeriodCreateSchema,
    TERPeriodDetailSchema,
    TERPeriodUpdateSchema,
    TERRankingCreateSchema,
    TERRankingItemSchema,
    TERRankingListSchema,
    TERSubjectCreateSchema,
    TERSubjectDetailSchema,
    TERSubjectListSchema,
    TERSubjectUpdateSchema,
)

# Re-export Stage schemas for convenience
from backend_django.stages.schemas import (
    StageFavoriteSchema,
    StageOfferCreateSchema,
    StageOfferDetailSchema,
    StageOfferListSchema,
    StageOfferUpdateSchema,
    StagePeriodCreateSchema,
    StagePeriodDetailSchema,
    StagePeriodUpdateSchema,
    StageRankingCreateSchema,
    StageRankingItemSchema,
    StageRankingListSchema,
)

__all__ = [
    # Attachments
    "AttachmentSchema",
    "AttachmentUploadResponse",
    # Groups
    "GroupListSchema",
    "GroupDetailSchema",
    "GroupCreateSchema",
    "GroupUpdateSchema",
    "TERPeriodSchema",
    "StagePeriodSchema",
    # Invitations
    "InvitationSchema",
    "InvitationCreateSchema",
    "InvitationResponseSchema",
    # Leadership
    "TransferLeadershipSchema",
    # TER schemas
    "TERPeriodDetailSchema",
    "TERPeriodCreateSchema",
    "TERPeriodUpdateSchema",
    "TERPeriodCopySchema",
    "TERSubjectListSchema",
    "TERSubjectDetailSchema",
    "TERSubjectCreateSchema",
    "TERSubjectUpdateSchema",
    "TERFavoriteSchema",
    "TERRankingItemSchema",
    "TERRankingListSchema",
    "TERRankingCreateSchema",
    # Stage schemas
    "StagePeriodDetailSchema",
    "StagePeriodCreateSchema",
    "StagePeriodUpdateSchema",
    "StageOfferListSchema",
    "StageOfferDetailSchema",
    "StageOfferCreateSchema",
    "StageOfferUpdateSchema",
    "StageFavoriteSchema",
    "StageRankingItemSchema",
    "StageRankingListSchema",
    "StageRankingCreateSchema",
]
