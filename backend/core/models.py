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
    pronouns = models.CharField(max_length=40, blank=True)
    bio = models.TextField(blank=True)  # 500 characters, enforced by MeSerializer
    # Storage key of the profile picture in the lab_files storage (core/avatars.py), or "".
    avatar = models.CharField(max_length=200, blank=True, editable=False)
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


def default_saml_attributes():
    """eduPerson/LDAP attribute OIDs (what Shibboleth sends), then the friendly names. The first
    one present wins. `uid` falls back to the NameID when none is sent."""
    return {
        "uid": ["urn:oid:1.3.6.1.4.1.5923.1.1.1.6", "eduPersonPrincipalName"]
        + ["urn:oid:0.9.2342.19200300.100.1.1", "uid"],
        "email": ["urn:oid:0.9.2342.19200300.100.1.3", "mail", "email"],
        "first_name": ["urn:oid:2.5.4.42", "givenName"],
        "last_name": ["urn:oid:2.5.4.4", "sn"],
    }


class InstitutionSSO(models.Model):
    """SAML 2.0 sign-in for one institution (D152, D153). Edited by Django superusers only (admin
    in dev, `manage.py configure_sso` anywhere), never through the API, because it decides who
    the app trusts to vouch for an email address. `core.auth` turns enabled rows into allauth
    SAML apps; the SP URLs are /accounts/saml/<slug>/{metadata,acs}/."""

    institution = models.OneToOneField(Institution, on_delete=models.CASCADE, related_name="sso")
    slug = models.SlugField(max_length=50, unique=True, help_text="URL part, e.g. ualberta")
    enabled = models.BooleanField(default=False)
    email_domains = models.JSONField(
        default=list, help_text='Exact domains this IdP vouches for, e.g. ["ualberta.ca"]'
    )
    idp_entity_id = models.CharField("IdP entity ID", max_length=500, blank=True)
    idp_sso_url = models.URLField("IdP SSO URL (HTTP-Redirect)", max_length=500, blank=True)
    idp_x509cert = models.TextField("IdP signing certificate (PEM)", blank=True)
    idp_metadata_url = models.URLField(
        "IdP metadata URL",
        max_length=500,
        blank=True,
        help_text="Optional, https only. Each save fetches it into the IdP fields.",
    )
    attribute_mapping = models.JSONField(default=default_saml_attributes)
    require_sso = models.BooleanField(
        default=False, help_text="Refuse password sign-in and signup for these domains (D156)."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "institution SSO (SAML)"

    def __str__(self):
        return f"{self.institution.name} ({self.slug})"

    @property
    def provider_id(self) -> str:
        return f"saml:{self.slug}"

    def clean(self):
        from django.core.exceptions import ValidationError

        domains = self.email_domains
        if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
            raise ValidationError({"email_domains": 'A JSON list of domains, e.g. ["ualberta.ca"]'})
        self.email_domains = sorted({d.strip().lower().lstrip("@") for d in domains if d.strip()})
        for d in self.email_domains:
            if "." not in d or "@" in d or "/" in d or " " in d:
                raise ValidationError({"email_domains": f"Not a domain: {d}"})
        taken = InstitutionSSO.objects.exclude(pk=self.pk).filter(enabled=True)
        clash = {d for o in taken for d in o.email_domains} & set(self.email_domains)
        if self.enabled and clash:
            raise ValidationError({"email_domains": f"Already routed elsewhere: {sorted(clash)}"})
        if self.enabled and not self.email_domains:
            raise ValidationError({"email_domains": "Add at least one domain before enabling."})
        for url in (self.idp_sso_url, self.idp_metadata_url):
            if url and not url.startswith("https://"):
                raise ValidationError("IdP URLs must be https.")
        if self.idp_metadata_url:  # every save refetches, so re-saving is "refresh metadata"
            from core.auth import fetch_idp_metadata

            fetch_idp_metadata(self)
        if self.enabled and not (self.idp_entity_id and self.idp_sso_url and self.idp_x509cert):
            raise ValidationError("Enabling needs the IdP entity ID, SSO URL and certificate.")


class NotificationKind(models.TextChoices):
    ETHICS_EXPIRY = "ethics_expiry"
    RETENTION_DUE = "retention_due"
    INVITE_ACCEPTED = "invite_accepted"
    TASK_ASSIGNED = "task_assigned"
    # Run 2
    TASK_UNASSIGNED = "task_unassigned"
    PROJECT_EXPORTED = "project_exported"
    INTEGRATION_ISSUE = "integration_issue"
    # Run 4
    TASK_POST = "task_post"
    # Run 5 (training, D178)
    TRAINING_EXPIRY = "training_expiry"
    TRAINING_DIGEST = "training_digest"
    # D260: someone @mentioned you in a chat message or task update
    MENTION = "mention"
    # Walkthrough fixes: added to a project or role changed, project archived, document owner
    PROJECT_ROLE = "project_role"
    PROJECT_ARCHIVED = "project_archived"
    DOCUMENT_OWNER = "document_owner"
    DATASET_CONTROLLER = "dataset_controller"  # a dataset handed to you


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
