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


class AiPolicy(models.TextChoices):
    """D188: what AI assistants may do with this lab's data. Managed by pi and lab_admin."""

    OFF = "off"  # no AI assistant of any kind (MCP connections and the in-app assistant get 403)
    MCP = "mcp"  # people may connect their own AI app over MCP, but the in-app assistant is off
    FULL = "full"  # MCP and the in-app assistant (the default)


class Lab(models.Model):
    """The tenant. Not lab-scoped."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey("core.Institution", on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    # Lab details (Run 4, D146): free text shown in Admin > Lab details.
    department = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(max_length=300, blank=True)
    ai_policy = models.CharField(max_length=8, choices=AiPolicy.choices, default=AiPolicy.FULL)
    inventory_enabled = models.BooleanField(default=True)  # D227: off for a dry lab
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

    def __str__(self):  # shown as the audit log's target, so plain words, never an id
        return f"{self.user.display_name or 'A lab member'} ({self.get_role_display()})"


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


# ---------------------------------------------------------------- lab-wide chat and calendar


class LabChatMessage(LabScopedModel):
    """One message in the lab's group chat: project chat's rules (D206), for every lab member."""

    permission_domain = "lab"

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "created_at"], name="labchat_recent_idx")]

    def __str__(self):
        return f"{self.author_id}: {self.body[:40]}"


class LabChatReadState(LabScopedModel):
    """How far one person has read the lab chat (D207). No row means nothing read yet."""

    permission_domain = "lab"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    last_read_at = models.DateTimeField()

    class Meta(LabScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["lab", "user"], name="labchatread_unique")]

    def __str__(self):
        return f"{self.user_id} read to {self.last_read_at}"


class LabEvent(LabScopedModel):
    """A lab-wide calendar entry. `contribute_lab` writes; every lab member reads."""

    permission_domain = "lab"

    title = models.CharField(max_length=200)
    date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # blank means a single day
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "date"], name="labevent_lab_date_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("date")),
                name="labevent_end_after_start",
            )
        ]

    def __str__(self):
        return self.title


class Meeting(LabScopedModel):
    """A meeting on the calendar (D230). Only the people on it see it; its organiser always is."""

    permission_domain = "lab"

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(attendees=user)

    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    join_url = models.URLField(max_length=500, blank=True)  # Zoom or Google Meet, pasted in
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="+")

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "starts_at"], name="meeting_lab_start_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="meeting_end_after_start"
            )
        ]

    def __str__(self):
        return self.title


class CalendarFeedToken(LabScopedModel):
    """One person's secret .ics link for one lab (D231). Only the hash is stored."""

    permission_domain = "lab"

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(user=user)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    token_hash = models.CharField(max_length=64, unique=True)

    class Meta(LabScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["lab", "user"], name="calfeed_one_per_user")]

    def __str__(self):
        return f"calendar feed of {self.user_id}"

    @classmethod
    def issue(cls, *, lab, user):
        """Make a new secret, replacing any earlier one; returns (row, token)."""
        token = secrets.token_urlsafe(32)
        feed, _ = cls.objects.for_lab(lab).update_or_create(
            lab=lab, user=user, defaults={"token_hash": hash_token(token)}
        )
        return feed, token


# ---------------------------------------------------------------- Run 4: admin area (D146-D151)


class InventoryCategory(models.TextChoices):
    EQUIPMENT = "equipment"
    REAGENT = "reagent"
    CONSUMABLE = "consumable"
    SOFTWARE_LICENCE = "software_licence"
    OTHER = "other"


class InventoryStatus(models.TextChoices):
    ACTIVE = "active"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"
    LOST = "lost"


class InventoryItem(LabScopedModel):
    """A lab-owned thing (D147). Editing needs manage_inventory; every lab member reads."""

    permission_domain = "lab"

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=24, choices=InventoryCategory.choices)
    location = models.CharField(max_length=200, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit = models.CharField(max_length=32, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    serial_number = models.CharField(max_length=100, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)  # calibration or maintenance
    status = models.CharField(
        max_length=16, choices=InventoryStatus.choices, default=InventoryStatus.ACTIVE
    )
    notes = models.TextField(blank=True)

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "category"], name="inventory_lab_cat_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=0), name="inventory_quantity_gte0")
        ]

    def __str__(self):
        return self.name


class OrderStatus(models.TextChoices):
    REQUESTED = "requested"
    ORDERED = "ordered"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class InventoryOrder(LabScopedModel):
    """A purchase request. `manage_inventory` writes; every lab member reads. Moving to received
    adds `quantity` to the linked item once; a received order is then frozen (admin_services)."""

    permission_domain = "lab"
    lab_parents = ("item",)

    item = models.ForeignKey(
        InventoryItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    name = models.CharField(max_length=200)
    vendor = models.CharField(max_length=200, blank=True)
    catalog_number = models.CharField(max_length=100, blank=True)
    url = models.URLField(max_length=500, blank=True)  # https only; validated in the serializer
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit = models.CharField(max_length=32, blank=True)
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.REQUESTED
    )
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "created_at"], name="inventoryorder_lab_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="inventoryorder_quantity_gt0")
        ]

    def __str__(self):
        return self.name


class Protocol(LabScopedModel):
    """A project's written-down recipe: which reagents, and how much of each (D228)."""

    permission_domain = "project"
    project_path = "project"
    lab_parents = ("project",)

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["project", "name"], name="protocol_project_idx")]

    def __str__(self):
        return self.name


class ProtocolReagent(LabScopedModel):
    """One line of a protocol. `unit` must equal the item's unit: we never convert (D228)."""

    permission_domain = "project"
    project_path = "protocol__project"
    lab_parents = ("protocol", "item")

    protocol = models.ForeignKey(Protocol, on_delete=models.CASCADE, related_name="reagents")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=32, blank=True)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["protocol", "item"], name="protocol_reagent_once"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="protocol_reagent_amount_gt0"),
        ]

    def __str__(self):
        return f"{self.amount} {self.unit} of {self.item_id}"


class InventoryUsage(LabScopedModel):
    """A record that someone took stock for a project. Stock leaves the item exactly once: the
    row and the conditional quantity update share a transaction, and `request_id` makes a retried
    click a no-op (D228). `reversed_at` undoes a mistake and puts the amount back."""

    permission_domain = "project"
    project_path = "project"
    lab_parents = ("project", "protocol", "item")

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    protocol = models.ForeignKey(
        Protocol, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    protocol_name = models.CharField(max_length=200)  # survives the protocol being deleted
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=32, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    request_id = models.UUIDField()
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["project", "created_at"], name="invusage_project_idx")]
        constraints = [
            models.UniqueConstraint(fields=["lab", "request_id"], name="invusage_request_once"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="invusage_amount_gt0"),
        ]

    def __str__(self):
        return f"{self.amount} {self.unit} of {self.item_id}"


class OnboardingKind(models.TextChoices):
    NEW_MEMBER = "new_member"
    DEPARTING = "departing"


class OnboardingItem(LabScopedModel):
    """One line of the onboarding or departure checklist (D148)."""

    permission_domain = "lab"
    lab_parents = ("training_requirement",)

    kind = models.CharField(max_length=16, choices=OnboardingKind.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(max_length=500, blank=True)  # https only; validated in the serializer
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    # Run 5, D179: a current training record counts as done for this item
    training_requirement = models.ForeignKey(
        "training.TrainingRequirement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "kind", "order"], name="onboarding_lab_kind_idx")]

    def __str__(self):
        return self.title


class OnboardingCompletion(LabScopedModel):
    permission_domain = "lab"
    lab_parents = ("item",)

    item = models.ForeignKey(OnboardingItem, on_delete=models.CASCADE, related_name="completions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["item", "user"], name="onboarding_completion_unique")
        ]

    def __str__(self):
        return f"{self.user_id} completed {self.item_id}"


class ResourceCategory(models.TextChoices):
    ETHICS = "ethics"
    FUNDING = "funding"
    DATA_MANAGEMENT = "data_management"
    OTHER = "other"


class InstitutionResource(LabScopedModel):
    """A curated link to a university page (D126, D149). Lab-scoped, so one lab's edits never
    reach another lab that shares the institution."""

    permission_domain = "lab"

    category = models.CharField(max_length=24, choices=ResourceCategory.choices)
    title = models.CharField(max_length=200)
    url = models.URLField(max_length=500)  # https only; validated in the serializer
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["lab", "url"], name="institution_resource_url_unique")
        ]
        indexes = [models.Index(fields=["lab", "category", "order"], name="instres_lab_cat_idx")]

    def __str__(self):
        return self.title
