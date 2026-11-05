"""Daily retention review (SPEC phase 5). It only creates notifications: it never deletes or
changes a project or document. Permissions are re-checked per recipient (D49)."""

from celery import shared_task
from django.utils import timezone

from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, can, forget, users_with
from labs.models import Lab
from projects import services


def _item(kind, obj, label, project):
    flag = " (deleted)" if (project.deleted_at is not None or obj.deleted_at is not None) else ""
    note = f" Note: {obj.retention_note}" if obj.retention_note else ""
    return {
        "target": obj,
        "dedupe_key": f"retention:{kind}:{obj.pk}:{obj.retain_until.isoformat()}",
        "title": f"Retention review: {kind} {label}{flag}",
        "body": f"The {kind} {label}{flag} passed its retain-until date {obj.retain_until}."
        f" Nothing has been deleted; review it.{note}",
    }


@shared_task
def retention_scan() -> int:
    """Notify each lab's retention reviewers (pi, lab_admin) once per overdue item and
    retain-until date. Returns the number of notifications created."""
    today = timezone.localdate()
    created = 0
    for lab in Lab.objects.all():
        projects, documents = services.retention_due(lab, today)
        items = [_item("project", p, p.name, p) for p in projects]
        items += [_item("document", d, d.title, d.project) for d in documents]
        if not items:
            continue
        for user in users_with(Perm.VIEW_RETENTION, lab):
            forget(user)
            if not can(user, Perm.VIEW_RETENTION, lab):
                continue
            for item in items:
                created += notify(
                    lab=lab,
                    recipient=user,
                    kind=NotificationKind.RETENTION_DUE,
                    email_template="retention_notice",
                    **item,
                )
    return created
