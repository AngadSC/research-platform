"""In-app notifications first; the kinds in EMAIL_KINDS are also emailed through core.email
(SPEC phase 5, D14, D30, D71)."""

import re
import uuid
from itertools import islice

from django.apps import apps

from core.email import send_email
from core.models import Notification, NotificationKind, User
from core.permissions import Perm, can, forget

# D71: only notices someone must act on, or that matter for compliance, are emailed.
EMAIL_KINDS = frozenset(
    {
        NotificationKind.ETHICS_EXPIRY,
        NotificationKind.RETENTION_DUE,
        NotificationKind.PROJECT_EXPORTED,
        NotificationKind.INTEGRATION_ISSUE,
        NotificationKind.TRAINING_EXPIRY,  # D178
        NotificationKind.TRAINING_DIGEST,
    }
)


def notify(
    *,
    lab,
    recipient,
    kind,
    title,
    body="",
    target=None,
    dedupe_key,
    email_template="notification",
    email_context=None,
) -> bool:
    """Create the notification unless `(recipient, dedupe_key)` already exists. Returns True
    when a new one was created (and emails it with `email_template` if `kind` is in EMAIL_KINDS)."""
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
    if created and kind in EMAIL_KINDS:
        send_email(
            email_template,
            recipient.email,
            email_context or {"title": title[:200], "body": body},
        )
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
    if n.kind == NotificationKind.TASK_POST:  # D142: the reader must still see the project
        task = (
            apps.get_model("projects", "Task").objects.for_lab(lab).filter(pk=n.target_id).first()
        )
        return task is not None and can(user, Perm.VIEW_PROJECT, task)
    if n.kind == NotificationKind.MENTION:  # D260: a mention in a project or task needs the project
        model = {"projects.project": "Project", "projects.task": "Task"}.get(n.target_type.lower())
        if model is not None:
            target = (
                apps.get_model("projects", model)
                .objects.for_lab(lab)
                .filter(pk=n.target_id)
                .first()
            )
            return target is not None and can(user, Perm.VIEW_PROJECT, target)
    return can(user, Perm.VIEW_LAB, lab)


def visible_notifications(user, lab, qs, limit=100) -> list:
    """The first `limit` rows of `qs` the user may still see. Also used for unread counts."""
    forget(user)
    return list(islice((n for n in qs if _still_allowed(user, lab, n)), limit))


# D260: `@[Display Name](user:<uuid>)` is what the composer stores for a mention.
MENTION_TOKEN = re.compile(r"@\[([^\]\n]{1,100})\]\(user:([0-9a-fA-F-]{36})\)")
MAX_MENTIONS = 20


def notify_mentions(*, lab, author, body, where, perm, target, key) -> None:
    """Tell each person @mentioned in `body` that `author` did so in `where` ("the lab chat").
    Only people who may read the conversation (`can(person, perm, target)`) are told, never the
    author, and at most MAX_MENTIONS per message. `key` names the message for deduplication, so
    editing a post tells only the newly mentioned."""
    ids = []
    for _, raw in MENTION_TOKEN.findall(body):
        try:
            uid = uuid.UUID(raw)
        except ValueError:
            continue
        if uid != author.pk and uid not in ids:
            ids.append(uid)
    users = User.objects.filter(pk__in=ids[:MAX_MENTIONS], is_active=True)
    forget(author)
    name = author.display_name or author.email
    for user in users:
        forget(user)
        if not can(user, perm, target):
            continue
        notify(
            lab=lab,
            recipient=user,
            kind=NotificationKind.MENTION,
            title=f"{name} mentioned you in {where}"[:200],
            body=MENTION_TOKEN.sub(lambda m: f"@{m[1]}", body)[:200],
            target=target if target._meta.label != "labs.Lab" else None,
            dedupe_key=f"mention:{key}",
        )
