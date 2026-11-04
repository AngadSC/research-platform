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


class ProjectDeadline(LabScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="deadlines")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    done = models.BooleanField(default=False)

    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["project", "due_date"], name="deadline_project_due_idx")]

    def __str__(self):
        return self.title


class TaskStatus(models.TextChoices):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(LabScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO)
    position = models.IntegerField(default=0)  # board order within a status column
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        indexes = [
            models.Index(fields=["project", "status", "position"], name="task_board_idx"),
            models.Index(fields=["lab", "assignee"], name="task_lab_assignee_idx"),
        ]

    def __str__(self):
        return self.title
