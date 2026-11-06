"""Daily integration jobs (ARCHITECTURE section 9, D120).

The link check runs as one Celery task per lab, so a lab with slow servers can't hold up the
others, and each task has a soft limit (it stops and reports) and a hard limit (it is killed).
Inside, every link and every request has its own deadline (`integrations.http.budget`).
"""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from integrations.services import check_all_links, check_lab_links, revoke_orphaned_accounts
from labs.models import Lab

log = logging.getLogger("integrations.jobs")

LAB_SOFT_LIMIT = 1200  # seconds; INTEGRATION_JOB_LAB_BUDGET (900) ends the loop earlier
LAB_HARD_LIMIT = 1260
ALL_SOFT_LIMIT = 6 * 3600
ALL_HARD_LIMIT = ALL_SOFT_LIMIT + 60


@shared_task(soft_time_limit=ALL_SOFT_LIMIT, time_limit=ALL_HARD_LIMIT)
def check_links() -> dict:
    """Refresh link metadata for every lab in turn, with each linker's own token (ARCHITECTURE
    section 9). Kept for manual runs; the schedule uses `check_links_by_lab`."""
    try:
        return check_all_links()
    except SoftTimeLimitExceeded:
        log.warning("integration link check stopped at its time limit")
        return {"checked": 0, "skipped": 0, "failed": 1}


@shared_task(soft_time_limit=LAB_SOFT_LIMIT, time_limit=LAB_HARD_LIMIT)
def check_lab_links_task(lab_id) -> dict:
    """Refresh link metadata for one lab."""
    lab = Lab.objects.filter(pk=lab_id).first()
    if lab is None:
        return {"checked": 0, "skipped": 0, "failed": 0}
    try:
        return check_lab_links(lab)
    except SoftTimeLimitExceeded:
        log.warning("integration link check for a lab stopped at its time limit")
        return {"checked": 0, "skipped": 0, "failed": 1}


@shared_task(soft_time_limit=300, time_limit=360)
def check_links_by_lab() -> int:
    """Daily entry point: queue one `check_lab_links_task` per lab. Returns how many."""
    ids = list(Lab.objects.values_list("pk", flat=True))
    for lab_id in ids:
        check_lab_links_task.delay(str(lab_id))
    return len(ids)


@shared_task(soft_time_limit=600, time_limit=660)
def revoke_orphans() -> int:
    """Revoke accounts whose owner left the lab or was deactivated (a missed lifecycle hook)."""
    return revoke_orphaned_accounts()
