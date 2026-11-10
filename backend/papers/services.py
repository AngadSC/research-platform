"""Paper library business logic. Views and AI tools both come through here, after checking
`contribute_lab`. Deletes record their audit event in the same transaction."""

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can
from documents import services as document_services
from integrations import http, registry
from integrations.providers import zotero
from integrations.services import active_account_or_404
from papers.models import Paper, PaperNote
from papers.pdftext import MAX_BYTES, PdfTextError, read_pages


def with_counts(qs):
    """Papers ready for serializing: note count and PDF flag without a query per row."""
    return qs.annotate(note_count=Count("notes")).prefetch_related("attachments")


def _check_doi_free(lab, doi, exclude=None):
    """DOIs are case-insensitive. ponytail: a race can add a duplicate, which is only untidy."""
    if not doi:
        return
    clash = Paper.objects.for_lab(lab).filter(deleted_at__isnull=True, doi__iexact=doi)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise ValidationError({"doi": "This DOI is already in the lab's library."})


def _owner_or_manager(user, owner_id, lab) -> bool:
    return owner_id == user.pk or can(user, Perm.MANAGE_LAB, lab)


def create_paper(lab, *, user, data) -> Paper:
    _check_doi_free(lab, data.get("doi"))
    return Paper.objects.create(lab=lab, added_by=user, **data)


def update_paper(paper, *, data) -> Paper:
    """Any contributor may correct a shared record's metadata."""
    _check_doi_free(paper.lab, data.get("doi"), exclude=paper)
    for key, value in data.items():
        setattr(paper, key, value)
    paper.save()
    return paper


@transaction.atomic
def delete_paper(paper, *, user, request=None) -> None:
    """Soft delete, by whoever added it or a PI or lab admin. The notes go with it (`visible_rows`)
    and the PDF is soft-deleted; nothing is purged (D24)."""
    if not _owner_or_manager(user, paper.added_by_id, paper.lab):
        raise PermissionDenied
    now = timezone.now()
    paper.deleted_at = now
    paper.save(update_fields=["deleted_at", "updated_at"])
    paper.attachments.filter(deleted_at__isnull=True).update(deleted_at=now)
    record(AuditAction.PAPER_DELETED, actor=user, lab=paper.lab, target=paper, request=request)


def add_note(paper, *, author, body) -> PaperNote:
    return PaperNote.objects.create(paper=paper, lab_id=paper.lab_id, author=author, body=body)


def edit_note(note, *, user, body) -> PaperNote:
    if note.author_id != user.pk:
        raise PermissionDenied
    note.body, note.edited_at = body, timezone.now()
    note.save(update_fields=["body", "edited_at", "updated_at"])
    return note


@transaction.atomic
def delete_note(note, *, user, request=None) -> None:
    if not _owner_or_manager(user, note.author_id, note.lab):
        raise PermissionDenied
    record(AuditAction.PAPER_NOTE_DELETED, actor=user, lab=note.lab, target=note, request=request)
    note.delete()


# ---------------------------------------------------------------- the PDF (the D175 pattern)


def live_pdf(paper):
    return paper.attachments.filter(deleted_at__isnull=True).order_by("-created_at").first()


@transaction.atomic
def upload_pdf(paper, *, user, file, request=None):
    """One live PDF per paper: a new upload replaces the old one (kept, soft-deleted)."""
    magic = file.read(1024)
    file.seek(0)
    if file.content_type != "application/pdf" or b"%PDF-" not in magic:
        raise ValidationError({"file": "Upload a PDF file."})
    for old in paper.attachments.filter(deleted_at__isnull=True):
        document_services.delete_attachment(old, user=user, request=request)
    return document_services.upload_attachment(paper=paper, user=user, file=file, request=request)


def read_pdf_text(paper, *, first: int, last: int):
    """(the attachment, `pdftext.read_pages` output). Raises PdfTextError with a clear message."""
    attachment = live_pdf(paper)
    if attachment is None:
        raise PdfTextError("This paper has no PDF attached.")
    if attachment.size_bytes > MAX_BYTES:
        raise PdfTextError("This PDF is too large to read (50 MB maximum).")
    try:
        with document_services.lab_files().open(attachment.storage_key, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        raise PdfTextError("The stored PDF could not be found.") from None
    return attachment, read_pages(data, first, last)


@http.interactive
def zotero_items(lab, *, user, query="") -> list[dict]:
    """Up to 20 items from the person's own Zotero libraries (D242); nothing is kept."""
    provider = registry.get("zotero")
    account = active_account_or_404(lab, user, provider)
    return provider.search_items(account, query, "project")


@http.interactive
def import_from_zotero(lab, *, user, ids, request=None) -> dict:
    """Add the chosen items to the library. Metadata only, never the attachments. An item
    already here (same DOI or title), gone from Zotero, or with fields we refuse is skipped."""
    from papers.serializers import PaperInputSerializer  # late: the serializers import this

    account = active_account_or_404(lab, user, registry.get("zotero"))
    live = Paper.objects.for_lab(lab).filter(deleted_at__isnull=True)
    created = skipped = 0
    for external_id in dict.fromkeys(ids):
        fields = zotero.paper_fields(account, external_id)
        form = PaperInputSerializer(data=fields) if fields else None
        if form is None or not form.is_valid() or live.filter(title__iexact=fields["title"]):
            skipped += 1
            continue
        try:
            create_paper(lab, user=user, data=form.validated_data)
            created += 1
        except ValidationError:  # the DOI is already in the library
            skipped += 1
    record(
        AuditAction.PAPERS_IMPORTED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"provider": "zotero", "created": created, "skipped": skipped},
    )
    return {"created": created, "skipped": skipped}
