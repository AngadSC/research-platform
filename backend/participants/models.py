"""Participant registry (Part A of the participant-tracking brief). Coded IDs only: there is no
field for a name, email, phone, address or birthdate, and `identifiers.py` guards free text.
Links are titles, URLs and dates; file contents are never stored. Rows are never hard-deleted
here: participants are archived, and a project's retention date covers them (D52)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel


class EnrolmentStatus(models.TextChoices):
    SCREENED = "screened"
    ENROLLED = "enrolled"
    ACTIVE = "active"
    COMPLETED = "completed"
    WITHDRAWN = "withdrawn"
    INELIGIBLE = "ineligible"


class CellStatus(models.TextChoices):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    EXCLUDED = "excluded"


# Statuses that need an explanation, and the kind of reason that explains each.
REASON_KIND = {
    CellStatus.MISSING: "missing",
    CellStatus.NOT_APPLICABLE: "not_applicable",
    CellStatus.EXCLUDED: "excluded",
}


class Category(models.TextChoices):
    SESSION = "session"
    TRANSCRIPT = "transcript"
    TRANSLATION = "translation"
    SCORING = "scoring"
    QUESTIONNAIRE = "questionnaire"
    CONSENT = "consent"
    OTHER = "other"


class Provider(models.TextChoices):
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"
    DROPBOX = "dropbox"
    BOX = "box"
    GITHUB = "github"
    OTHER = "other"


class LinkState(models.TextChoices):
    OK = "ok"
    MOVED = "moved"
    NO_ACCESS = "no_access"
    NOT_FOUND = "not_found"
    UNCHECKED = "unchecked"


class FileRole(models.TextChoices):
    RAW = "raw"
    TRANSCRIPT = "transcript"
    TRANSLATION = "translation"
    SCORING = "scoring"
    OTHER = "other"


class ReasonKind(models.TextChoices):
    MISSING = "missing"
    EXCLUDED = "excluded"
    NOT_APPLICABLE = "not_applicable"


class StatusReason(LabScopedModel):
    """The lab's controlled list of why a cell is not complete."""

    label = models.CharField(max_length=100)
    kind = models.CharField(max_length=16, choices=ReasonKind.choices)
    active = models.BooleanField(default=True)

    permission_domain = "lab"
    project_path = None

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["lab", "kind", "label"], name="reason_unique_label")
        ]

    def __str__(self):
        return self.label


class ParticipantModel(LabScopedModel):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="%(class)s_set"
    )

    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        abstract = True


class Participant(ParticipantModel):
    code = models.CharField(max_length=40)
    group = models.CharField(max_length=100, blank=True)  # e.g. a study arm or cohort
    cohort = models.CharField(max_length=100, blank=True)
    enrolment_status = models.CharField(
        max_length=16, choices=EnrolmentStatus.choices, default=EnrolmentStatus.ENROLLED
    )
    enrolled_on = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=2000)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    lab_parents = ("project",)

    class Meta(ParticipantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["project", "code"], name="participant_unique_code")
        ]
        indexes = [models.Index(fields=["project", "group"], name="participant_group_idx")]

    def __str__(self):
        return self.code


class Component(ParticipantModel):
    """A column: one piece of data each participant should have."""

    name = models.CharField(max_length=100)
    key = models.SlugField(max_length=60)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    required = models.BooleanField(default=True)
    # Empty means every participant; otherwise only these groups.
    applies_to_groups = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    expected_per_participant = models.PositiveSmallIntegerField(default=1)
    template_origin = models.CharField(max_length=60, blank=True)
    sensitive = models.BooleanField(default=False)  # left out of exports
    archived_at = models.DateTimeField(null=True, blank=True)

    lab_parents = ("project",)

    class Meta(ParticipantModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["project", "key"], name="component_unique_key")
        ]
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ParticipantComponent(ParticipantModel):
    """A cell: one participant and one component."""

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="cells")
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="cells")
    status = models.CharField(
        max_length=16, choices=CellStatus.choices, default=CellStatus.NOT_STARTED
    )
    reason = models.ForeignKey(
        StatusReason, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    due_date = models.DateField(null=True, blank=True)
    collected_on = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True, max_length=1000)
    # When it was last confirmed complete. A linked document edited after this is flagged.
    verified_at = models.DateTimeField(null=True, blank=True)
    # An exclusion can point at the Decision that explains it, so the rationale is permanent.
    decision = models.ForeignKey(
        "provenance.Decision", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    lab_parents = ("project", "participant", "component", "reason", "decision")

    class Meta(ParticipantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["participant", "component"], name="cell_unique_participant_component"
            ),
            models.CheckConstraint(
                condition=Q(reason__isnull=True)
                | Q(status__in=["missing", "not_applicable", "excluded"]),
                name="cell_reason_only_when_explaining",
            ),
        ]
        indexes = [models.Index(fields=["project", "status"], name="cell_status_idx")]

    def __str__(self):
        return f"{self.participant_id}/{self.component_id}"


class ComponentFile(ParticipantModel):
    """A link in a cell. Title, address and dates only; the file's contents are never copied."""

    cell = models.ForeignKey(ParticipantComponent, on_delete=models.CASCADE, related_name="files")
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.OTHER)
    url = models.URLField(max_length=1000)
    external_id = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=300, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    last_modified_remote = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    link_state = models.CharField(
        max_length=16, choices=LinkState.choices, default=LinkState.UNCHECKED
    )
    role = models.CharField(max_length=16, choices=FileRole.choices, default=FileRole.OTHER)
    version_label = models.CharField(max_length=100, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    lab_parents = ("project", "cell")

    def __str__(self):
        return self.title or self.url


class ParticipantEvent(ParticipantModel):
    """History for one participant or cell. Values are statuses, dates and ids, never free text."""

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="events")
    component = models.ForeignKey(
        Component, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=40)
    from_value = models.CharField(max_length=100, blank=True)
    to_value = models.CharField(max_length=100, blank=True)

    lab_parents = ("project", "participant", "component")

    class Meta(ParticipantModel.Meta):
        ordering = ["-created_at", "id"]


class ImportRun(ParticipantModel):
    """One import from a sheet or CSV. Keeps what it created and what it changed, so the last
    one can be undone. Holds counts and ids only, never the sheet's text."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    source = models.CharField(max_length=16, default="csv")
    summary = models.JSONField(default=dict)
    undo = models.JSONField(default=dict)
    undone_at = models.DateTimeField(null=True, blank=True)

    lab_parents = ("project",)

    class Meta(ParticipantModel.Meta):
        ordering = ["-created_at"]


class CellTask(ParticipantModel):
    """A task made from a gap in a cell. Completing it never changes the cell by itself: the
    person is asked, and the same the other way round."""

    cell = models.ForeignKey(
        ParticipantComponent, on_delete=models.CASCADE, related_name="task_links"
    )
    task = models.ForeignKey("projects.Task", on_delete=models.CASCADE, related_name="+")

    lab_parents = ("project", "cell", "task")

    class Meta(ParticipantModel.Meta):
        constraints = [models.UniqueConstraint(fields=["cell", "task"], name="celltask_unique")]


class InclusionRule(ParticipantModel):
    """Who counts for one paper or analysis. Editing bumps the version and keeps the old one."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=1000)
    version = models.PositiveIntegerField(default=1)
    # {"requires": [component keys that must be Complete], "groups": [names, empty = all],
    #  "exclude_enrolment": ["withdrawn", "ineligible"]}
    spec = models.JSONField(default=dict)
    history = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    lab_parents = ("project",)

    class Meta(ParticipantModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name"],
                condition=Q(archived_at__isnull=True),
                name="rule_unique_name",
            )
        ]


class AnalysisSet(ParticipantModel):
    """A locked list of participants, with the version of every linked file they rested on."""

    name = models.CharField(max_length=120)
    rule = models.ForeignKey(
        InclusionRule, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    rule_version = models.PositiveIntegerField(default=1)
    participant_ids = models.JSONField(default=list)
    snapshot = models.JSONField(default=dict)  # participant -> column key -> status and files
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    locked_at = models.DateTimeField(auto_now_add=True)
    analysis = models.ForeignKey(
        "provenance.Analysis", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    supersedes = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    lab_parents = ("project", "rule", "analysis", "supersedes")

    class Meta(ParticipantModel.Meta):
        ordering = ["-locked_at"]
