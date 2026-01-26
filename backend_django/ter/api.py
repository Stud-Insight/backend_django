from typing import List

from ninja_extra import api_controller, http_get

from backend_django.core.api.base import BaseAPI
from backend_django.ter.models import TER
from backend_django.ter.schemas import TERListSchema


@api_controller("/ter", tags=["TER"])
class TERController(BaseAPI):
    """
    TER endpoints.
    """

    @http_get("/", response=List[TERListSchema])
    def list_ters(self):
        """
        Retrieve all TERs.
        """
        return TER.objects.all()
