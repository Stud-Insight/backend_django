"""
Project, attachment, and proposal schemas.
"""

from backend_django.projects.schemas.attachments import AcademicProjectCreateSchema as LegacyAcademicProjectCreateSchema
from backend_django.projects.schemas.attachments import AcademicProjectSchema
from backend_django.projects.schemas.attachments import AttachmentSchema
from backend_django.projects.schemas.attachments import AttachmentUploadResponse
from backend_django.projects.schemas.projects import AcademicProjectCreateSchema
from backend_django.projects.schemas.projects import AcademicProjectDetailSchema
from backend_django.projects.schemas.projects import AcademicProjectListSchema
from backend_django.projects.schemas.projects import AcademicProjectUpdateSchema
from backend_django.projects.schemas.projects import AttachmentMinimalSchema
from backend_django.projects.schemas.projects import MessageSchema
from backend_django.projects.schemas.projects import ProjectStatusUpdateSchema
from backend_django.projects.schemas.projects import UserMinimalSchema
from backend_django.projects.schemas.proposals import ApplicationCreateSchema
from backend_django.projects.schemas.proposals import ApplicationSchema
from backend_django.projects.schemas.proposals import ProposalCreateSchema
from backend_django.projects.schemas.proposals import ProposalDetailSchema
from backend_django.projects.schemas.proposals import ProposalListSchema
from backend_django.projects.schemas.proposals import ProposalStatusUpdateSchema
from backend_django.projects.schemas.proposals import ProposalUpdateSchema

__all__ = [
    # Attachments (legacy)
    "AttachmentSchema",
    "AttachmentUploadResponse",
    "AcademicProjectSchema",  # Legacy schema for backward compatibility
    "LegacyAcademicProjectCreateSchema",
    # Attachments (new)
    "AttachmentMinimalSchema",
    # Projects
    "UserMinimalSchema",
    "AcademicProjectListSchema",
    "AcademicProjectDetailSchema",
    "AcademicProjectCreateSchema",
    "AcademicProjectUpdateSchema",
    "ProjectStatusUpdateSchema",
    "MessageSchema",
    # Proposals
    "ProposalListSchema",
    "ProposalDetailSchema",
    "ProposalCreateSchema",
    "ProposalUpdateSchema",
    "ProposalStatusUpdateSchema",
    "ApplicationSchema",
    "ApplicationCreateSchema",
]
