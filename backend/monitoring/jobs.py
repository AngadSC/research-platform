"""Sensor jobs: quiet sensors every few minutes, and the hourly roll-up of old readings."""

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncHour
from django.utils import timezone

from labs.models import Lab
from monitoring import services
from monitoring.models import Reading, ReadingHour, Sensor

RAW_DAYS = 30


@shared_task
def check_silent_sensors() -> int:
    """Open a "quiet" alert for each active sensor whose last reading is older than its window.
    A sensor that never reported is still being set up, so it is left alone."""
    now = timezone.now()
    opened = 0
    for lab in Lab.objects.filter(inventory_enabled=True):  # D227
        quiet = Sensor.objects.for_lab(lab).filter(active=True, last_at__isnull=False)
        for sensor in quiet:
            if sensor.last_at <= now - timedelta(minutes=sensor.silent_after_minutes):
                opened += services.mark_silent(sensor, now)
    return opened


@shared_task
def roll_up_readings() -> int:
    """Readings older than RAW_DAYS become one min/max/mean row per sensor and hour. Readings are
    never accepted more than a day late (services.MAX_AGE), so a rolled-up hour is complete."""
    cutoff = (timezone.now() - timedelta(days=RAW_DAYS)).replace(minute=0, second=0, microsecond=0)
    old = Reading.objects.filter(at__lt=cutoff)
    hours = (
        old.annotate(hour=TruncHour("at"))
        .values("sensor_id", "hour")
        .annotate(low=Min("value"), high=Max("value"), mean=Avg("value"), n=Count("id"))
        .order_by()
    )
    with transaction.atomic():  # ponytail: one batch; chunk by sensor if a backlog gets huge
        ReadingHour.objects.bulk_create(
            [
                ReadingHour(
                    sensor_id=h["sensor_id"],
                    hour=h["hour"],
                    low=h["low"],
                    high=h["high"],
                    mean=h["mean"],
                    count=h["n"],
                )
                for h in hours
            ],
            ignore_conflicts=True,  # a run that stopped after this line wrote the same rows
        )
        deleted, _ = old.delete()
    return deleted
