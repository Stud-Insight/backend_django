"""
Main API configuration for Django Ninja Extra.
All API controllers are automatically registered here.
"""

import importlib
import inspect
import logging

from django.conf import settings
from ninja_extra import NinjaExtraAPI

from backend_django.core.api.base import BaseAPI

logger = logging.getLogger(__name__)

api = NinjaExtraAPI(
    title="Stud'Insight API",
    version="1.0.0",
    description="Backend API for Stud'Insight application",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


def register_controllers_from_module(api_instance: NinjaExtraAPI, module_path: str) -> None:
    """
    Dynamically import and register API controllers from a module.

    Controllers must inherit from BaseAPI to be registered.
    """
    try:
        module = importlib.import_module(module_path)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                inspect.isclass(attr)
                and issubclass(attr, BaseAPI)
                and attr is not BaseAPI
            ):
                logger.debug("Registering controller: %s.%s", module_path, attr_name)
                api_instance.register_controllers(attr)
    except ModuleNotFoundError:
        logger.debug("Module %s not found, skipping", module_path)
    except Exception:
        logger.exception("Error registering controllers from %s", module_path)


# Register controllers from each local app
LOCAL_APPS = [
    "backend_django.users",
    "backend_django.projects",
    "backend_django.chat",
]

for app in LOCAL_APPS:
    register_controllers_from_module(api, f"{app}.api")
