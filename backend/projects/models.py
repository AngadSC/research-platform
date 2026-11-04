from django.conf import settings
from django.db import models

from core.tenancy import LabScopedModel


class ProjectStatus(models.TextChoices):
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProjectRole(models.TextChoices):
    LEAD = "lead"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


class Project(LabScopedModel):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=ProjectStatus.choices, default=ProjectStatus.PLANNING
    )
    start_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    retain_until = models.DateField(null=True, blank=True)
    retention_note = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    permission_domain = "project"
    project_path = ""  # itself

    class Meta(LabScopedModel.Meta):
        indexes = [
            models.Index(fields=["lab", "deleted_at"], name="project_lab_deleted_idx"),
            models.Index(fields=["lab", "retain_until"], name="project_lab_retain_idx"),
        ]

    def __str__(self):
        return self.name


class ProjectMembership(LabScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=16, choices=ProjectRole.choices)

    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="projectmember_unique")
        ]
        indexes = [models.Index(fields=["lab", "user"], name="projectmember_lab_user_idx")]

    def __str__(self):
        return f"{self.user_id} is {self.role}"
