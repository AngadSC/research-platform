import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.tenancy import LabScopedModel

INVITE_TTL = timedelta(days=7)


class LabRole(models.TextChoices):
    PI = "pi"
    LAB_ADMIN = "lab_admin"
    MEMBER = "member"
    VIEWER = "viewer"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Lab(models.Model):
    """The tenant. Not lab-scoped."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey("core.Institution", on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["institution"], name="lab_institution_idx")]

    def __str__(self):
        return self.name


class LabMembership(LabScopedModel):
    permission_domain = "lab"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, choices=LabRole.choices)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["lab", "user"], name="labmember_unique")]
        indexes = [models.Index(fields=["user"], name="labmember_user_idx")]

    def __str__(self):
        return f"{self.user_id} is {self.role}"


class Invite(LabScopedModel):
    permission_domain = "lab"

    @classmethod
    def visible_rows(cls, qs, user, lab):
        from core.permissions import Perm, can

        return qs if can(user, Perm.MANAGE_MEMBERS, lab) else qs.none()

    email = models.EmailField()  # stored lower-cased
    role = models.CharField(max_length=16, choices=LabRole.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["lab", "email"],
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="invite_one_open_per_email",
            )
        ]
        indexes = [models.Index(fields=["expires_at"], name="invite_expires_idx")]

    def __str__(self):
        return f"invite for {self.email}"

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        if self.expires_at is None:
            self.expires_at = timezone.now() + INVITE_TTL
        super().save(*args, **kwargs)

    @classmethod
    def issue(cls, *, lab, email, role, invited_by):
        """Create an invite; returns (invite, token). Only the hash is stored."""
        token = secrets.token_urlsafe(32)
        invite = cls.objects.create(
            lab=lab, email=email, role=role, invited_by=invited_by, token_hash=hash_token(token)
        )
        return invite, token

    @property
    def is_usable(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )
