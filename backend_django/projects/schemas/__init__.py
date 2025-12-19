"""
Project and attachment schemas.
"""

from backend_django.projects.schemas.attachments import AcademicProjectCreateSchema
from backend_django.projects.schemas.attachments import AcademicProjectSchema
from backend_django.projects.schemas.attachments import AttachmentSchema
from backend_django.projects.schemas.attachments import AttachmentUploadResponse

__all__ = [
    "AttachmentSchema",
    "AttachmentUploadResponse",
    "AcademicProjectSchema",
    "AcademicProjectCreateSchema",
]
