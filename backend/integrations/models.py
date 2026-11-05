"""Integration models (ARCHITECTURE section 9). Tokens are stored only as Fernet ciphertext in
`editable=False` fields, so forms, the admin and generic serializers never see them; plaintext
exists only in the return value of `access_token()` / `refresh_token()`."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel
from integrations import crypto
from provenance.models import validate_web_url


class AccountStatus(models.TextChoices):
    ACTIVE = "active"
    EXPIRED = "expired"  # the provider refused a refresh: the user must reconnect
    REVOKED = "revoked"  # disconnected or revoked by us; tokens wiped
    ERROR = "error"  # our side is misconfigured (bad client credentials, unknown provider)


class ConnectedAccount(LabScopedModel):
    """One user's account at one provider, usable in one lab only."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    provider = models.CharField(max_length=40)  # integrations.registry key
    external_account_id = models.CharField(max_length=255)
    external_email = models.EmailField(blank=True)
    granted_scopes = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE
    )
    access_token_ct = models.TextField(blank=True, editable=False)
    refresh_token_ct = models.TextField(blank=True, editable=False)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)  # last successful provider call

    permission_domain = "lab"
    project_path = None

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["lab", "user", "provider", "external_account_id"],
                name="connectedaccount_unique_external",
            ),
            models.UniqueConstraint(  # one usable account per user, lab and provider
                fields=["lab", "user", "provider"],
                condition=Q(status="active"),
                name="connectedaccount_one_active",
            ),
        ]
        indexes = [models.Index(fields=["lab", "user"], name="connectedaccount_user_idx")]

    @classmethod
    def visible_rows(cls, qs, user, lab):
        """D54: your own accounts; every member's with manage_lab_integrations."""
        from core.permissions import Perm, can

        return qs if can(user, Perm.MANAGE_LAB_INTEGRATIONS, lab) else qs.filter(user=user)

    def __str__(self):
        return f"{self.provider}: {self.external_email or self.external_account_id}"

    def access_token(self) -> str:
        return crypto.decrypt(self.access_token_ct)

    def refresh_token(self) -> str:
        return crypto.decrypt(self.refresh_token_ct)

    def set_tokens(self, *, access: str, refresh: str | None, expires_at) -> None:
        """`refresh=None` keeps the stored refresh token (providers that do not rotate it)."""
        self.access_token_ct = crypto.encrypt(access)
        if refresh is not None:
            self.refresh_token_ct = crypto.encrypt(refresh)
        self.token_expires_at = expires_at

    def clear_tokens(self) -> None:
        self.access_token_ct = self.refresh_token_ct = ""
        self.token_expires_at = None


TARGET_FIELDS = ("document", "dataset", "analysis", "result", "manuscript")


def _at_most_one(fields):
    q = Q(**{f"{f}__isnull": True for f in fields})  # none set
    for g in fields:
        q |= Q(**{f"{f}__isnull": f != g for f in fields})  # only g set
    return q


class ExternalLink(LabScopedModel):
    """A pointer to an item held by an outside service. Only metadata is stored, never content.
    Belongs to one project and optionally to one item in it (TARGET_FIELDS)."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="external_links"
    )
    document = models.ForeignKey(
        "documents.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    dataset = models.ForeignKey(
        "provenance.DatasetRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    analysis = models.ForeignKey(
        "provenance.Analysis", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    result = models.ForeignKey(
        "provenance.Result", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    manuscript = models.ForeignKey(
        "provenance.ManuscriptLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    provider = models.CharField(max_length=40)
    # The linker's account, used for freshness checks (drive.file grants are per user).
    # Null for link_only providers.
    connected_account = models.ForeignKey(
        ConnectedAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    external_id = models.CharField(max_length=255)
    url = models.URLField(max_length=2000, validators=[validate_web_url])
    title = models.CharField(max_length=500)
    mime_type = models.CharField(max_length=255, blank=True)
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # Baseline at link time, and the latest seen by a freshness check.
    linked_modified_at = models.DateTimeField(null=True, blank=True)
    linked_version = models.CharField(max_length=100, blank=True)
    linked_checksum = models.CharField(max_length=140, blank=True)
    remote_modified_at = models.DateTimeField(null=True, blank=True)
    remote_version = models.CharField(max_length=100, blank=True)
    remote_checksum = models.CharField(max_length=140, blank=True)  # "md5:<hex>" when given
    last_checked_at = models.DateTimeField(null=True, blank=True)
    unavailable_since = models.DateTimeField(null=True, blank=True)  # "no longer available"

    permission_domain = "project"
    project_path = "project"
    lab_parents = ("project", *TARGET_FIELDS, "connected_account")

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=_at_most_one(TARGET_FIELDS), name="externallink_at_most_one_target"
            )
        ]
        indexes = [
            models.Index(fields=["project"], name="externallink_project_idx"),
            models.Index(fields=["lab", "linked_by"], name="externallink_linker_idx"),
        ]

    def __str__(self):
        return self.title

    @property
    def status(self) -> str:
        if self.unavailable_since:
            return "unavailable"
        return "changed" if self.changed_since_linked else "ok"

    @property
    def changed_since_linked(self) -> bool:
        if self.remote_checksum and self.linked_checksum:
            if self.remote_checksum != self.linked_checksum:
                return True
        if self.remote_version and self.linked_version:
            return self.remote_version != self.linked_version
        return bool(
            self.remote_modified_at
            and self.linked_modified_at
            and self.remote_modified_at > self.linked_modified_at
        )
