from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel

# Content is capped in documents.services; the file limit lives in settings.ATTACHMENT_MAX_BYTES.


class Folder(LabScopedModel):
    """One tree per project, shared by documents and files. `parent` is set once at creation and
    never changes, so cycles cannot happen. Deleting moves the contents up (services)."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="folders"
    )
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children"
    )
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    lab_parents = ("project", "parent")
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["project", "parent"], name="folder_project_parent_idx")]

    def __str__(self):
        return self.name


class Document(LabScopedModel):
    # D233: no project means a lab-wide document (a lab manual, an SOP). Project code never sees
    # one: `visible_to` filters on project, and only `services.lab_documents` returns them.
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="documents",
    )
    folder = models.ForeignKey(
        Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    title = models.CharField(max_length=300)
    content = models.JSONField(default=list)  # BlockNote blocks
    # Set once at creation by documents.embed (allowlisted hosts). Blank for a normal document.
    embed_url = models.URLField(max_length=2000, blank=True, default="")
    embed_open_url = models.URLField(max_length=2000, blank=True, default="")  # "Open in ..."
    version = models.PositiveIntegerField(default=1)  # D11: bumped by save_document only
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    retain_until = models.DateField(null=True, blank=True)
    retention_note = models.TextField(blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    search_text = models.TextField(blank=True, editable=False)  # D93: derived from content

    lab_parents = ("project", "folder")
    permission_domain = "project"
    project_path = "project"

    @property
    def lab_wide(self) -> bool:
        return self.project_id is None

    def save(self, *args, **kwargs):
        from documents.text import extract_text

        self.search_text = extract_text(self.content)
        fields = kwargs.get("update_fields")
        if fields is not None and "content" in fields:
            kwargs["update_fields"] = {*fields, "search_text"}
        super().save(*args, **kwargs)

    class Meta(LabScopedModel.Meta):
        indexes = [
            models.Index(fields=["project", "deleted_at"], name="document_project_deleted_idx"),
            models.Index(fields=["lab", "retain_until"], name="document_lab_retain_idx"),
        ]
        constraints = [
            # With a null project the composite (folder, project) FK would not apply (MATCH SIMPLE).
            models.CheckConstraint(
                condition=Q(folder__isnull=True) | Q(project__isnull=False),
                name="document_folder_needs_project",
            ),
        ]

    def __str__(self):
        return self.title


class DocumentRevision(LabScopedModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=300)
    content = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    restored_from = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)

    lab_parents = ("document",)
    permission_domain = "project"
    project_path = "document__project"

    @property
    def lab_wide(self) -> bool:
        return self.document.lab_wide

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["document", "version"], name="revision_doc_version")
        ]

    def __str__(self):
        return f"{self.title} v{self.version}"


class Attachment(LabScopedModel):
    """D38, D175: exactly one owner, a project, an ethics approval, a training record or a paper
    (DB check). Project views see only project-owned files; ethics files are served through the
    approval (D48), training certificates through their record, paper PDFs through their paper."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, null=True, related_name="attachments"
    )
    ethics_approval = models.ForeignKey(
        "ethics.EthicsApproval", on_delete=models.PROTECT, null=True, related_name="attachments"
    )
    training_record = models.ForeignKey(  # D175: a member's certificate, private to them
        "training.TrainingRecord", on_delete=models.PROTECT, null=True, related_name="attachments"
    )
    paper = models.ForeignKey(  # a paper's PDF, lab-wide, served through its paper
        "papers.Paper", on_delete=models.PROTECT, null=True, related_name="attachments"
    )
    storage_key = models.CharField(max_length=512, unique=True)  # set server-side only
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    notice_acknowledged_at = models.DateTimeField()
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete; bytes are kept
    folder = models.ForeignKey(  # only on project-owned files
        Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments"
    )
    pi_only = models.BooleanField(default=False)  # D244: a grant letter; never cleared

    lab_parents = ("project", "ethics_approval", "training_record", "folder", "paper")
    permission_domain = "project"
    project_path = "project"

    @classmethod
    def visible_rows(cls, qs, user, lab):
        """D226, D244: a grant letter is PI-only. The flag is set when the file is linked to
        funding and never cleared, so removing that link does not reopen the file."""
        from core.permissions import can_access_funding

        return qs if can_access_funding(user, lab) else qs.filter(pi_only=False)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    project__isnull=False,
                    ethics_approval__isnull=True,
                    training_record__isnull=True,
                    paper__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    ethics_approval__isnull=False,
                    training_record__isnull=True,
                    paper__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    ethics_approval__isnull=True,
                    training_record__isnull=False,
                    paper__isnull=True,
                )
                | Q(
                    project__isnull=True,
                    ethics_approval__isnull=True,
                    training_record__isnull=True,
                    paper__isnull=False,
                ),
                name="attachment_has_one_owner",
            ),
            # With a null project the composite (folder, project) FK would not apply (MATCH SIMPLE).
            models.CheckConstraint(
                condition=Q(folder__isnull=True) | Q(project__isnull=False),
                name="attachment_folder_needs_project",
            ),
        ]

    def __str__(self):
        return self.original_filename
