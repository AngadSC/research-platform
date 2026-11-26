"""Demo sensors (WETLAB.md): a -80 °C freezer with a week of readings and one acknowledged
excursion, a 4 °C cold room and a 37 °C shaker incubator. All values are made up."""

import math
import random
from datetime import timedelta

from django.utils import timezone

from labs.models import InventoryItem
from monitoring.models import Reading, Sensor, SensorAlert

STEP = timedelta(minutes=10)
DAYS = 7
# A week of history ends now and no device keeps posting after the seed, so the demo sensors get
# a 7-day quiet window; otherwise they would all report "quiet" half an hour after seeding.
QUIET = 7 * 24 * 60


def _item(lab, name, location, owner):
    return InventoryItem.objects.create(
        lab=lab, name=name, category="equipment", location=location, owner=owner, quantity=1
    )


def _history(sensor, base, noise, rng, now, excursion=None):
    """Readings every 10 minutes for a week: noise, a slow daily drift, the odd door opening and,
    for the freezer, one excursion `(start, minutes, peak)`."""
    rows, at = [], now - timedelta(days=DAYS)
    while at <= now:
        value = base + rng.gauss(0, noise) + noise * math.sin(at.timestamp() / 43200 * math.pi)
        if rng.random() < 0.02:  # a door opened for a sample: a short blip, no alert
            value += noise * 6
        if excursion and excursion[0] <= at < excursion[0] + timedelta(minutes=excursion[1]):
            done = (at - excursion[0]) / timedelta(minutes=excursion[1])
            value = base + (excursion[2] - base) * math.sin(done * math.pi)
        rows.append(Reading(sensor=sensor, at=at, value=round(value, 2)))
        at += STEP
    Reading.objects.bulk_create(rows)
    sensor.last_value, sensor.last_at = rows[-1].value, rows[-1].at
    sensor.save(update_fields=["last_value", "last_at"])
    return rows


def seed(lab, users: dict) -> None:
    pi = users.get("pi") or next(iter(users.values()))
    keeper = users.get("admin") or users.get("lead") or pi  # looks after the freezers
    rng = random.Random(80)
    now = timezone.now().replace(second=0, microsecond=0)

    freezer = Sensor.objects.create(
        lab=lab,
        name="-80 Freezer B",
        item=_item(lab, "-80 °C freezer B (Thermo TSX)", "Room 2-115", keeper),
        low_limit=-90,
        high_limit=-70,
        silent_after_minutes=QUIET,
    )
    freezer.recipients.set([keeper])
    start = (now - timedelta(days=3)).replace(hour=14, minute=10)
    rows = _history(freezer, -80.2, 0.4, rng, now, excursion=(start, 50, -61.2))
    out = [r for r in rows if r.value > freezer.high_limit]
    SensorAlert.objects.create(
        lab=lab,
        sensor=freezer,
        kind="high",
        value=out[1].value,  # two readings in a row raise it
        peak=max(r.value for r in out),
        started_at=out[1].at,
        ended_at=out[-1].at + STEP,
        acknowledged_by=pi,
        acknowledged_at=out[1].at + timedelta(minutes=6),
        note=(
            "Door left ajar after a sample pull. Closed it and moved the CMP-Neu5Ac aliquots "
            "and the MBP-ST6Gal1 glycerol stocks to Freezer A until it settled."
        ),
    )

    cold = Sensor.objects.create(
        lab=lab,
        name="Cold room",
        item=_item(lab, "Cold room (4 °C)", "Room 2-110", keeper),
        low_limit=2,
        high_limit=8,
        silent_after_minutes=QUIET,
    )
    cold.recipients.set([keeper])
    _history(cold, 4.1, 0.25, rng, now)

    shaker = Sensor.objects.create(
        lab=lab,
        name="Shaker incubator",
        item=_item(lab, "Shaker incubator (Innova 44)", "Room 2-112", keeper),
        low_limit=36,
        high_limit=38,
        silent_after_minutes=QUIET,
    )
    shaker.recipients.set([keeper])
    _history(shaker, 37.0, 0.1, rng, now)
