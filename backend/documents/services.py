"""Document and attachment business logic (ARCHITECTURE sections 1, 4, 8). Write actions
record their audit event in the same transaction."""

import hashlib
import json
import re
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import storages
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from audit.models import AuditAction
from audit.services import record
from core.retention import audit_retention, guard_retention, retention_changes
from core.serializers import UserSerializer
from documents import embed
from documents.models import Attachment, Document, DocumentRevision, Folder

MAX_CONTENT_BYTES = 1024 * 1024
AUTOSAVE_WINDOW = timedelta(minutes=15)
CONTENT_TYPE_RE = re.compile(r"^[\w.+-]+/[\w.+-]+$")


class Conflict(APIException):
    """D11: the document changed since the client loaded it. The body tells the UI who and when."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "edit_conflict"


def validate_content(content) -> list:
    if not isinstance(content, list) or not all(isinstance(b, dict) for b in content):
        raise ValidationError("Content must be a JSON array of block objects.")
    if len(json.dumps(content).encode()) > MAX_CONTENT_BYTES:
        raise ValidationError("Content is too large (1 MB maximum).")
    return content


def lab_files():
    return storages["lab_files"]


# ---------------------------------------------------------------- documents


def _absorbs_autosave(latest, user) -> bool:
    """An autosave updates the latest revision in place only if it is this user's own, recent, and
    not a restore (those stay exactly as restored). The window is from the revision's creation, so
    long sessions still leave one revision every 15 minutes."""
    return (
        latest is not None
        and latest.created_by_id == user.pk
        and latest.restored_from_id is None
        and timezone.now() - latest.created_at < AUTOSAVE_WINDOW
    )


def _revise(doc, *, title, content, user, restored_from=None, retention=None, autosave=False):
    """Bump the version and write a revision. The caller holds the row lock (`_lock`), and
    `doc.version` is one past every existing revision, so moving the latest revision to it cannot
    collide with `revision_doc_version`."""
    doc.title, doc.content, doc.updated_by = title, content, user
    for key, value in (retention or {}).items():
        setattr(doc, key, value)
    doc.version += 1
    doc.save()
    if autosave:
        latest = doc.revisions.order_by("-version").first()
        if _absorbs_autosave(latest, user):
            latest.version, latest.title, latest.content = doc.version, title, content
            latest.save(update_fields=["version", "title", "content", "updated_at"])
            return latest
    return DocumentRevision.objects.create(
        document=doc,
        version=doc.version,
        title=title,
        content=content,
        created_by=user,
        restored_from=restored_from,
    )


def lab_documents(lab):
    """D233: the lab's lab-wide documents, the only path to them (`visible_to` needs a project)."""
    return Document.objects.for_lab(lab).filter(project__isnull=True)


@transaction.atomic
def create_document(
    *,
    user,
    title,
    content,
    project=None,
    lab=None,
    embed_url="",
    folder=None,
    contains_participant_data=False,
) -> Document:
    """A non-empty `embed_url` makes a document that frames an outside file (documents.embed).
    `lab` instead of `project` makes a lab-wide document (D233). A flagged folder flags it."""
    validate_content(content)
    _check_folder(folder, project.pk if project else None)
    frame, open_url = embed.normalise(embed_url) if embed_url else ("", "")
    doc = Document.objects.create(
        lab=lab or project.lab,
        project=project,
        title=title,
        content=content,
        embed_url=frame,
        embed_open_url=open_url,
        folder=folder,
        version=1,
        created_by=user,
        updated_by=user,
        contains_participant_data=_inherit(contains_participant_data, folder),
    )
    DocumentRevision.objects.create(
        document=doc, version=1, title=title, content=content, created_by=user
    )
    return doc


def _lock(doc) -> Document:
    try:
        return (
            Document.objects.for_lab(doc.lab_id)
            .select_for_update()
            .select_related("updated_by")
            .get(pk=doc.pk, deleted_at__isnull=True)
        )
    except Document.DoesNotExist as exc:
        raise Http404 from exc


def _conflict(doc):
    exc = Conflict()
    exc.detail = {  # set after init: DRF would turn the numbers and dates into strings
        "detail": "This document changed since you opened it.",
        "code": "edit_conflict",
        "current_version": doc.version,
        "updated_by": UserSerializer(doc.updated_by).data,
        "updated_at": doc.updated_at,
    }
    return exc


@transaction.atomic
def save_document(
    doc, *, title, content, base_version, user, request=None, autosave=False, **retention
) -> Document:
    """`retention` may carry `retain_until` and `retention_note` (D55: view_retention to change).
    `autosave` may fold this save into the latest revision instead of adding one (`_revise`)."""
    validate_content(content)
    doc = _lock(doc)
    if base_version != doc.version:
        raise _conflict(doc)
    if doc.lab_wide:  # D233: retention review works project by project
        retention = {}
    changes = retention_changes(doc, retention)
    guard_retention(user, doc.lab, changes)
    _revise(doc, title=title, content=content, user=user, retention=retention, autosave=autosave)
    audit_retention(user, doc.lab, doc, changes, request)
    return doc


@transaction.atomic
def restore_revision(revision, *, user, request=None) -> Document:
    """A new revision copied from `revision`; history is never rewritten."""
    doc = _lock(revision.document)
    new = _revise(
        doc, title=revision.title, content=revision.content, user=user, restored_from=revision
    )
    record(
        AuditAction.DOCUMENT_RESTORED,
        actor=user,
        lab=doc.lab,
        target=doc,
        request=request,
        metadata={"restored_version": revision.version, "new_version": new.version},
    )
    return doc


@transaction.atomic
def delete_document(doc, *, user, request=None) -> None:
    doc = _lock(doc)
    doc.deleted_at = timezone.now()
    doc.save(update_fields=["deleted_at", "updated_at"])
    record(AuditAction.DOCUMENT_DELETED, actor=user, lab=doc.lab, target=doc, request=request)


# ---------------------------------------------------------------- attachments


def _safe_content_type(declared) -> str:
    declared = (declared or "").split(";")[0].strip().lower()
    return (
        declared
        if CONTENT_TYPE_RE.match(declared) and len(declared) <= 100
        else ("application/octet-stream")
    )


def _link_drive_file(
    *, user, file_id, owners, folder, request, pi_only, flag, copied_from=None
) -> Attachment:
    """D257: attach a Google Drive file by reference. The id comes from the Google Picker, but
    the title, type and address are read from Drive with the person's own connection, so the
    browser cannot name a file they cannot open or a link that goes anywhere but Drive. Nothing
    is downloaded (D64); opening it goes to Drive, where Google decides who may see it."""
    from integrations.http import AccountUnavailable, IntegrationError
    from integrations.models import AccountStatus, ConnectedAccount
    from integrations.providers import google_drive

    project, approval, training_record, paper = owners
    owner = project or approval or training_record or paper
    provider = google_drive.PROVIDER
    if not provider.valid_external_id(file_id):
        raise ValidationError({"drive_file_id": "That is not a Google Drive file."})
    account = (
        ConnectedAccount.objects.for_lab(owner.lab_id)
        .filter(user=user, provider=provider.name, status=AccountStatus.ACTIVE)
        .first()
    )
    if account is None:
        raise ValidationError(
            {"drive_file_id": "Connect Google Drive in Settings > Integrations first."}
        )
    try:
        meta = google_drive.fetch_item(account, file_id)
    except (IntegrationError, AccountUnavailable):
        raise ValidationError(
            {"drive_file_id": "Google Drive did not answer. Try again."}
        ) from None
    if meta is None:
        raise ValidationError({"drive_file_id": "That Drive file is not available to you."})
    if not provider.link_url_ok(meta["url"]):
        raise ValidationError({"drive_file_id": "Google Drive returned an unexpected link."})
    _check_folder(folder, project.pk if project else None)
    attachment_id = uuid.uuid4()
    with transaction.atomic():
        attachment = Attachment.objects.create(
            id=attachment_id,
            project=project,
            ethics_approval=approval,
            training_record=training_record,
            paper=paper,
            folder=folder,
            storage_key=f"drive:{attachment_id}",  # never opened: there are no bytes
            original_filename="".join(c for c in meta["title"] if c.isprintable())[:255] or "file",
            content_type=_safe_content_type(meta.get("mime_type")),
            size_bytes=0,
            sha256="",
            uploaded_by=user,
            notice_acknowledged_at=None,
            pi_only=pi_only,
            contains_participant_data=flag,
            drive_file_id=file_id,
            external_url=meta["url"],
            copied_from=copied_from,
        )
        record(
            # D244: lab admins read the audit log, and funding.* is hidden from them
            AuditAction.FUNDING_UPDATED if pi_only else AuditAction.ATTACHMENT_UPLOADED,
            actor=user,
            lab=owner.lab,
            target=attachment,
            request=request,
            metadata={
                "source": "google_copy" if copied_from else "google_drive",
                "drive_file_id": file_id,
                **({"copied_from": str(copied_from.pk)} if copied_from else {}),
                "ethics_approval": str(approval.pk) if approval else None,
                "training_record": str(training_record.pk) if training_record else None,
                "paper": str(paper.pk) if paper else None,
            },
        )
    return attachment


def upload_attachment(
    *,
    user,
    file=None,
    drive_file_id=None,
    project=None,
    approval=None,
    training_record=None,
    paper=None,
    request=None,
    folder=None,
    pi_only=False,
    contains_participant_data=False,
    source="web",
) -> Attachment:
    """The caller has already checked `acknowledged_notice` (the serializer) and access to the
    owner: exactly one of `project`, an ethics `approval`, a `training_record` or a `paper` (D38,
    D175). The key is built here and never taken from the client (D26)."""
    if sum(o is not None for o in (project, approval, training_record, paper)) != 1:
        raise ValueError("an attachment has exactly one owner")
    owner = project or approval or training_record or paper
    flag = _inherit(contains_participant_data, folder)
    if drive_file_id:
        return _link_drive_file(
            user=user,
            file_id=drive_file_id,
            owners=(project, approval, training_record, paper),
            folder=folder,
            request=request,
            pi_only=pi_only,
            flag=flag,
        )
    _check_folder(folder, project.pk if project else None)
    if file.size > settings.ATTACHMENT_MAX_BYTES:
        raise ValidationError({"file": "File is too large (50 MB maximum)."})
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    attachment_id = uuid.uuid4()
    key = f"labs/{owner.lab_id}/attachments/{attachment_id}"
    saved = lab_files().save(key, file)
    now = timezone.now()
    try:
        with transaction.atomic():
            attachment = Attachment.objects.create(
                id=attachment_id,
                project=project,
                ethics_approval=approval,
                training_record=training_record,
                paper=paper,
                folder=folder,
                storage_key=saved,
                original_filename="".join(c for c in file.name if c.isprintable())[:255] or "file",
                content_type=_safe_content_type(file.content_type),
                size_bytes=file.size,
                sha256=digest.hexdigest(),
                uploaded_by=user,
                notice_acknowledged_at=now,
                pi_only=pi_only,
                contains_participant_data=flag,
                source=source,
            )
            record(
                # D244: lab admins read the audit log, and funding.* is hidden from them
                AuditAction.FUNDING_UPDATED if pi_only else AuditAction.ATTACHMENT_UPLOADED,
                actor=user,
                lab=owner.lab,
                target=attachment,
                request=request,
                metadata={
                    "ethics_approval": str(approval.pk) if approval else None,
                    "training_record": str(training_record.pk) if training_record else None,
                    "paper": str(paper.pk) if paper else None,
                    "notice_acknowledged_at": now.isoformat(),
                    "size_bytes": attachment.size_bytes,
                    "sha256": attachment.sha256,
                    "source": source,
                },
            )
    except Exception:
        lab_files().delete(saved)  # nothing references these bytes yet
        raise
    return attachment


def edit_in_google(attachment, *, user, request=None) -> Attachment:
    """VISION B3: copy a Word, Excel or PowerPoint upload into the person's own Google Drive as a
    Google Doc, Sheet or Slides file, and attach that copy next to the original, pointing back at
    it. The caller has checked edit rights on the project. Participant data stays here."""
    from assistant.privacy import is_flagged
    from integrations.http import IntegrationError
    from integrations.models import AccountStatus, ConnectedAccount
    from integrations.providers import google_drive

    stem, dot, ext = attachment.original_filename.rpartition(".")
    ext = f".{ext.lower()}" if dot else ""
    if (
        attachment.from_drive
        or attachment.project_id is None
        or ext not in google_drive.CONVERTIBLE
    ):
        raise ValidationError(
            {"file": "Only Word, Excel and PowerPoint files can be edited in Google."}
        )
    if is_flagged(attachment):
        raise ValidationError(
            {"file": "Files marked as identifying participants stay in labbenchos."}
        )
    limit = google_drive.CONVERT_MAX_BYTES
    too_big = f"This file is too large to copy to Google ({limit // 1048576} MB maximum)."
    if attachment.size_bytes > limit:
        raise ValidationError({"file": too_big})
    account = (
        ConnectedAccount.objects.for_lab(attachment.lab_id)
        .filter(user=user, provider=google_drive.PROVIDER.name, status=AccountStatus.ACTIVE)
        .first()
    )
    if account is None:
        raise ValidationError({"file": "Connect Google in Integrations first."})
    try:
        with lab_files().open(attachment.storage_key, "rb") as fh:
            data = fh.read(limit + 1)
    except FileNotFoundError:
        raise Http404 from None
    if len(data) > limit:
        raise ValidationError({"file": too_big})
    try:
        file_id = google_drive.create_converted(account, name=stem, extension=ext, data=data)
    except IntegrationError:  # AccountUnavailable too
        raise ValidationError({"file": "Google Drive did not answer. Try again."}) from None
    # The bytes have left: recorded now, so a failure to link the copy below still leaves a trace.
    record(
        # D244, as upload_attachment: a PI-only file's name must not reach lab admins
        AuditAction.FUNDING_UPDATED if attachment.pi_only else AuditAction.ATTACHMENT_DOWNLOADED,
        actor=user,
        lab=attachment.lab,
        target=attachment,
        request=request,
        metadata={"via": "google_copy", "drive_file_id": file_id},
    )
    return _link_drive_file(
        user=user,
        file_id=file_id,
        owners=(attachment.project, None, None, None),
        folder=attachment.folder,
        request=request,
        pi_only=attachment.pi_only,
        flag=False,
        copied_from=attachment,
    )


@transaction.atomic
def delete_attachment(attachment, *, user, request=None) -> None:
    """Soft delete. The stored bytes stay; nothing is purged automatically (D24)."""
    attachment.deleted_at = timezone.now()
    attachment.save(update_fields=["deleted_at", "updated_at"])
    record(
        AuditAction.ATTACHMENT_DELETED,
        actor=user,
        lab=attachment.lab,
        target=attachment,
        request=request,
    )


# ---------------------------------------------------------------- folders


def _inherit(flag, folder) -> bool:
    """VISION A3: something new in a flagged folder is flagged too."""
    return bool(flag or (folder is not None and folder.contains_participant_data))


def _check_folder(folder, project_id) -> None:
    if folder is not None and folder.project_id != project_id:
        raise ValidationError({"folder": "That folder is not in this project."})


def create_folder(*, project, user, name, parent=None) -> Folder:
    _check_folder(parent, project.pk)
    return Folder.objects.create(
        project=project,
        parent=parent,
        name=name,
        created_by=user,
        contains_participant_data=_inherit(False, parent),
    )


def rename_folder(folder, *, name) -> Folder:
    folder.name = name
    folder.save(update_fields=["name", "updated_at"])
    return folder


def move_to_folder(item, folder) -> None:
    """`item` is a Document or an Attachment; `folder` None is the project's top level."""
    _check_folder(folder, item.project_id)
    item.folder = folder
    fields = ["folder"]  # not updated_at: a move is not an edit
    if _inherit(False, folder):  # the flag sticks to the item if the folder goes away
        item.contains_participant_data = True
        fields.append("contains_participant_data")
    item.save(update_fields=fields)


@transaction.atomic
def delete_folder(folder) -> None:
    """Contents and subfolders move up to the parent, deleted items included. Nothing is lost.
    Rows are saved one by one because `update()` may not change a lab_parents field."""
    folder = Folder.objects.for_lab(folder.lab_id).select_for_update().get(pk=folder.pk)
    parent = folder.parent
    flagged = folder.contains_participant_data  # what moves up keeps the flag
    for model in (Document, Attachment):
        for item in model.objects.for_lab(folder.lab_id).filter(folder=folder):
            item.folder = parent
            item.contains_participant_data = item.contains_participant_data or flagged
            item.save(update_fields=["folder", "contains_participant_data"])
    for child in Folder.objects.for_lab(folder.lab_id).filter(parent=folder):
        child.parent = parent
        child.contains_participant_data = child.contains_participant_data or flagged
        child.save(update_fields=["parent", "contains_participant_data", "updated_at"])
    folder.delete()
