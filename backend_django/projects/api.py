from typing import List
from django.db.models import Q
from ninja_extra import api_controller, http_get
from backend_django.core.api.base import BaseAPI
from backend_django.projects.models import Project
from backend_django.projects.schemas import ProjectSchema


@api_controller("/projects", tags=["Projects"])
class ProjectController(BaseAPI):

    @http_get("/me", response=List[ProjectSchema])
    def my_projects(self, request):
        user = request.user

        return (
            Project.objects
            .filter(Q(author=user) | Q(externes=user))
            .distinct()
            .select_related("ter")
            .prefetch_related("author", "externes")
        )
