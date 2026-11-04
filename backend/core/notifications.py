"""In-app notifications first, email as a console-backend stub (SPEC phase 5, D14, D30)."""

from itertools import islice

from django.apps import apps
from django.core.mail import send_mail

from core.models import Notification, NotificationKind
from core.permissions import Perm, can, forget


def notify(*, lab, recipient, kind, title, body="", target=None, dedupe_key) -> bool:
    """Create the notification unless `(recipient, dedupe_key)` already exists. Returns True
    when a new one was created (and emails it)."""
    _, created = Notification.objects.for_lab(lab).get_or_create(
        recipient=recipient,
        dedupe_key=dedupe_key,
        defaults={
            "lab": lab,
            "kind": kind,
            "title": title[:200],
            "body": body,
            "target_type": target._meta.label if target is not None else "",
            "target_id": target.pk if target is not None else None,
        },
    )
    if created:
        send_mail(title, body, None, [recipient.email], fail_silently=True)
    return created


def _still_allowed(user, lab, n) -> bool:
    """D54: re-check at read time, since the role may have changed since the job ran."""
    if n.kind == NotificationKind.RETENTION_DUE:  # may point at a soft-deleted item
        return can(user, Perm.VIEW_RETENTION, lab)
    if n.kind == NotificationKind.ETHICS_EXPIRY:
        approval = (
            apps.get_model("ethics", "EthicsApproval")
            .objects.for_lab(lab)
            .filter(pk=n.target_id, deleted_at__isnull=True)
            .prefetch_related("projects")
            .first()
        )
        return (
            approval is not None
            and can(user, Perm.VIEW_ETHICS, approval)
            and (
                can(user, Perm.VIEW_RETENTION, lab)
                or any(can(user, Perm.EDIT_PROJECT, p) for p in approval.projects.all())
            )
        )
    return can(user, Perm.VIEW_LAB, lab)


def visible_notifications(user, lab, qs, limit=100) -> list:
    """The first `limit` rows of `qs` the user may still see. Also used for unread counts."""
    forget(user)
    return list(islice((n for n in qs if _still_allowed(user, lab, n)), limit))
