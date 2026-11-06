"""Training reminders (D178), modelled on the ethics job (D29): daily expiry reminders to the
member, and a weekly digest of expired and missing items for people who manage training."""

from celery import shared_task
from django.utils import timezone

from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, can, forget, users_with
from labs.models import Lab
from training import services

THRESHOLDS = (0, 7, 30, 60)  # days before expiry (0 = on or after the day); tightest crossed wins
DIGEST_LINES = 25


def threshold_for(days: int) -> int | None:
    return next((t for t in THRESHOLDS if days <= t), None)


@shared_task
def send_expiry_reminders() -> int:
    """One reminder per member per record, expiry date and tightest threshold crossed. Re-running
    creates nothing new; a renewal is a new record, so it re-arms. A requirement that never
    expires has no expiry date, so it is never reminded."""
    today = timezone.localdate()
    created = 0
    for lab in Lab.objects.all():
        current = services.latest_records(lab)  # an older, superseded record is not reminded
        recs = [
            r
            for r in current.values()
            if r.expires_on is not None and (r.expires_on - today).days <= max(THRESHOLDS)
        ]
        for rec in recs:
            days = (rec.expires_on - today).days
            threshold = threshold_for(days)
            user = rec.user
            forget(user)
            if not user.is_active or not can(user, Perm.VIEW_LAB, lab):
                continue
            name = rec.requirement.name
            if days < 0:
                title = f"{name} training has expired"
                body = f"Your {name} training expired on {rec.expires_on}. Please renew it."
            else:
                when = "today" if days == 0 else f"in {days} {'day' if days == 1 else 'days'}"
                title = f"{name} training expires {when}"
                body = (
                    f"Your {name} training expires on {rec.expires_on}. "
                    f"This is the {threshold}-day reminder."
                    if threshold
                    else f"Your {name} training expires on {rec.expires_on}. Please renew it."
                )
            created += notify(
                lab=lab,
                recipient=user,
                kind=NotificationKind.TRAINING_EXPIRY,
                title=title,
                body=body,
                target=rec,
                dedupe_key=f"training:{rec.pk}:{threshold}:{rec.expires_on.isoformat()}",
            )
    return created


def _digest_lines(data):
    names = {str(r.pk): r.name for r in data["requirements"]}
    lines = []
    for row in data["members"]:
        who = row["user"].display_name or row["user"].email
        for rid, cell in row["cells"].items():
            if cell and cell["status"] in (services.EXPIRED, services.MISSING):
                detail = (
                    f"expired {cell['expires_on']}"
                    if cell["status"] == services.EXPIRED
                    else "missing"
                )
                lines.append(f"{who}: {names[rid]} ({detail})")
    return lines


@shared_task
def send_weekly_digest() -> int:
    """Mondays. One notice per manager per ISO week listing expired and missing items; nothing
    is sent when the lab is clean."""
    today = timezone.localdate()
    year, week, _ = today.isocalendar()
    created = 0
    for lab in Lab.objects.all():
        data = services.compliance(lab, today=today)
        lines = _digest_lines(data)
        if not lines:
            continue
        s = data["summary"]
        title = f"Training: {s[services.EXPIRED]} expired, {s[services.MISSING]} missing"
        shown = lines[:DIGEST_LINES]
        more = len(lines) - len(shown)
        body = "\n".join(shown) + (f"\nand {more} more." if more > 0 else "")
        for user in users_with(Perm.MANAGE_TRAINING, lab):
            forget(user)
            if not can(user, Perm.MANAGE_TRAINING, lab):
                continue
            created += notify(
                lab=lab,
                recipient=user,
                kind=NotificationKind.TRAINING_DIGEST,
                title=title,
                body=body,
                dedupe_key=f"training-digest:{year}-W{week:02d}",
            )
    return created
