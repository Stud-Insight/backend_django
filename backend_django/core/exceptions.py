"""
Custom exceptions for the Stud'Insight API.
Centralized error handling following best practices.
"""

from ninja import Schema


class ErrorSchema(Schema):
    """Standard error response schema."""

    code: str
    message: str
    details: dict | None = None


class APIException(Exception):
    """Base exception for API errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "Une erreur interne est survenue."

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        details: dict | None = None,
    ):
        self.message = message or self.__class__.message
        self.code = code or self.__class__.code
        self.details = details
        super().__init__(self.message)

    def to_response(self) -> tuple[int, ErrorSchema]:
        """Convert exception to API response tuple."""
        return self.status_code, ErrorSchema(
            code=self.code,
            message=self.message,
            details=self.details,
        )


# Authentication Exceptions
class NotAuthenticatedError(APIException):
    """User is not authenticated."""

    status_code = 401
    code = "NOT_AUTHENTICATED"
    message = "Authentification requise."


class InvalidCredentialsError(APIException):
    """Invalid login credentials."""

    status_code = 401
    code = "INVALID_CREDENTIALS"
    message = "Identifiants incorrects."


class AccountDisabledError(APIException):
    """User account is disabled."""

    status_code = 401
    code = "ACCOUNT_DISABLED"
    message = "Ce compte est désactivé."


# Authorization Exceptions
class PermissionDeniedError(APIException):
    """User doesn't have required permissions."""

    status_code = 403
    code = "PERMISSION_DENIED"
    message = "Vous n'avez pas les permissions nécessaires."


class NotOwnerError(APIException):
    """User is not the owner of the resource."""

    status_code = 403
    code = "NOT_OWNER"
    message = "Vous n'êtes pas le propriétaire de cette ressource."


# Resource Exceptions
class NotFoundError(APIException):
    """Resource not found."""

    status_code = 404
    code = "NOT_FOUND"
    message = "Ressource introuvable."


class AlreadyExistsError(APIException):
    """Resource already exists."""

    status_code = 409
    code = "ALREADY_EXISTS"
    message = "Cette ressource existe déjà."


# Validation Exceptions
class ValidationError(APIException):
    """Invalid input data."""

    status_code = 400
    code = "VALIDATION_ERROR"
    message = "Données invalides."


class BadRequestError(APIException):
    """Bad request."""

    status_code = 400
    code = "BAD_REQUEST"
    message = "Requête invalide."


# File Exceptions
class FileTooLargeError(APIException):
    """File exceeds size limit."""

    status_code = 413
    code = "FILE_TOO_LARGE"
    message = "Le fichier dépasse la taille maximale autorisée."


class InvalidFileTypeError(APIException):
    """File type not allowed."""

    status_code = 415
    code = "INVALID_FILE_TYPE"
    message = "Ce type de fichier n'est pas autorisé."
