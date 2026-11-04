from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel


class ApprovalStatus(models.TextChoices):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"


class EthicsApproval(LabScopedModel):
    """Lab-level (D27): every lab role reads it, pi/lab_admin/member edit it. Its files are
    `Attachment` rows with `ethics_approval` set (D38) and are gated by D48."""

    approval_number = models.CharField(max_length=100)
    board = models.CharField(max_length=200)
    title = models.CharField(max_length=300)
    projects = models.ManyToManyField(
        "projects.Project", blank=True, related_name="ethics_approvals"
    )
    approval_date = models.DateField()
    expiry_date = models.DateField()
    status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete (D52)
    # D56: when set, only pi, lab_admin and people who can see a linked project see it
    restricted = models.BooleanField(default=False)

    permission_domain = "lab"  # lab-level (D27); "ethics" would fail the domain consistency test
    project_path = None

    @classmethod
    def visible_rows(cls, qs, user, lab):
        from core.permissions import _IMPLICIT_LEADS, lab_role, visible_projects

        if lab_role(user, lab) in _IMPLICIT_LEADS:
            return qs
        seen = Q(projects__in=visible_projects(user, lab))
        return qs.filter(Q(restricted=False) | seen).distinct()

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["lab", "board", "approval_number"],
                condition=models.Q(deleted_at__isnull=True),
                name="ethics_unique_number",
            )
        ]
        indexes = [
            models.Index(fields=["lab", "status", "expiry_date"], name="ethics_lab_status_exp_idx")
        ]

    def __str__(self):
        return f"{self.board} {self.approval_number}"
