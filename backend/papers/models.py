"""The lab's paper library and notes. Lab-level: every member reads, `contribute_lab` adds."""

from django.conf import settings
from django.db import models

from core.tenancy import LabScopedModel


class Paper(LabScopedModel):
    """A paper the lab has read. The PDF is an `Attachment` owned by this row (the D175 pattern)."""

    permission_domain = "lab"

    title = models.CharField(max_length=500)
    # "Family, Given" strings. No comma: "Given Family". A trailing comma ("WHO,") is an
    # organisation or a single name, which citations never split. See citation.split_name.
    authors = models.JSONField(default=list, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    venue = models.CharField(max_length=300, blank=True)  # journal or conference
    doi = models.CharField(max_length=200, blank=True)  # bare, the D95 rule; checked on input
    url = models.URLField(max_length=500, blank=True)  # http(s) only; checked on input
    abstract = models.TextField(blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete; bytes are kept

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(deleted_at__isnull=True)

    @property
    def has_pdf(self) -> bool:
        return any(a.deleted_at is None for a in self.attachments.all())

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["lab", "deleted_at"], name="paper_lab_deleted_idx")]

    def __str__(self):
        return self.title


class PaperNote(LabScopedModel):
    """One member's note on a paper. Deleting is a real delete, and audited (as chat, D206)."""

    permission_domain = "lab"
    lab_parents = ("paper",)

    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    body = models.TextField()
    edited_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def visible_rows(cls, qs, user, lab):
        return qs.filter(paper__deleted_at__isnull=True)

    class Meta(LabScopedModel.Meta):
        indexes = [models.Index(fields=["paper", "created_at"], name="papernote_paper_created_idx")]

    def __str__(self):
        return f"Note on {self.paper_id}"
