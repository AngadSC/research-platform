"""Daily ethics jobs (ARCHITECTURE section 5, D29). Recipients come from `users_with` and are
re-checked with `can` before anything is sent (D49)."""

import datetime

from celery import shared_task
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record
from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, can, forget, users_with
from ethics.models import ApprovalStatus, EthicsApproval
from labs.models import Lab

THRESHOLDS = (7, 30, 60)  # days before expiry; only the tightest one crossed is sent


def threshold_for(days: int) -> int | None:
    return next((t for t in THRESHOLDS if days <= t), None)


@shared_task
def mark_expired() -> int:
    """Set `expired` on approvals whose expiry date has passed. Returns how many changed."""
    today = timezone.localdate()
    changed = 0
    for lab in Lab.objects.all():
        due = EthicsApproval.objects.for_lab(lab).filter(
            deleted_at__isnull=True,
            status__in=[ApprovalStatus.ACTIVE, ApprovalStatus.PENDING],
            expiry_date__lt=today,
        )
        for approval in due:
            approval.status = ApprovalStatus.EXPIRED
            approval.save(update_fields=["status", "updated_at"])
            record(
                AuditAction.ETHICS_APPROVAL_UPDATED,
                actor=None,
                lab=lab,
                target=approval,
                actor_label="job:ethics_expiry",
                metadata={"fields": ["status"], "status": ApprovalStatus.EXPIRED},
            )
            changed += 1
    return changed


def _recipients(lab, approval):
    """Leads of the linked projects plus the lab PIs, each re-checked with can()."""
    found = {}
    for user in users_with(Perm.VIEW_RETENTION, lab):  # pi and lab_admin
        forget(user)
        if can(user, Perm.VIEW_RETENTION, lab):
            found[user.pk] = user
    for project in approval.projects.all():
        for user in users_with(Perm.EDIT_PROJECT, project):  # leads (and implicit leads)
            forget(user)
            if can(user, Perm.EDIT_PROJECT, project):
                found[user.pk] = user
    for user in found.values():
        forget(user)
    return [u for u in found.values() if can(u, Perm.VIEW_ETHICS, approval)]


@shared_task
def send_expiry_reminders() -> int:
    """One reminder per recipient per approval, expiry date and tightest threshold crossed
    (60, 30 or 7 days). Re-running creates nothing new; a new expiry date re-arms it."""
    today = timezone.localdate()
    horizon = today + datetime.timedelta(days=max(THRESHOLDS))
    created = 0
    for lab in Lab.objects.all():
        approvals = (
            EthicsApproval.objects.for_lab(lab)
            .filter(
                deleted_at__isnull=True,
                status=ApprovalStatus.ACTIVE,
                expiry_date__gte=today,
                expiry_date__lte=horizon,
            )
            .prefetch_related("projects")
        )
        for approval in approvals:
            days = (approval.expiry_date - today).days
            threshold = threshold_for(days)
            key = f"ethics:{approval.pk}:{threshold}:{approval.expiry_date.isoformat()}"
            when = "today" if days == 0 else f"in {days} day(s)"
            title = f"Ethics approval {approval.approval_number} expires {when}"
            body = (
                f"{approval.title} ({approval.board} {approval.approval_number}) expires on "
                f"{approval.expiry_date}. This is the {threshold}-day reminder."
            )
            for user in _recipients(lab, approval):
                created += notify(
                    lab=lab,
                    recipient=user,
                    kind=NotificationKind.ETHICS_EXPIRY,
                    title=title,
                    body=body,
                    target=approval,
                    dedupe_key=key,
                )
    return created
