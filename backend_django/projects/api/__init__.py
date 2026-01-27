"""
Project API controllers.

NOTE: TER/Stage periods APIs have been moved to:
- ter/api/periods.py → /api/ter/periods/
- stages/api/periods.py → /api/stages/periods/
"""

from backend_django.projects.api.attachments import AttachmentsController
from backend_django.projects.api.groups import GroupController
from backend_django.projects.api.projects import AcademicProjectController
from backend_django.projects.api.proposals import ProposalController

__all__ = [
    "AttachmentsController",
    "AcademicProjectController",
    "GroupController",
    "ProposalController",
]
