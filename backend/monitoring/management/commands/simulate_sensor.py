"""Post made-up readings to a sensor for a demo: steady values with a little noise, and a door left
open part way through that pushes past the high limit for a few readings, then recovers.

    python manage.py simulate_sensor lbs_... --count 40 --every 15

The readings go through the same checks and alerts as a real device's.
"""

import random
import time

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitoring import services

DOOR = (0.5, 1.1, 1.2, 0.7, 0.3)  # share of the gap to the high limit, reading by reading


def values(sensor, count, door_at, rng):
    """`count` believable readings; from reading `door_at` the door is open for a few."""
    lo, hi = sensor.low_limit, sensor.high_limit
    if lo is not None and hi is not None:
        base = (lo + hi) / 2
    else:
        base = sensor.last_value if sensor.last_value is not None else 4.0
    room = (hi - base) if hi is not None else 5.0
    for i in range(count):
        step = i - door_at
        bump = DOOR[step] * room if door_at and 0 <= step < len(DOOR) else 0
        yield round(base + bump + rng.gauss(0, max(abs(room) * 0.02, 0.05)), 2)


class Command(BaseCommand):
    help = "Post realistic readings to a sensor over time, with a door-open spike (for demos)."

    def add_arguments(self, parser):
        parser.add_argument("token", help="The sensor's device token")
        parser.add_argument("--count", type=int, default=40)
        parser.add_argument("--every", type=float, default=15, help="Seconds between readings")
        parser.add_argument(
            "--door-at", type=int, default=10, help="Reading where it opens; 0: never"
        )

    def handle(self, token, count, every, door_at, **options):
        sensor = services.sensor_for_token(token)
        if sensor is None:
            raise CommandError("No sensor has that token. Make one on the sensor's page.")
        for i, value in enumerate(values(sensor, count, door_at, random.Random())):
            services.record_reading(sensor, value, timezone.now())
            self.stdout.write(f"{i + 1}/{count}: {sensor.show(value)}")
            if i + 1 < count:
                time.sleep(every)
