"""Liveness and readiness probe for Caddy and the Dockerfile HEALTHCHECK (deploy/).

Plain Django view outside /api/, unauthenticated. It reports only which check failed; hosts,
passwords and driver messages stay in the server log.
"""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def healthz(request):
    failed = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("healthz: database check failed")
        failed.append("database")
    try:
        cache.set("healthz", "1", 10)
        if cache.get("healthz") != "1":
            raise RuntimeError("cache round-trip returned the wrong value")
    except Exception:
        logger.exception("healthz: valkey check failed")
        failed.append("valkey")
    if failed:
        return JsonResponse({"status": "error", "failed": failed}, status=503)
    return JsonResponse({"status": "ok"})
