import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower

from core.tenancy import LabScopedModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusers must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    # Personal UI settings; only these keys, validated by MeSerializer (D125).
    preferences = models.JSONField(default=dict, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]

    def __str__(self):
        return self.email


PLACEHOLDER_INSTITUTION = "PLACEHOLDER INSTITUTION (fake, replace me)"  # see migration 0003


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class NotificationKind(models.TextChoices):
    ETHICS_EXPIRY = "ethics_expiry"
    RETENTION_DUE = "retention_due"
    INVITE_ACCEPTED = "invite_accepted"
    TASK_ASSIGNED = "task_assigned"
    # Run 2
    TASK_UNASSIGNED = "task_unassigned"
    PROJECT_EXPORTED = "project_exported"
    INTEGRATION_ISSUE = "integration_issue"


class Notification(LabScopedModel):
    """In-app notification (D30). Lab-scoped, but only its recipient may read or change it."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    kind = models.CharField(max_length=24, choices=NotificationKind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=200)
    read_at = models.DateTimeField(null=True, blank=True)

    permission_domain = "lab"
    project_path = None

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(recipient=user)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["recipient", "dedupe_key"], name="notification_dedupe")
        ]
        indexes = [
            models.Index(
                fields=["lab", "recipient", "read_at", "created_at"], name="notification_inbox_idx"
            )
        ]

    def __str__(self):
        return self.title
