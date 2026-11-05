"""Daily integration jobs (ARCHITECTURE section 9)."""

from celery import shared_task

from integrations.services import revoke_orphaned_accounts


@shared_task
def revoke_orphans() -> int:
    """Revoke accounts whose owner left the lab or was deactivated (a missed lifecycle hook)."""
    return revoke_orphaned_accounts()
