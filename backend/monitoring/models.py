"""Freezer, fridge and incubator sensors. A cheap Wi-Fi device posts readings with its own token;
people are told when a reading is out of range or the sensor goes quiet. Lab-level, like
inventory: every member reads, manage_inventory changes, and it is off with inventory (D227)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from core.tenancy import LabScopedModel


class Unit(models.TextChoices):
    CELSIUS = "c", "°C"
    HUMIDITY = "rh", "% humidity"
    CO2 = "co2", "% CO2"


SYMBOL = {Unit.CELSIUS: " °C", Unit.HUMIDITY: "%", Unit.CO2: "% CO2"}


class Sensor(LabScopedModel):
    """One probe. Only the SHA-256 of its device token is kept; the token is shown once."""

    permission_domain = "lab"
    lab_parents = ("item",)

    name = models.CharField(max_length=200)
    item = models.ForeignKey(
        "labs.InventoryItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.CELSIUS)
    low_limit = models.FloatField(null=True, blank=True)
    high_limit = models.FloatField(null=True, blank=True)
    silent_after_minutes = models.PositiveIntegerField(default=30)
    # PIs and lab admins are always told; these are the other people who are.
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")
    active = models.BooleanField(default=True)  # off: readings are kept, nobody is alerted
    token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    token_created_at = models.DateTimeField(null=True, blank=True)
    last_value = models.FloatField(null=True, blank=True)
    last_at = models.DateTimeField(null=True, blank=True)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.CheckConstraint(
                condition=Q(low_limit__isnull=True)
                | Q(high_limit__isnull=True)
                | Q(low_limit__lt=models.F("high_limit")),
                name="sensor_low_below_high",
            )
        ]

    def __str__(self):
        return self.name

    def show(self, value) -> str:
        """-61 °C, 45.5%, 5% CO2."""
        return "" if value is None else f"{round(value, 1):g}{SYMBOL.get(self.unit, '')}"


class Reading(models.Model):
    """One value. Not lab-scoped on purpose: there are many, so each row is small. Always read
    through a Sensor that was itself looked up lab-scoped. Kept 30 days, then rolled up hourly."""

    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="+")
    at = models.DateTimeField()
    value = models.FloatField()

    class Meta:
        indexes = [models.Index(fields=["sensor", "at"], name="reading_sensor_at_idx")]

    def __str__(self):
        return f"{self.value} at {self.at}"


class ReadingHour(models.Model):
    """An hour of readings older than 30 days (jobs.roll_up_readings). Same rule as Reading."""

    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="+")
    hour = models.DateTimeField()
    low = models.FloatField()
    high = models.FloatField()
    mean = models.FloatField()
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sensor", "hour"], name="readinghour_one_per_hour")
        ]

    def __str__(self):
        return f"{self.mean} in the hour from {self.hour}"


class AlertKind(models.TextChoices):
    HIGH = "high"
    LOW = "low"
    SILENT = "silent"


class SensorAlert(LabScopedModel):
    """Out of range or quiet, from `started_at` until `ended_at`. At most one open per sensor and
    kind, so a long excursion is one alert, not one per reading."""

    permission_domain = "lab"
    lab_parents = ("sensor",)

    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=8, choices=AlertKind.choices)
    value = models.FloatField(null=True, blank=True)  # the reading that raised it
    peak = models.FloatField(null=True, blank=True)  # the worst reading while it was open
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta(LabScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["sensor", "kind"],
                condition=Q(ended_at__isnull=True),
                name="sensoralert_one_open",
            )
        ]
        indexes = [models.Index(fields=["sensor", "-started_at"], name="sensoralert_time_idx")]

    def __str__(self):
        return f"{self.sensor} {self.kind}"
