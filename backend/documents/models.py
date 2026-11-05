from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel

# Content is capped in documents.services; the file limit lives in settings.ATTACHMENT_MAX_BYTES.


class Document(LabScopedModel):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="documents"
    )
    title = models.CharField(max_length=300)
    content = models.JSONField(default=list)  # BlockNote blocks
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

    lab_parents = ("project",)
    permission_domain = "project"
    project_path = "project"

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

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["document", "version"], name="revision_doc_version")
        ]

    def __str__(self):
        return f"{self.title} v{self.version}"


class Attachment(LabScopedModel):
    """D38: exactly one owner, a project or an ethics approval (DB check). Project views see
    only project-owned files; ethics files are served through the approval (D48)."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, null=True, related_name="attachments"
    )
    ethics_approval = models.ForeignKey(
        "ethics.EthicsApproval", on_delete=models.PROTECT, null=True, related_name="attachments"
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

    lab_parents = ("project", "ethics_approval")
    permission_domain = "project"
    project_path = "project"

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(project__isnull=False, ethics_approval__isnull=True)
                | Q(project__isnull=True, ethics_approval__isnull=False),
                name="attachment_has_one_owner",
            )
        ]

    def __str__(self):
        return self.original_filename
