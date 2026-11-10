"""Provenance models (ARCHITECTURE section 1, D20). Every row belongs to one project; every
link stays inside it (D31: `lab_parents` in save(), the m2m_changed receiver, and services)."""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel

COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
# e.g. sha256:<hex> or md5:<hex>; drive-version:<n> for Drive files with no md5 (D76)
CHECKSUM_RE = re.compile(r"^(?:[a-z0-9-]+:[0-9a-fA-F]{8,128}|drive-version:[0-9]{1,20})$")

# URLField's default validator also accepts ftp; provenance links are web pages only, and
# javascript: must never be storable (it would run when a UI renders the link).
validate_web_url = URLValidator(schemes=["http", "https"])


def validate_commit(value):
    if value and not COMMIT_RE.match(value):
        raise ValidationError("Enter a commit hash (7 to 40 hex characters).")


def validate_checksum(value):
    if value and not CHECKSUM_RE.match(value):
        raise ValidationError(
            "Use the form algorithm:hex, for example sha256:ab12... or md5:ab12..."
        )


class ManuscriptStatus(models.TextChoices):
    DRAFTING = "drafting"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    PUBLISHED = "published"


class LineageKind(models.TextChoices):
    DATASET = "dataset"
    ANALYSIS = "analysis"
    RESULT = "result"
    MANUSCRIPT = "manuscript"
    DECISION = "decision"


class ProvenanceModel(LabScopedModel):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="%(class)s_set"
    )

    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        abstract = True


class DatasetRecord(ProvenanceModel):
    """A pointer to where a dataset lives. No data is stored. A new version is a new row."""

    name = models.CharField(max_length=200)
    location_text = models.TextField(blank=True)
    location_url = models.URLField(blank=True, validators=[validate_web_url])
    controlled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    access_notes = models.TextField(blank=True)  # free-text access controller
    version_label = models.CharField(max_length=100)
    checksum = models.CharField(max_length=140, blank=True, validators=[validate_checksum])
    previous_version = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="next_versions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project", "previous_version")

    class Meta(ProvenanceModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name", "version_label"], name="dataset_unique_version"
            )
        ]

    def __str__(self):
        return f"{self.name} {self.version_label}"


class Analysis(ProvenanceModel):
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    code_repo_url = models.URLField(blank=True, validators=[validate_web_url])
    code_commit = models.CharField(max_length=40, blank=True, validators=[validate_commit])
    code_attachment = models.ForeignKey(
        "documents.Attachment", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    datasets = models.ManyToManyField(DatasetRecord, blank=True, related_name="analyses")
    ran_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ran_at = models.DateTimeField()

    lab_parents = ("project", "code_attachment")

    class Meta(ProvenanceModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=(~Q(code_repo_url="") & ~Q(code_commit=""))
                | Q(code_attachment__isnull=False),
                name="analysis_has_code_reference",
            )
        ]

    def __str__(self):
        return self.title


class Result(ProvenanceModel):
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True)
    analysis = models.ForeignKey(Analysis, on_delete=models.PROTECT, related_name="results")
    attachments = models.ManyToManyField("documents.Attachment", blank=True, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project", "analysis")

    def __str__(self):
        return self.title


class Decision(ProvenanceModel):
    title = models.CharField(max_length=300)
    rationale = models.TextField(blank=True)
    decided_on = models.DateField()
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    supporting_documents = models.ManyToManyField(
        "documents.Document", blank=True, related_name="+"
    )
    supporting_attachments = models.ManyToManyField(
        "documents.Attachment", blank=True, related_name="+"
    )
    references = models.JSONField(default=list, blank=True)  # [{title, url, doi}]
    analyses = models.ManyToManyField(Analysis, blank=True, related_name="decisions")
    results = models.ManyToManyField(Result, blank=True, related_name="decisions")
    datasets = models.ManyToManyField(DatasetRecord, blank=True, related_name="decisions")

    lab_parents = ("project",)

    def __str__(self):
        return self.title


class ManuscriptLink(ProvenanceModel):
    title = models.CharField(max_length=300)
    url = models.URLField(validators=[validate_web_url])
    status = models.CharField(
        max_length=16, choices=ManuscriptStatus.choices, default=ManuscriptStatus.DRAFTING
    )
    results = models.ManyToManyField(Result, blank=True, related_name="manuscripts")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project",)

    def __str__(self):
        return self.title


# ---------------------------------------------------------------- Workflow records (Run 4)


class FundingStatus(models.TextChoices):
    APPLIED = "applied"
    AWARDED = "awarded"
    ACTIVE = "active"
    CLOSED = "closed"
    DECLINED = "declined"


class FundingRecord(ProvenanceModel):
    """A grant or award behind the project (D133). PIs only, every field and every route (D226):
    `visible_rows` makes `visible_to` empty for anyone else, so search, the calendar, the
    dashboard and the AI tools all follow it."""

    @classmethod
    def visible_rows(cls, qs, user, lab):
        from core.permissions import can_access_funding

        return qs if can_access_funding(user, lab) else qs.none()

    funder = models.CharField(max_length=200)
    program = models.CharField(max_length=300, blank=True)  # program or grant name
    award_number = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="CAD")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=FundingStatus.choices, default=FundingStatus.APPLIED
    )
    holder = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    notes = models.TextField(blank=True)
    attachment = models.ForeignKey(
        "documents.Attachment", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project", "attachment")

    class Meta(ProvenanceModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="funding_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.funder} {self.program}".strip()


class ReviewStatus(models.TextChoices):
    REQUESTED = "requested"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"


class ReviewItem(ProvenanceModel):
    """A project review or sign-off request (D138)."""

    title = models.CharField(max_length=300)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    status = models.CharField(
        max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.REQUESTED
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project",)

    def __str__(self):
        return self.title


class RecruitmentPlan(ProvenanceModel):
    """One per project: the enrolment target and free notes. Counts only, never people (D136)."""

    project = models.OneToOneField(
        "projects.Project", on_delete=models.CASCADE, related_name="recruitment_plan"
    )
    target_enrolment = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    lab_parents = ("project",)


class RecruitmentStatus(models.TextChoices):
    SCREENED = "screened"
    ENROLLED = "enrolled"
    WITHDRAWN = "withdrawn"
    COMPLETED = "completed"


class RecruitmentEntry(ProvenanceModel):
    """A dated increment to one count: "on this day, N more people were screened". The running
    totals are the sums per status. No names, ids or other personal data (D136)."""

    entry_date = models.DateField()
    status = models.CharField(max_length=16, choices=RecruitmentStatus.choices)
    count = models.PositiveIntegerField()
    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project",)

    class Meta(ProvenanceModel.Meta):
        indexes = [models.Index(fields=["project", "entry_date"], name="recruit_project_date_idx")]

    def __str__(self):
        return f"{self.entry_date} {self.status} {self.count}"


WORKFLOW_STAGES = (
    "funding",
    "ethics",
    "participants",
    "data",
    "analysis",
    "manuscript",
    "review",
)


class ExternalType(models.TextChoices):
    POSTER = "poster"
    PRESENTATION = "presentation"
    CONFERENCE = "conference"
    OTHER = "other"


class ExternalOutput(ProvenanceModel):
    """A poster, talk or conference from this project. The file is an ordinary project
    `Attachment`, so it is served only through the permission-checked download endpoint."""

    title = models.CharField(max_length=300)
    type = models.CharField(max_length=16, choices=ExternalType.choices)
    date = models.DateField()
    place = models.CharField(max_length=300, blank=True)
    url = models.URLField(blank=True, validators=[validate_web_url])
    attachment = models.ForeignKey(
        "documents.Attachment", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project", "attachment")

    def __str__(self):
        return self.title


# ---------------------------------------------------------------- Data management plan (Run 5)

DMP_SECTIONS = (
    "data_description",
    "collection",
    "documentation",
    "storage",
    "preservation",
    "sharing",
    "responsibilities",
    "ethics_legal",
)


class DmpStatus(models.TextChoices):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"


class DataManagementPlan(ProvenanceModel):
    """One per project (D180): the Tri-Agency RDM / DMP Assistant sections as free text, a
    status, the last review date, an optional external DMP link and one attachment."""

    project = models.OneToOneField(
        "projects.Project", on_delete=models.CASCADE, related_name="data_management_plan"
    )
    data_description = models.TextField(blank=True)
    collection = models.TextField(blank=True)
    documentation = models.TextField(blank=True)
    storage = models.TextField(blank=True)
    preservation = models.TextField(blank=True)
    sharing = models.TextField(blank=True)
    responsibilities = models.TextField(blank=True)
    ethics_legal = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=DmpStatus.choices, default=DmpStatus.DRAFT)
    last_reviewed = models.DateField(null=True, blank=True)
    external_url = models.CharField(max_length=500, blank=True, validators=[validate_web_url])
    attachment = models.ForeignKey(
        "documents.Attachment", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )

    lab_parents = ("project", "attachment")

    def __str__(self):
        return f"DMP {self.project_id}"


class DataManagementPlanRevision(LabScopedModel):
    """A snapshot after every save (D181): numbered per plan, never edited."""

    plan = models.ForeignKey(DataManagementPlan, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("plan",)
    permission_domain = "project"
    project_path = "plan__project"

    class Meta(LabScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["plan", "number"], name="dmp_rev_number")]
