"""Document and attachment business logic (ARCHITECTURE sections 1, 4, 8). Write actions
record their audit event in the same transaction."""

import hashlib
import json
import re
import uuid

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
from documents.models import Attachment, Document, DocumentRevision

MAX_CONTENT_BYTES = 1024 * 1024
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


def _revise(doc, *, title, content, user, restored_from=None, retention=None):
    doc.title, doc.content, doc.updated_by = title, content, user
    for key, value in (retention or {}).items():
        setattr(doc, key, value)
    doc.version += 1
    doc.save()
    return DocumentRevision.objects.create(
        document=doc,
        version=doc.version,
        title=title,
        content=content,
        created_by=user,
        restored_from=restored_from,
    )


@transaction.atomic
def create_document(*, project, user, title, content) -> Document:
    validate_content(content)
    doc = Document.objects.create(
        project=project,
        title=title,
        content=content,
        version=1,
        created_by=user,
        updated_by=user,
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
    doc, *, title, content, base_version, user, request=None, **retention
) -> Document:
    """`retention` may carry `retain_until` and `retention_note` (D55: view_retention to change)."""
    validate_content(content)
    doc = _lock(doc)
    if base_version != doc.version:
        raise _conflict(doc)
    changes = retention_changes(doc, retention)
    guard_retention(user, doc.lab, changes)
    _revise(doc, title=title, content=content, user=user, retention=retention)
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


def upload_attachment(
    *, user, file, project=None, approval=None, training_record=None, request=None
) -> Attachment:
    """The caller has already checked `acknowledged_notice` (the serializer) and access to the
    owner: exactly one of `project`, an ethics `approval` or a `training_record` (D38, D175). The
    key is built here and never taken from the client (D26)."""
    if sum(o is not None for o in (project, approval, training_record)) != 1:
        raise ValueError("an attachment has exactly one owner")
    owner = project or approval or training_record
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
                storage_key=saved,
                original_filename="".join(c for c in file.name if c.isprintable())[:255] or "file",
                content_type=_safe_content_type(file.content_type),
                size_bytes=file.size,
                sha256=digest.hexdigest(),
                uploaded_by=user,
                notice_acknowledged_at=now,
            )
            record(
                AuditAction.ATTACHMENT_UPLOADED,
                actor=user,
                lab=owner.lab,
                target=attachment,
                request=request,
                metadata={
                    "ethics_approval": str(approval.pk) if approval else None,
                    "training_record": str(training_record.pk) if training_record else None,
                    "notice_acknowledged_at": now.isoformat(),
                    "size_bytes": attachment.size_bytes,
                    "sha256": attachment.sha256,
                },
            )
    except Exception:
        lab_files().delete(saved)  # nothing references these bytes yet
        raise
    return attachment


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
