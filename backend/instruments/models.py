"""Instruments as places that collect data. An instrument is an equipment `InventoryItem`
(D147); what it exports lands in a project as an ordinary attachment, with its parsed summary
here. Drop links let a shared instrument PC or a core facility send files without signing in."""

from django.conf import settings
from django.db import models

from core.tenancy import LabScopedModel


class ParseStatus(models.TextChoices):
    PENDING = "pending"
    OK = "ok"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class UploadedVia(models.TextChoices):
    PAGE = "page"  # the signed-in drop page (or the QR sticker on a phone)
    LINK = "link"  # an instrument drop link, no sign-in


class InstrumentFile(LabScopedModel):
    """One exported file. The bytes are `attachment`, an ordinary project file, so downloads,
    "Contains participant data", PI-only and Drive copies all behave as for any upload."""

    permission_domain = "project"
    project_path = "project"
    lab_parents = ("instrument", "attachment", "project")

    instrument = models.ForeignKey(
        "labs.InventoryItem", on_delete=models.CASCADE, related_name="instrument_files"
    )
    attachment = models.OneToOneField(
        "documents.Attachment", on_delete=models.CASCADE, related_name="instrument_file"
    )
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    software = models.CharField(max_length=64, blank=True)  # the instrument's, when dropped
    status = models.CharField(
        max_length=12, choices=ParseStatus.choices, default=ParseStatus.PENDING
    )
    summary = models.JSONField(default=dict, blank=True)  # instrument_parsers.parse_file
    uploaded_via = models.CharField(max_length=8, choices=UploadedVia.choices)
    dropped_by = models.ForeignKey(  # null: sent through a drop link
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    @classmethod
    def visible_rows(cls, qs, user, lab):
        """A file later linked to funding becomes PI-only (D244); its name must not show here."""
        from core.permissions import can_access_funding

        qs = qs.filter(attachment__deleted_at__isnull=True)
        return qs if can_access_funding(user, lab) else qs.filter(attachment__pi_only=False)

    class Meta(LabScopedModel.Meta):
        indexes = [
            models.Index(fields=["lab", "instrument", "-created_at"], name="instfile_inst_idx")
        ]

    def __str__(self):
        return f"{self.instrument_id}: {self.attachment_id}"


class InstrumentDropLink(LabScopedModel):
    """A secret upload-only link bound to one instrument and one project (D231 pattern): only
    the token's sha256 is stored, so it is shown once. Every use re-reads the maker's access."""

    permission_domain = "project"
    project_path = "project"
    lab_parents = ("instrument", "project")

    instrument = models.ForeignKey(
        "labs.InventoryItem", on_delete=models.CASCADE, related_name="drop_links"
    )
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="+")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    label = models.CharField(max_length=100, blank=True)  # "Core facility PC"
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def visible_rows(cls, qs, user, lab):
        """Your own links; a PI or lab admin sees everyone's, and a project lead everyone's into
        their project, so a leaked one can be stopped."""
        from core.permissions import led_projects, sees_all_drop_links

        if sees_all_drop_links(user, lab):
            return qs
        return qs.filter(models.Q(created_by=user) | models.Q(project__in=led_projects(user, lab)))

    def __str__(self):
        return f"Drop link {self.label or self.pk}"
