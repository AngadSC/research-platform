"""Daily integration jobs (ARCHITECTURE section 9)."""

from celery import shared_task

from integrations.services import check_all_links, revoke_orphaned_accounts


@shared_task
def check_links() -> dict:
    """Refresh link metadata with each linker's own token (ARCHITECTURE section 9)."""
    return check_all_links()


@shared_task
def revoke_orphans() -> int:
    """Revoke accounts whose owner left the lab or was deactivated (a missed lifecycle hook)."""
    return revoke_orphaned_accounts()
