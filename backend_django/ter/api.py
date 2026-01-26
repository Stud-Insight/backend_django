from typing import List

from ninja_extra import api_controller, http_get, http_post
from backend_django.core.api.base import BaseAPI
from backend_django.ter.models import TER
from backend_django.ter.schemas import TERCreateSchema, TERSchema


@api_controller("/ter", tags=["TER"])
class TERController(BaseAPI):

    @http_get("/", response=List[TERSchema])
    def list_ters(self):
        return TER.objects.all()


    @http_post("/", response=TERSchema)
    def create_ter(self, data: TERCreateSchema):

        ter = TER.objects.create(
            title=data.title,
            code=data.code,
            year=data.year,
            start_date=data.start_date,
            end_date=data.end_date,
            max_allowed_groups = 0,
            status = "EN_COURS",
        )
        return ter
