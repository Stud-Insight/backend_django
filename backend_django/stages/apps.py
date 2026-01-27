from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StagesConfig(AppConfig):
    name = "backend_django.stages"
    verbose_name = _("Internship Management")
