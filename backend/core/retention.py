"""D55: changing `retain_until` or `retention_note` needs view_retention (pi, lab_admin) and is
audited. Leaving a field at its current value is not a change."""

from rest_framework.exceptions import PermissionDenied

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can

FIELDS = ("retain_until", "retention_note")


def _text(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def retention_changes(obj, data) -> dict:
    """{field: [old, new]} for submitted retention fields that differ from `obj`."""
    return {
        f: [_text(getattr(obj, f)), _text(data[f])]
        for f in FIELDS
        if f in data and data[f] != getattr(obj, f)
    }


def guard_retention(user, lab, changes) -> None:
    if changes and not can(user, Perm.VIEW_RETENTION, lab):
        raise PermissionDenied("Only a PI or lab admin can change retention settings.")


def audit_retention(user, lab, obj, changes, request=None) -> None:
    if changes:
        record(
            AuditAction.RETENTION_CHANGED,
            actor=user,
            lab=lab,
            target=obj,
            request=request,
            metadata={"changes": changes},
        )
