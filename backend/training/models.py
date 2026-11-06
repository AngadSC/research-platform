"""Training requirements and per-member records (Run 5, D175-D179). Both are lab-level."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from core.tenancy import LabScopedModel


class TrainingCategory(models.TextChoices):
    ETHICS = "ethics"
    SAFETY = "safety"
    BIOSAFETY = "biosafety"
    CHEMICAL = "chemical"
    DATA_PRIVACY = "data_privacy"
    EQUIPMENT = "equipment"
    OTHER = "other"


class ComplianceStatus(models.TextChoices):
    DONE = "done"
    EXPIRING = "expiring"  # within 60 days (D177)
    EXPIRED = "expired"
    MISSING = "missing"


class AppliesTo(models.TextChoices):
    ALL = "all"
    ROLES = "roles"
    PROJECTS = "projects"


class TrainingRequirement(LabScopedModel):
    """One training the lab requires. `validity_months` null means it never expires."""

    permission_domain = "lab"

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=16, choices=TrainingCategory.choices)
    validity_months = models.PositiveSmallIntegerField(null=True, blank=True)
    applies_to = models.CharField(max_length=10, choices=AppliesTo.choices, default=AppliesTo.ALL)
    roles = models.JSONField(default=list, blank=True)  # lab roles, when applies_to == "roles"
    projects = models.ManyToManyField(
        "projects.Project", blank=True, related_name="training_requirements"
    )  # when applies_to == "projects": people on any of these projects
    url = models.URLField(max_length=500, blank=True)  # https only; validated in the serializer
    notes = models.TextField(blank=True)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["lab", "name"], name="training_requirement_name_uniq")
        ]

    def __str__(self):
        return self.name


class TrainingRecord(LabScopedModel):
    """One completion by one member. A renewal is a new row; the latest completion counts.
    Visible to its owner and to people with manage_training (D176)."""

    permission_domain = "lab"
    lab_parents = ("requirement",)

    requirement = models.ForeignKey(
        TrainingRequirement, on_delete=models.PROTECT, related_name="records"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    completed_on = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete (D24)

    @classmethod
    def visible_rows(cls, qs, user, lab):
        from core.permissions import Perm, can

        return qs if can(user, Perm.MANAGE_TRAINING, lab) else qs.filter(user=user)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_on__isnull=True) | Q(expires_on__gte=F("completed_on")),
                name="training_record_expiry_after_completion",
            )
        ]
        indexes = [
            models.Index(fields=["lab", "user"], name="training_rec_lab_user_idx"),
            models.Index(fields=["lab", "expires_on"], name="training_rec_lab_exp_idx"),
        ]

    def __str__(self):
        return f"{self.user_id} {self.requirement_id} {self.completed_on}"
