from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TerConfig(AppConfig):
    name = "backend_django.ter"
    verbose_name = _("TER Management")
