from backend_django.core.api.auth import SessionAuth
from backend_django.core.api.base import BaseAPI
from backend_django.core.api.permissions import AllowAny
from backend_django.core.api.permissions import IsAcademic
from backend_django.core.api.permissions import IsAdmin
from backend_django.core.api.permissions import IsAuthenticated
from backend_django.core.api.permissions import IsEncadrant
from backend_django.core.api.permissions import IsEtudiant
from backend_django.core.api.permissions import IsExterne
from backend_django.core.api.permissions import IsRespo
from backend_django.core.api.permissions import IsRespoStage
from backend_django.core.api.permissions import IsRespoTER
from backend_django.core.api.permissions import IsStaff
from backend_django.core.api.permissions import IsStaffOrRespo
from backend_django.core.api.permissions import IsSuperuser

__all__ = [
    "BaseAPI",
    "SessionAuth",
    # Standard permissions
    "AllowAny",
    "IsAuthenticated",
    "IsStaff",
    "IsSuperuser",
    # Role-based permissions
    "IsEtudiant",
    "IsRespoTER",
    "IsRespoStage",
    "IsEncadrant",
    "IsExterne",
    "IsAdmin",
    # Composite permissions
    "IsRespo",
    "IsAcademic",
    "IsStaffOrRespo",
]
