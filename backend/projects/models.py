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


class ProjectColor(models.TextChoices):
    """Order matters: the next colour picked is the first of the least used."""

    BLUE = "blue"
    ORANGE = "orange"
    GREEN = "green"
    PINK = "pink"
    TEAL = "teal"
    YELLOW = "yellow"
    VIOLET = "violet"
    RED = "red"
    LIME = "lime"
    BROWN = "brown"


class Project(LabScopedModel):
    name = models.CharField(max_length=200)
    color = models.CharField(max_length=16, choices=ProjectColor.choices, default=ProjectColor.BLUE)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=ProjectStatus.choices, default=ProjectStatus.PLANNING
    )
    start_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    retain_until = models.DateField(null=True, blank=True)
    retention_note = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    # D139: the latest change by a signed-in user to the project or anything in it.
    last_activity_at = models.DateTimeField(null=True, blank=True)
    last_activity_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Workflow stages someone marked as done or not needed (provenance.WORKFLOW_STAGES).
    workflow_marked_done = models.JSONField(default=list, blank=True)

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


class DeadlinePriority(models.TextChoices):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProjectDeadline(LabScopedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="deadlines")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    done = models.BooleanField(default=False)
    priority = models.CharField(
        max_length=8, choices=DeadlinePriority.choices, default=DeadlinePriority.MEDIUM
    )

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
    # D141: same-project links, enforced by core.lab_db triggers in migration 0003.
    documents = models.ManyToManyField("documents.Document", blank=True, related_name="+")
    attachments = models.ManyToManyField("documents.Attachment", blank=True, related_name="+")

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


class ChatMessage(LabScopedModel):
    """One message in a project's group chat. Removal is a real delete (see services)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chat_messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()

    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["project", "created_at"], name="chatmessage_recent_idx")]

    def __str__(self):
        return f"{self.author_id}: {self.body[:40]}"


class ChatReadState(LabScopedModel):
    """How far one person has read one project's chat (D207). No row means nothing read yet."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    last_read_at = models.DateTimeField()

    not_an_edit = True  # reading the chat is not activity (projects/activity.py)
    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="chatreadstate_unique")
        ]

    def __str__(self):
        return f"{self.user_id} read to {self.last_read_at}"


class TaskPost(LabScopedModel):
    """One update on a task's thread (D142). Plain text with simple markdown; the client
    renders it safely."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    edited_at = models.DateTimeField(null=True, blank=True)

    lab_parents = ("task",)
    permission_domain = "project"
    project_path = "task__project"

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["task", "created_at"], name="taskpost_thread_idx")]

    def __str__(self):
        return self.body[:50]
