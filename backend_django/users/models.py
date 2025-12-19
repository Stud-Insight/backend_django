import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db.models import CharField
from django.db.models import EmailField
from django.db.models import ImageField
from django.db.models import UUIDField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


def user_avatar_path(instance: "User", filename: str) -> str:
    """Generate upload path for user avatar."""
    return f"avatars/user_{instance.pk}/{filename}"


class User(AbstractUser):
    """
    Custom user model for Stud'Insight.
    Uses email as the unique identifier instead of username.
    Uses UUID as primary key.
    """

    # UUID primary key
    id = UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Use first_name and last_name like the original backend
    first_name = CharField(_("first name"), max_length=150)
    last_name = CharField(_("last name"), max_length=150, blank=True)
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    # Avatar stored in MinIO/S3
    avatar = ImageField(
        _("avatar"),
        upload_to=user_avatar_path,
        blank=True,
        null=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        """Return first_name + last_name."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view."""
        return reverse("users:detail", kwargs={"pk": self.id})
