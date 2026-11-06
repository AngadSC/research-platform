"""Daily housekeeping for the AI access app (D200)."""

from datetime import timedelta

from celery import shared_task
from django.db.models import Exists, OuterRef
from django.utils import timezone

from assistant.models import AIGrant, OAuthClient

CLIENT_GRACE = timedelta(hours=24)


@shared_task
def prune_unused_clients() -> int:
    """Dynamic registration is open to anyone (20 an hour per IP), so rows pile up. Delete clients
    older than 24 hours that never received a grant (a grant keeps its client: PROTECT)."""
    used = AIGrant.objects.filter(client=OuterRef("pk"))
    old = OAuthClient.objects.filter(created_at__lt=timezone.now() - CLIENT_GRACE)
    return old.filter(~Exists(used)).delete()[0]
