"""AI access (D160-D169): OAuth clients, grants and hashed tokens for the MCP server.

Not lab-scoped: a grant belongs to a user and names one or more labs. The labs only narrow what
the user may already see; every tool call re-checks membership and roles (D163). `FileLink`
(VISION S1) is the exception: it points at one project's files, so it is lab-scoped."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.tenancy import LabScopedModel


class ClientKind(models.TextChoices):
    DCR = "dcr"  # RFC 7591 dynamic registration: we issued a random client_id
    CIMD = "cimd"  # Client ID Metadata Document: client_id is the document's https URL


class OAuthClient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=255, unique=True)
    kind = models.CharField(max_length=8, choices=ClientKind.choices)
    name = models.CharField(max_length=100)  # self-reported by the client
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    refreshed_at = models.DateTimeField(default=timezone.now)  # CIMD: last fetch

    def __str__(self):
        return self.name


class GrantKind(models.TextChoices):
    OAUTH = "oauth"  # a connected AI app (consent screen)
    PAT = "pat"  # a personal access token


class Access(models.TextChoices):
    READ = "read"
    WRITE = "write"  # read and write


class AIGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=8, choices=GrantKind.choices)
    client = models.ForeignKey(
        OAuthClient, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    name = models.CharField(max_length=100)  # the token's label, or the client's name
    labs = models.ManyToManyField("labs.Lab", related_name="+")
    access = models.CharField(max_length=8, choices=Access.choices, default=Access.READ)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # PATs; OAuth grants live on
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # D195: why the system ended it (password_changed, password_reset, mfa_removed, deactivated);
    # blank when a person or a lab manager revoked it. Settings tells the owner.
    revoked_reason = models.CharField(max_length=24, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"], name="aigrant_user_idx")]

    def __str__(self):
        return self.name

    @property
    def active(self) -> bool:
        return self.revoked_at is None and (
            self.expires_at is None or self.expires_at > timezone.now()
        )


class TokenKind(models.TextChoices):
    CODE = "code"
    ACCESS = "access"
    REFRESH = "refresh"
    PAT = "pat"


class AIToken(models.Model):
    """Only the sha256 of a token is stored (D162). `data` holds a code's PKCE challenge,
    redirect URI and resource, or an access token's resource (audience)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.ForeignKey(AIGrant, on_delete=models.CASCADE, related_name="tokens")
    kind = models.CharField(max_length=8, choices=TokenKind.choices)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)  # codes and refresh tokens: single use
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.kind} token"


# ---------------------------------------------------------------- in-app assistant (D187-D192)


class Provider(models.TextChoices):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class AIProviderKey(models.Model):
    """A user's own API key for one provider (D187). Per user, not per lab. Encrypted with the
    same MultiFernet as integration tokens (D63) and never returned: only `last4` is shown. The
    plaintext exists only inside `api_key()` and `set_key()`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    provider = models.CharField(max_length=12, choices=Provider.choices)
    key_ciphertext = models.TextField(editable=False)
    last4 = models.CharField(max_length=4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    # D189: Anthropic only. On, a refused request is retried server-side on the model Anthropic
    # recommends; the person can turn that off in Settings.
    refusal_fallback = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "provider"], name="aiproviderkey_unique")
        ]

    def __str__(self):
        return f"{self.provider} key"  # never the key, not even its last characters

    def set_key(self, raw: str) -> None:
        from integrations import crypto

        self.key_ciphertext = crypto.encrypt(raw)
        self.last4 = raw[-4:]

    def api_key(self) -> str:
        from integrations import crypto

        return crypto.decrypt(self.key_ciphertext)


class LabAIKey(LabScopedModel):
    """VISION A5: one provider key a PI or lab admin sets for the whole lab, used by members who
    have no key of their own for that provider, until this month's spend reaches the cap. Stored
    exactly like a personal key: encrypted, never returned (only `last4`), never logged."""

    provider = models.CharField(max_length=12, choices=Provider.choices)
    key_ciphertext = models.TextField(editable=False)
    last4 = models.CharField(max_length=4, editable=False)
    monthly_cap_usd = models.DecimalField(max_digits=9, decimal_places=2)

    permission_domain = "lab"

    class Meta(LabScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["lab"], name="labaikey_one_per_lab")]

    def __str__(self):
        return f"{self.provider} lab key"  # never the key, not even its last characters

    set_key = AIProviderKey.set_key
    api_key = AIProviderKey.api_key


class LabAIUsage(LabScopedModel):
    """What one person's turns on the lab key cost in one month (VISION A5), at list prices
    (catalog.cost). `month` is the first day of the month."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    month = models.DateField()
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    input_tokens = models.BigIntegerField(default=0)  # cached reads and writes included
    output_tokens = models.BigIntegerField(default=0)

    permission_domain = "lab"

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["lab", "user", "month"], name="labaiusage_unique")
        ]

    def __str__(self):
        return f"AI usage {self.month:%Y-%m}"


class LabAIReservation(LabScopedModel):
    """What a model call on the lab key is expected to cost, held from before the call until its
    real cost is recorded, so that answers running at the same moment each see the others' spend
    against the monthly cap. One that is never released (a crash) stops counting after
    ASSISTANT_LOCK_TTL seconds."""

    cost_usd = models.DecimalField(max_digits=12, decimal_places=6)

    permission_domain = "lab"

    def __str__(self):
        return "AI cost reservation"


class Role(models.TextChoices):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(models.Model):
    """One chat, owned by one user in one lab, optionally about one project. Not lab-scoped data
    in the D18 sense (like AIGrant): every query filters on `user` and `lab`, and another user's
    conversation is a 404 for everyone, lab managers included (D190). The provider and model are
    fixed at creation, and so is the system prompt: a thinking block's signature covers it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    lab = models.ForeignKey("labs.Lab", on_delete=models.PROTECT, related_name="+")
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    provider = models.CharField(max_length=12, choices=Provider.choices)
    model = models.CharField(max_length=40)
    title = models.CharField(max_length=120, blank=True)
    system_prompt = models.TextField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user", "lab", "-updated_at"], name="conv_user_lab_idx")]

    def __str__(self):
        return self.title or "Conversation"


class Message(models.Model):
    """Append-only (D190): `content` holds the provider's own content blocks exactly as received
    (Claude: text, thinking, tool_use; OpenAI: output items), so history is replayed unchanged.
    `in_context` is False for a refused or truncated turn, which is shown but never replayed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    seq = models.PositiveIntegerField()
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.JSONField()
    model = models.CharField(max_length=40, blank=True)  # the model that answered (assistant)
    usage = models.JSONField(default=dict, blank=True)
    stop_reason = models.CharField(max_length=24, blank=True)
    in_context = models.BooleanField(default=True)
    meta = models.JSONField(default=dict, blank=True)  # refusal details, fallback, request id
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "seq"], name="message_seq_unique")
        ]

    def __str__(self):
        return f"{self.role} message {self.seq}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Messages are append-only.")
        super().save(*args, **kwargs)


# ---------------------------------------------------------------- file links (VISION S1)


class FileLinkKind(models.TextChoices):
    DOWNLOAD = "download"
    UPLOAD = "upload"


class FileLink(LabScopedModel):
    """A 15-minute link that lets a tool on the person's own computer (MATLAB's websave or
    webwrite) download one project file or upload one file into a project, without a session.
    Only the token's sha256 is stored. The link names the person who made it, and their access is
    read again on every use (assistant/file_links.py). An upload link works once."""

    kind = models.CharField(max_length=8, choices=FileLinkKind.choices)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    attachment = models.ForeignKey(  # download links
        "documents.Attachment", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    folder = models.ForeignKey(  # upload links: where the file goes
        "documents.Folder", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    analysis = models.ForeignKey(  # upload links: record the file as this analysis' output
        "provenance.Analysis", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    # what made the link: "mcp" (with the AI connection `grant`) or "in_app"; checked again on use
    via = models.CharField(max_length=12, blank=True)
    grant = models.ForeignKey(
        AIGrant, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )

    lab_parents = ("project", "attachment", "folder", "analysis")
    not_an_edit = True  # making a link does not change "last edited" (projects/activity.py)
    permission_domain = "project"
    project_path = "project"

    def __str__(self):
        return f"{self.kind} link"
