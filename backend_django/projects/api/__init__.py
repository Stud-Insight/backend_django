"""
Project API controllers.

Legacy AcademicProjectController and ProposalController have been removed.

Current controllers:
- AttachmentsController: File uploads/downloads (/api/attachments/)

For Groups API, use: groups/api/ → /api/groups/
For TER/Stage APIs, use:
- ter/api/ → /api/ter/
- stages/api/ → /api/stages/
"""

from backend_django.projects.api.attachments import AttachmentsController

__all__ = [
    "AttachmentsController",
]
