"""The morning digest (an email, not a stream of pings): what is due today and what is overdue,
for each person who turned it on. Runs every hour and sends to the people whose own morning it
is. Tasks the person snoozed are left out, and a day with nothing due sends nothing."""

import datetime

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.email import send_email
from core.models import User
from core.permissions import forget, labs_for
from core.quiet import digest_hour, zone_of
from projects.models import Task, TaskStatus

MAX_LISTED = 8


def tasks_for_today(user, today: datetime.date) -> list[Task]:
    """Open tasks assigned to `user`, due today or earlier, not snoozed past today, in labs they
    are still in, and that they can still see."""
    rows: list[Task] = []
    forget(user)
    for lab in labs_for(user):
        found = (
            Task.objects.visible_to(user, lab)
            .filter(assignee=user, due_date__lte=today)
            .exclude(status=TaskStatus.DONE)
            .exclude(snoozed_until__gt=today)
            .select_related("project")
        )
        rows.extend(found)
    return sorted(rows, key=lambda t: (t.due_date, t.title))


def build(user, today: datetime.date) -> dict | None:
    tasks = tasks_for_today(user, today)
    if not tasks:
        return None
    overdue = sum(t.due_date < today for t in tasks)
    due = len(tasks) - overdue
    n = len(tasks)
    parts = [f"{due} due today" if due else "", f"{overdue} overdue" if overdue else ""]
    return {
        "count": n,
        "headline": f"{n} thing{'s' * (n != 1)} today",
        "summary": ", ".join(p for p in parts if p),
        "items": [
            {
                "title": t.title,
                "project": t.project.name,
                "due": "Today" if t.due_date == today else f"Overdue since {t.due_date:%b %-d}",
                "url": f"{settings.FRONTEND_URL}/labs/{t.lab_id}/projects/{t.project_id}"
                f"/tasks?task={t.pk}",
            }
            for t in tasks[:MAX_LISTED]
        ],
        "more": max(0, n - MAX_LISTED),
        "home_url": f"{settings.FRONTEND_URL}/",
    }


@shared_task
def send_task_digests(now: datetime.datetime | None = None) -> int:
    """Send each opted-in person their digest when their own clock reaches their hour. Returns
    how many were queued."""
    now = now or timezone.now()
    sent = 0
    for user in User.objects.filter(is_active=True, preferences__digest="on"):
        local = now.astimezone(zone_of(user))
        if local.hour != digest_hour(user):
            continue
        # One per person per local day, even if the hourly job runs twice.
        if not cache.add(f"digest:{user.pk}:{local.date()}", 1, timeout=30 * 3600):
            continue
        context = build(user, local.date())
        if context is None:
            continue
        send_email("task_digest", user.email, context)
        sent += 1
    return sent
