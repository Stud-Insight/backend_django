"""
Authentication API controller.
"""

import logging

from allauth.account.internal.flows.email_verification import send_verification_email_for_user
from allauth.account.models import EmailAddress
from allauth.account.models import EmailConfirmationHMAC
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.http import HttpRequest
from django.middleware.csrf import get_token
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from ninja_extra import api_controller
from ninja_extra import http_get
from ninja_extra import http_post

from backend_django.core.api import BaseAPI
from backend_django.core.api import AllowAny
from backend_django.core.exceptions import AccountDisabledError
from backend_django.core.exceptions import AlreadyExistsError
from backend_django.core.exceptions import BadRequestError
from backend_django.core.exceptions import ErrorSchema
from backend_django.core.exceptions import InvalidCredentialsError
from backend_django.core.exceptions import NotAuthenticatedError
from backend_django.core.exceptions import NotFoundError
from backend_django.core.exceptions import ValidationError
from backend_django.users.models import User
from backend_django.users.schemas import ActivateCheckSchema
from backend_django.users.schemas import ActivateWithPasswordSchema
from backend_django.users.schemas import CSRFTokenSchema
from backend_django.users.schemas import EmailVerifySchema
from backend_django.users.schemas import LoginResponseSchema
from backend_django.users.schemas import LoginSchema
from backend_django.users.schemas import MessageSchema
from backend_django.users.schemas import PasswordChangeSchema
from backend_django.users.schemas import PasswordResetConfirmSchema
from backend_django.users.schemas import PasswordResetRequestSchema
from backend_django.users.schemas import ResendActivationSchema
from backend_django.users.schemas import SignupResponseSchema
from backend_django.users.schemas import SignupSchema
from backend_django.users.schemas import UserSchema

logger = logging.getLogger(__name__)


@api_controller("/auth", tags=["Authentication"], permissions=[AllowAny])
class AuthController(BaseAPI):
    """Authentication endpoints for login, signup, password reset, etc."""

    @http_get("/csrf", response=CSRFTokenSchema, url_name="auth_csrf")
    def get_csrf_token(self, request: HttpRequest):
        """Get a CSRF token for subsequent POST requests."""
        return CSRFTokenSchema(csrf_token=get_token(request))

    @http_post(
        "/login",
        response={200: LoginResponseSchema, 401: ErrorSchema, 400: ErrorSchema},
        url_name="auth_login",
    )
    def login_view(self, request: HttpRequest, data: LoginSchema):
        """Authenticate user with email and password."""
        if not data.email or not data.password:
            return BadRequestError("Email et mot de passe requis.").to_response()

        user = authenticate(request, username=data.email, password=data.password)

        if user is None:
            return InvalidCredentialsError().to_response()

        if not user.is_active:
            return AccountDisabledError().to_response()

        login(request, user)

        return 200, LoginResponseSchema(
            success=True,
            user=UserSchema.from_user(user),
            csrf_token=get_token(request),
        )

    @http_post("/logout", response={200: MessageSchema}, url_name="auth_logout")
    def logout_view(self, request: HttpRequest):
        """Logout the current user and clear session."""
        logout(request)
        return 200, MessageSchema(success=True, message="Déconnexion réussie.")

    @http_get(
        "/me",
        response={200: UserSchema, 401: ErrorSchema},
        url_name="auth_me",
    )
    def me_view(self, request: HttpRequest):
        """Get the current authenticated user's information."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        return 200, UserSchema.from_user(request.user)

    @http_post(
        "/signup",
        response={201: SignupResponseSchema, 400: ErrorSchema, 409: ErrorSchema},
        url_name="auth_signup",
    )
    def signup_view(self, request: HttpRequest, data: SignupSchema):
        """Register a new user account."""
        if User.objects.filter(email__iexact=data.email).exists():
            return AlreadyExistsError("Un compte avec cet email existe déjà.").to_response()

        try:
            validate_password(data.password)
        except DjangoValidationError as e:
            return ValidationError(
                message=" ".join(e.messages),
                details={"password_errors": e.messages},
            ).to_response()

        user = User.objects.create_user(
            email=data.email,
            password=data.password,
            first_name=data.first_name,
            last_name=data.last_name,
            is_active=False,
        )

        EmailAddress.objects.create(
            user=user,
            email=user.email,
            primary=True,
            verified=False,
        )

        try:
            send_verification_email_for_user(request, user)
        except Exception:
            logger.exception("Failed to send verification email")

        return 201, SignupResponseSchema(
            success=True,
            message="Compte créé. Veuillez vérifier votre email pour activer votre compte.",
            requires_email_verification=True,
        )

    @http_post(
        "/verify-email",
        response={200: MessageSchema, 400: ErrorSchema},
        url_name="auth_verify_email",
    )
    def verify_email_view(self, request: HttpRequest, data: EmailVerifySchema):
        """Verify email address using the key from the verification email."""
        try:
            email_confirmation = EmailConfirmationHMAC.from_key(data.key)
            if email_confirmation is None:
                return BadRequestError("Lien de vérification invalide ou expiré.").to_response()

            email_confirmation.confirm(request)

            user = email_confirmation.email_address.user
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])

            return 200, MessageSchema(
                success=True,
                message="Email vérifié avec succès. Vous pouvez maintenant vous connecter.",
            )

        except Exception:
            logger.exception("Email verification failed")
            return BadRequestError("Lien de vérification invalide ou expiré.").to_response()

    @http_post(
        "/resend-activation",
        response={200: MessageSchema, 400: ErrorSchema, 404: ErrorSchema},
        url_name="auth_resend_activation",
    )
    def resend_activation_view(self, request: HttpRequest, data: ResendActivationSchema):
        """Resend the account activation email."""
        try:
            user = User.objects.get(email__iexact=data.email)
        except User.DoesNotExist:
            return NotFoundError("Aucun compte trouvé avec cet email.").to_response()

        email_address = EmailAddress.objects.filter(user=user, email=user.email).first()
        if email_address and email_address.verified:
            return BadRequestError("Ce compte est déjà activé.").to_response()

        if not email_address:
            email_address = EmailAddress.objects.create(
                user=user,
                email=user.email,
                primary=True,
                verified=False,
            )

        try:
            send_verification_email_for_user(request, user)
        except Exception:
            logger.exception("Failed to send verification email")
            return BadRequestError("Erreur lors de l'envoi de l'email.").to_response()

        return 200, MessageSchema(
            success=True,
            message="Email d'activation envoyé.",
        )

    @http_post(
        "/password-reset",
        response={200: MessageSchema, 400: ErrorSchema},
        url_name="auth_password_reset",
    )
    def password_reset_request_view(self, request: HttpRequest, data: PasswordResetRequestSchema):
        """Request a password reset email."""
        try:
            user = User.objects.get(email__iexact=data.email, is_active=True)

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)

            frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
            reset_url = f"{frontend_url}/reset-password?uid={uid}&token={token}"

            subject = "Réinitialisation de votre mot de passe - Stud'Insight"
            message = f"""
Bonjour {user.first_name},

Vous avez demandé la réinitialisation de votre mot de passe.

Cliquez sur le lien suivant pour définir un nouveau mot de passe :
{reset_url}

Ce lien expire dans 24 heures.

Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.

L'équipe Stud'Insight
"""
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Failed to send password reset email")

        except User.DoesNotExist:
            pass

        return 200, MessageSchema(
            success=True,
            message="Si un compte existe avec cet email, un lien de réinitialisation a été envoyé.",
        )

    @http_post(
        "/password-reset/confirm",
        response={200: MessageSchema, 400: ErrorSchema},
        url_name="auth_password_reset_confirm",
    )
    def password_reset_confirm_view(self, request: HttpRequest, data: PasswordResetConfirmSchema):
        """Confirm password reset with token and set new password."""
        try:
            uid = force_str(urlsafe_base64_decode(data.uid))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return BadRequestError("Lien de réinitialisation invalide.").to_response()

        if not default_token_generator.check_token(user, data.token):
            return BadRequestError("Lien de réinitialisation expiré ou invalide.").to_response()

        try:
            validate_password(data.new_password, user=user)
        except DjangoValidationError as e:
            return ValidationError(
                message=" ".join(e.messages),
                details={"password_errors": e.messages},
            ).to_response()

        user.set_password(data.new_password)
        user.save()

        return 200, MessageSchema(
            success=True,
            message="Mot de passe modifié avec succès. Vous pouvez maintenant vous connecter.",
        )

    @http_post(
        "/password-change",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema},
        url_name="auth_password_change",
    )
    def password_change_view(self, request: HttpRequest, data: PasswordChangeSchema):
        """Change password for authenticated user."""
        if not request.user.is_authenticated:
            return NotAuthenticatedError().to_response()

        user = request.user

        if not user.check_password(data.current_password):
            return BadRequestError("Mot de passe actuel incorrect.").to_response()

        try:
            validate_password(data.new_password, user=user)
        except DjangoValidationError as e:
            return ValidationError(
                message=" ".join(e.messages),
                details={"password_errors": e.messages},
            ).to_response()

        user.set_password(data.new_password)
        user.save()

        login(request, user)

        return 200, MessageSchema(
            success=True,
            message="Mot de passe modifié avec succès.",
        )

    @http_post(
        "/activate/check/{token}",
        response={200: ActivateCheckSchema, 400: ErrorSchema, 401: ErrorSchema},
        url_name="auth_activate_check",
    )
    def check_activation_token(self, request: HttpRequest, token: str):
        """Check if an activation token is valid."""
        try:
            email_confirmation = EmailConfirmationHMAC.from_key(token)
            if email_confirmation is None:
                return 401, ErrorSchema(
                    code="INVALID_TOKEN",
                    message="Lien d'activation invalide ou expiré.",
                )

            if email_confirmation.email_address.verified:
                return 400, ErrorSchema(
                    code="ALREADY_ACTIVATED",
                    message="Ce compte est déjà activé.",
                )

            return 200, ActivateCheckSchema(
                valid=True,
                email=email_confirmation.email_address.email,
            )

        except Exception:
            logger.exception("Activation token check failed")
            return 401, ErrorSchema(
                code="INVALID_TOKEN",
                message="Lien d'activation invalide ou expiré.",
            )

    @http_post(
        "/activate/{token}",
        response={200: MessageSchema, 400: ErrorSchema, 401: ErrorSchema},
        url_name="auth_activate",
    )
    def activate_with_password(self, request: HttpRequest, token: str, data: ActivateWithPasswordSchema):
        """Activate account using token and set password."""
        try:
            email_confirmation = EmailConfirmationHMAC.from_key(token)
            if email_confirmation is None:
                return 401, ErrorSchema(
                    code="INVALID_TOKEN",
                    message="Lien d'activation invalide ou expiré.",
                )

            if email_confirmation.email_address.verified:
                return 400, ErrorSchema(
                    code="ALREADY_ACTIVATED",
                    message="Ce compte est déjà activé.",
                )

            user = email_confirmation.email_address.user

            try:
                validate_password(data.password, user=user)
            except DjangoValidationError as e:
                return ValidationError(
                    message=" ".join(e.messages),
                    details={"password_errors": e.messages},
                ).to_response()

            user.set_password(data.password)
            user.is_active = True
            user.save()

            email_confirmation.confirm(request)

            return 200, MessageSchema(
                success=True,
                message="Compte activé avec succès. Vous pouvez maintenant vous connecter.",
            )

        except Exception:
            logger.exception("Account activation failed")
            return 401, ErrorSchema(
                code="INVALID_TOKEN",
                message="Lien d'activation invalide ou expiré.",
            )
