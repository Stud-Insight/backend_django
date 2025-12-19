"""
Base API class for auto-discovery of controllers.

All API controllers should inherit from BaseAPI to be automatically
registered with the NinjaExtraAPI instance.
"""


class BaseAPI:
    """
    Marker class for API controllers.

    Controllers inheriting from this class will be automatically
    discovered and registered by the API configuration.

    Example:
        @api_controller("/users", tags=["Users"])
        class UsersController(BaseAPI):
            @http_get("/")
            def list_users(self):
                ...
    """

    pass
