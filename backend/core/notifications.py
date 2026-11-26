"""In-app notifications first; the kinds in EMAIL_KINDS are also emailed through core.email
(SPEC phase 5, D14, D30, D71)."""

import datetime
import re
import uuid

from django.apps import apps
from django.utils import timezone

from core.email import send_email
from core.models import Notification, NotificationKind, User
from core.permissions import Perm, can, forget, prime_project_roles
from core.quiet import quiet_release

# D71: only notices someone must act on, or that matter for compliance, are emailed.
EMAIL_KINDS = frozenset(
    {
        NotificationKind.ETHICS_EXPIRY,
        NotificationKind.RETENTION_DUE,
        NotificationKind.PROJECT_EXPORTED,
        NotificationKind.INTEGRATION_ISSUE,
        NotificationKind.TRAINING_EXPIRY,  # D178
        NotificationKind.TRAINING_DIGEST,
        NotificationKind.LOW_STOCK,  # D331: someone has to reorder it
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
            eta=quiet_release(recipient, timezone.now()),  # held until quiet hours end
        )
    return created


def _still_allowed(user, lab, n) -> bool:
    """D54: re-check at read time, since the role may have changed since the job ran."""
    if n.kind == NotificationKind.RETENTION_DUE:  # may point at a soft-deleted item
        return can(user, Perm.VIEW_RETENTION, lab)
    if n.kind == NotificationKind.ETHICS_EXPIRY:
        approval = _target(n, _ETHICS, lab, user)
        return (
            approval is not None
            and can(user, Perm.VIEW_ETHICS, approval)
            and (
                can(user, Perm.VIEW_RETENTION, lab)
                or any(can(user, Perm.EDIT_PROJECT, p) for p in approval.projects.all())
            )
        )
    if n.kind == NotificationKind.MEETING_INVITE:  # D230: only while still on the meeting
        return _target(n, _MEETING, lab, user) is not None and can(user, Perm.VIEW_LAB, lab)
    if n.kind in _ABOUT_PROJECT_ITEMS:  # D142, D260: the reader must still see the project
        model = _PROJECT_TARGETS.get(n.target_type.lower())
        if model is not None:
            target = _target(n, model, lab, user)
            if getattr(target, "deleted_at", None) is not None:  # gone with its document
                return False
            return target is not None and can(user, Perm.VIEW_PROJECT, target)
        if n.kind == NotificationKind.TASK_POST:
            return False
    return can(user, Perm.VIEW_LAB, lab)


_PROJECT_TARGETS = {
    "projects.project": "projects.Project",
    "projects.task": "projects.Task",
    "documents.document": "documents.Document",
    "provenance.datasetrecord": "provenance.DatasetRecord",
}
_ABOUT_PROJECT_ITEMS = (
    NotificationKind.TASK_POST,
    NotificationKind.MENTION,
    NotificationKind.TASK_ASSIGNED,
    NotificationKind.PROJECT_ROLE,
    NotificationKind.PROJECT_ARCHIVED,
    NotificationKind.DOCUMENT_OWNER,
    NotificationKind.DATASET_CONTROLLER,
    NotificationKind.DOCUMENT_COMMENT,
)


_ETHICS = "ethics.EthicsApproval"
_MEETING = "labs.Meeting"


def _models_for(n) -> tuple:
    """The target models `_still_allowed` and `notification_url` may look up for `n`."""
    wanted = [_PROJECT_TARGETS.get(n.target_type.lower())]
    if n.kind == NotificationKind.ETHICS_EXPIRY:
        wanted.append(_ETHICS)
    if n.kind == NotificationKind.MEETING_INVITE:
        wanted.append(_MEETING)
    return tuple(m for m in wanted if m is not None)


def _load_targets(rows, lab, user) -> dict:
    """Fetch every target of `rows` with one query per model, lab-scoped, and hang the result on
    each row, so the D54 re-check and the URL read the same objects without a query per row."""
    ids = {}
    for n in rows:
        if n.target_id is not None:
            for m in _models_for(n):
                ids.setdefault(m, set()).add(n.target_id)
    found = {}
    for m, pks in ids.items():
        qs = apps.get_model(m).objects.for_lab(lab).filter(pk__in=pks)
        if m == _ETHICS:
            qs = qs.filter(deleted_at__isnull=True).prefetch_related("projects")
        elif m == _MEETING:  # only meetings the reader is still on
            qs = qs.filter(attendees=user).distinct()
        elif qs.model.project_path:
            qs = qs.select_related(qs.model.project_path)
        found.update(((m, obj.pk), obj) for obj in qs)
    for n in rows:
        n._targets = found
    return found


def _project_ids(targets) -> set:
    ids = set()
    for obj in targets:
        if obj._meta.label == "projects.Project":
            ids.add(obj.pk)
        elif obj._meta.label == _ETHICS:
            ids.update(p.pk for p in obj.projects.all())
        elif getattr(obj, "project_id", None):
            ids.add(obj.project_id)
    return ids


def _target(n, model, lab, user):
    """`n`'s target as `model`, or None when it is gone (or, for a meeting, the reader left it)."""
    if not hasattr(n, "_targets"):
        _load_targets([n], lab, user)
    return n._targets.get((model, n.target_id))


def visible_notifications(user, lab, qs, limit=100) -> list:
    """The first `limit` rows of `qs` the user may still see. Also used for unread counts.
    Targets and project roles are fetched a page of `limit` rows at a time, so the query count
    stays flat."""
    # ponytail: a restricted ethics approval still costs one query per row for a non-lead
    # (`_sees_restricted`); batch that in permissions.py if expiry notices ever pile up.
    forget(user)
    rows, out = list(qs), []
    for i in range(0, len(rows), limit):
        page = rows[i : i + limit]
        prime_project_roles(user, _project_ids(_load_targets(page, lab, user).values()))
        out += [n for n in page if _still_allowed(user, lab, n)]
        if len(out) >= limit:
            break
    return out[:limit]


# D260: `@[Display Name](user:<uuid>)` is what the composer stores for a mention.
MENTION_TOKEN = re.compile(r"@\[([^\]\n]{1,100})\]\(user:([0-9a-fA-F-]{36})\)")
# A mention of someone who is only in the linked Google Chat space: `@[Name](gchat:<google id>)`.
# It notifies no one here; it is shown as "@Name" and sent to Google as a real mention.
GCHAT_MENTION_TOKEN = re.compile(r"@\[([^\]\n]{1,100})\]\(gchat:[0-9]{1,40}\)")
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
            body=GCHAT_MENTION_TOKEN.sub(
                lambda m: f"@{m[1]}", MENTION_TOKEN.sub(lambda m: f"@{m[1]}", body)
            )[:200],
            target=target if target._meta.label != "labs.Lab" else None,
            dedupe_key=f"mention:{key}",
        )


# ---------------------------------------------------------------- shown at read time

_EXPIRES = re.compile(r"expires (?:today|in \d+ days?)$")
_MARKS = [  # the composer's simple markdown (D260), as plain words
    (re.compile(r"^\s*```.*$", re.M), ""),
    (MENTION_TOKEN, r"@\1"),
    (GCHAT_MENTION_TOKEN, r"@\1"),
    (re.compile(r"\[([^\]\n]+)\]\((?:https?://|mailto:)[^\s)]+\)"), r"\1"),
    (re.compile(r"\*\*([^*\n]+)\*\*"), r"\1"),
    (re.compile(r"~~([^~\n]+)~~"), r"\1"),
    (re.compile(r"\*([^*\n]+)\*"), r"\1"),
    (re.compile(r"(?<!\w)_([^_\n]+)_(?!\w)"), r"\1"),
    (re.compile(r"`([^`\n]+)`"), r"\1"),
    (re.compile(r"^\s*(?:[-*>]|\d+\.) ?", re.M), ""),
]


def live_title(n) -> str:
    """Expiry reminders were stored as "expires in 24 days" on the day they were made. The count
    is worked out again from the expiry date kept in the dedupe key, so old rows read right too."""
    if n.kind not in (NotificationKind.ETHICS_EXPIRY, NotificationKind.TRAINING_EXPIRY):
        return n.title
    try:
        expiry = datetime.date.fromisoformat(n.dedupe_key.rsplit(":", 1)[-1])
    except ValueError:
        return n.title
    days = (expiry - timezone.localdate()).days
    if days < 0:
        when = "expired yesterday" if days == -1 else f"expired {-days} days ago"
    else:
        when = "expires today" if days == 0 else f"expires in {days} day{'s' * (days != 1)}"
    return _EXPIRES.sub(when, n.title)


def live_body(n) -> str:
    """Bodies quoting a message (mentions, task updates) as plain text, without markdown marks."""
    if n.kind not in (
        NotificationKind.MENTION,
        NotificationKind.TASK_POST,
        NotificationKind.DOCUMENT_COMMENT,
    ):
        return n.body
    text = n.body
    for pattern, repl in _MARKS:
        text = pattern.sub(repl, text)
    return " ".join(text.split())


def notification_url(n, user) -> str:
    """The app page a notification is about. A task's project is looked up only for a task the
    reader can still see, so the address never names a project they cannot."""
    lab = f"/labs/{n.lab_id}"
    target = n.target_type.lower()
    if n.kind == NotificationKind.RETENTION_DUE:
        return f"{lab}/retention"
    if n.kind in (
        NotificationKind.TRAINING_EXPIRY,
        NotificationKind.TRAINING_DIGEST,
        NotificationKind.TRAINING_REMINDER,
    ):
        return f"{lab}/training"
    if n.kind == NotificationKind.INTEGRATION_ISSUE:
        return f"{lab}/settings/integrations"
    if n.kind == NotificationKind.LOW_STOCK:
        return f"{lab}/inventory"
    if n.kind == NotificationKind.MEETING_INVITE:
        return f"{lab}/calendar?view=mine-agenda"
    if n.kind == NotificationKind.MENTION and n.dedupe_key.startswith("mention:labchat:"):
        return f"{lab}/chat"
    if target == "ethics.ethicsapproval" and n.target_id:
        return f"{lab}/ethics/{n.target_id}"
    if target == "projects.project" and n.target_id:
        chat = "/chat" if n.kind == NotificationKind.MENTION else ""
        return f"{lab}/projects/{n.target_id}{chat}"
    if target == "projects.task" and n.target_id:
        task = _target(n, "projects.Task", n.lab_id, user)
        if task is not None and can(user, Perm.VIEW_PROJECT, task):
            return f"{lab}/projects/{task.project_id}/tasks?task={task.pk}"
    if target == "documents.document" and n.target_id:
        doc = _target(n, "documents.Document", n.lab_id, user)
        if doc is not None and doc.deleted_at is None and can(user, Perm.VIEW_PROJECT, doc):
            # a mention in a document is always in a comment: documents themselves don't notify
            comments = n.kind in (NotificationKind.MENTION, NotificationKind.DOCUMENT_COMMENT)
            where = f"/projects/{doc.project_id}" if doc.project_id else ""  # D233: lab-wide
            return f"{lab}{where}/documents/{doc.pk}" + ("?comments=1" if comments else "")
    if target == "provenance.datasetrecord" and n.target_id:
        ds = _target(n, "provenance.DatasetRecord", n.lab_id, user)
        if ds is not None and can(user, Perm.VIEW_PROJECT, ds):
            return f"{lab}/projects/{ds.project_id}/workflow/data/datasets/{ds.pk}"
    return lab
