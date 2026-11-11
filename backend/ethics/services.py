"""Ethics approval business logic (ARCHITECTURE sections 1, 4, 5; D48). Writes record their
audit event in the same transaction."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can, can_edit_ethics, visible_projects
from documents import services as document_services
from ethics.models import ApprovalStatus, EthicsApproval

A = AuditAction


def _resolve_added(user, lab, ids):
    """Projects to link. An id the user cannot see fails like a missing id; a visible one
    needs edit_content (D48)."""
    ids = set(ids)
    found = list(visible_projects(user, lab).filter(pk__in=ids))
    if len(found) != len(ids):
        raise ValidationError({"projects": "One or more projects do not exist."})
    return found


def _require_edit_content(user, projects):
    for project in projects:
        if not can(user, Perm.EDIT_CONTENT, project):
            raise PermissionDenied(f"You cannot link or unlink project {project.name}.")


def _require_edit(user, approval):
    if not can_edit_ethics(user, approval):
        raise PermissionDenied(
            "You cannot change this approval: it is linked to projects you cannot see."
        )


def _save(approval):
    if approval.expiry_date < approval.approval_date:
        raise ValidationError({"expiry_date": "Expiry must not be before the approval date."})
    try:
        with transaction.atomic():
            approval.save()
    except IntegrityError as exc:  # unique (lab, board, approval_number), D33
        raise ValidationError(
            {"approval_number": "This board already has an approval with this number."}
        ) from exc


def _links_changed(approval, user, added, removed, request):
    record(
        A.ETHICS_APPROVAL_LINKS_CHANGED,
        actor=user,
        lab=approval.lab,
        target=approval,
        request=request,
        metadata={
            "added": sorted(str(p.pk) for p in added),
            "removed": sorted(str(p.pk) for p in removed),
        },
    )


@transaction.atomic
def create_approval(*, lab, user, data, request=None) -> EthicsApproval:
    data = dict(data)
    added = _resolve_added(user, lab, data.pop("projects", []))
    _require_edit_content(user, added)
    approval = EthicsApproval(lab=lab, created_by=user, **data)
    _save(approval)
    approval.projects.add(*added)
    record(A.ETHICS_APPROVAL_CREATED, actor=user, lab=lab, target=approval, request=request)
    if added:
        _links_changed(approval, user, added, [], request)
    return approval


@transaction.atomic
def update_approval(approval, *, user, data, request=None) -> EthicsApproval:
    _require_edit(user, approval)
    data = dict(data)
    lab = approval.lab
    added, removed = [], []
    if "projects" in data:
        requested = set(data.pop("projects"))
        current = {p.pk: p for p in approval.projects.all()}
        # Linked projects the user cannot see stay linked: they cannot unlink what they
        # cannot see (D48), so only the visible ones can be removed by omission.
        seen_current = {p.pk for p in visible_projects(user, lab).filter(pk__in=list(current))}
        # Every requested id must be visible (no probing for hidden links); only new ones link.
        added = [p for p in _resolve_added(user, lab, requested) if p.pk not in current]
        removed = [current[pk] for pk in seen_current - requested]
        _require_edit_content(user, [*added, *removed])
    for key, value in data.items():
        setattr(approval, key, value)
    if (
        "expiry_date" in data
        and "status" not in data
        and approval.status == ApprovalStatus.EXPIRED
        and approval.expiry_date >= timezone.localdate()
    ):
        approval.status = ApprovalStatus.ACTIVE  # a renewal re-activates (and re-arms reminders)
    _save(approval)
    approval.projects.add(*added)
    approval.projects.remove(*removed)
    record(
        A.ETHICS_APPROVAL_UPDATED,
        actor=user,
        lab=lab,
        target=approval,
        request=request,
        metadata={"fields": sorted(data)},
    )
    if added or removed:
        _links_changed(approval, user, added, removed, request)
    return approval


@transaction.atomic
def delete_approval(approval, *, user, request=None) -> None:
    """Soft delete of the approval and its attachments; stored bytes are kept (D24, D52)."""
    _require_edit(user, approval)
    now = timezone.now()
    record(
        A.ETHICS_APPROVAL_DELETED,
        actor=user,
        lab=approval.lab,
        target=approval,
        request=request,
        metadata={"attachments": approval.attachments.count()},
    )
    approval.attachments.filter(deleted_at__isnull=True).update(deleted_at=now)
    approval.deleted_at = now
    approval.save(update_fields=["deleted_at", "updated_at"])


def upload_file(*, approval, user, file=None, drive_file_id=None, request=None):
    return document_services.upload_attachment(
        approval=approval, user=user, file=file, drive_file_id=drive_file_id, request=request
    )
