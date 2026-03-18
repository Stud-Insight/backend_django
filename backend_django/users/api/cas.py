"""
CAS SSO Authentication API controller.

Provides endpoints for university CAS (Central Authentication Service) login.
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import logout
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.middleware.csrf import get_token
from django_cas_ng.utils import get_cas_client
from ninja_extra import api_controller
from ninja_extra import http_get
from ninja_extra import http_post

from backend_django.core.api import AllowAny
from backend_django.core.api import BaseAPI
from backend_django.core.exceptions import ErrorSchema
from backend_django.users.models import User
from backend_django.users.schemas import LoginResponseSchema
from backend_django.users.schemas import MessageSchema
from backend_django.users.schemas import UserSchema

logger = logging.getLogger(__name__)


@api_controller("/auth/cas", tags=["CAS Authentication"], permissions=[AllowAny])
class CASController(BaseAPI):
    """
    CAS SSO Authentication endpoints.

    Flow for SPA (React frontend):
    1. Frontend redirects user to GET /api/auth/cas/login
    2. Backend redirects to CAS login page
    3. After CAS login, user is redirected to GET /api/auth/cas/callback?ticket=XXX
    4. Backend validates ticket, creates/logs in user, redirects to frontend with cas_success=true
    """

    def _get_service_url(self, request: HttpRequest) -> str:
        """Build the CAS service URL (callback URL)."""
        scheme = "https" if request.is_secure() else "http"
        host = request.get_host()
        return f"{scheme}://{host}/api/auth/cas/callback"

    @http_get("/login", url_name="cas_api_login")
    def cas_login(self, request: HttpRequest, next: str | None = None):
        """
        Redirect to CAS login page.

        The frontend should redirect the user to this endpoint.
        After successful CAS authentication, the user will be redirected
        back to the callback endpoint.
        """
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        next_url = next or frontend_url
        request.session["cas_next"] = next_url

        service_url = self._get_service_url(request)
        cas_server_url = getattr(settings, "CAS_SERVER_URL", "https://cas.umontpellier.fr/cas/")
        cas_login_url = f"{cas_server_url}login?service={service_url}"

        return HttpResponseRedirect(cas_login_url)

    @http_get("/callback", url_name="cas_api_callback")
    def cas_callback(self, request: HttpRequest, ticket: str | None = None):
        """
        Handle CAS callback after successful authentication.

        CAS redirects here with a ticket parameter that we validate
        to authenticate the user.
        """
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        next_url = request.session.pop("cas_next", frontend_url)

        if not ticket:
            logger.warning("CAS callback received without ticket")
            error_url = f"{frontend_url}/login?error=cas_no_ticket"
            return HttpResponseRedirect(error_url)

        service_url = self._get_service_url(request)
        cas_client = get_cas_client(service_url=service_url, request=request)

        try:
            cas_username, attributes, pgtiou = cas_client.verify_ticket(ticket)
        except Exception:
            logger.exception("CAS ticket verification failed")
            error_url = f"{frontend_url}/login?error=cas_verification_failed"
            return HttpResponseRedirect(error_url)

        if not cas_username:
            logger.warning("CAS ticket verification returned no username")
            error_url = f"{frontend_url}/login?error=cas_invalid_ticket"
            return HttpResponseRedirect(error_url)

        logger.info("CAS authentication successful for: %s", cas_username)
        logger.debug("CAS attributes: %s", attributes)

        user = self._get_or_create_cas_user(cas_username, attributes)

        if user is None:
            logger.error("Failed to create/get user for CAS username: %s", cas_username)
            error_url = f"{frontend_url}/login?error=cas_user_creation_failed"
            return HttpResponseRedirect(error_url)

        if not user.is_active:
            logger.warning("CAS user %s is inactive", cas_username)
            error_url = f"{frontend_url}/login?error=account_disabled"
            return HttpResponseRedirect(error_url)

        login(request, user, backend="django_cas_ng.backends.CASBackend")
        logger.info("User %s logged in via CAS", user.email)

        separator = "&" if "?" in next_url else "?"
        redirect_url = f"{next_url}{separator}cas_success=true"

        return HttpResponseRedirect(redirect_url)

    def _get_or_create_cas_user(self, cas_username: str, attributes: dict) -> User | None:
        """
        Get existing user or create a new one from CAS attributes.
        """
        # Try to find existing CAS user
        try:
            user = User.objects.get(cas_username=cas_username)
            self._update_user_from_attributes(user, attributes)
            return user
        except User.DoesNotExist:
            pass

        # Extract email from attributes
        email = attributes.get("mail") or attributes.get("email")
        if not email:
            email = f"{cas_username}@umontpellier.fr"

        # Check if a user with this email already exists (link accounts)
        try:
            user = User.objects.get(email__iexact=email)
            user.is_cas_user = True
            user.cas_username = cas_username
            self._update_user_from_attributes(user, attributes)
            return user
        except User.DoesNotExist:
            pass

        # Create new user
        try:
            first_name = attributes.get("givenName") or attributes.get("prenom") or cas_username
            last_name = attributes.get("sn") or attributes.get("nom") or ""

            user = User.objects.create(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_cas_user=True,
                cas_username=cas_username,
            )
            user.set_unusable_password()
            user.save()

            logger.info("Created new CAS user: %s (%s)", email, cas_username)
            return user

        except Exception:
            logger.exception("Failed to create CAS user")
            return None

    def _update_user_from_attributes(self, user: User, attributes: dict) -> None:
        """Update user fields from CAS attributes."""
        updated = False

        if not user.is_cas_user:
            user.is_cas_user = True
            updated = True

        first_name = attributes.get("givenName") or attributes.get("prenom")
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            updated = True

        last_name = attributes.get("sn") or attributes.get("nom")
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            updated = True

        email = attributes.get("mail") or attributes.get("email")
        if email and user.email != email:
            user.email = email
            updated = True

        if updated:
            user.save()

    @http_post("/logout", response={200: MessageSchema}, url_name="cas_api_logout")
    def cas_logout(self, request: HttpRequest):
        """
        Logout from both Django and CAS.

        Returns the CAS logout URL for frontend to redirect to.
        """
        logout(request)

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
        cas_server_url = getattr(settings, "CAS_SERVER_URL", "https://cas.umontpellier.fr/cas/")
        cas_logout_url = f"{cas_server_url}logout?service={frontend_url}"

        return 200, MessageSchema(
            success=True,
            message=cas_logout_url,
        )
