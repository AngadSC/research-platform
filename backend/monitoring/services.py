"""Sensors: settings, device tokens, readings and alerts. Every change a person makes is audited;
readings come from devices and are not."""

import math
import secrets
import time
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction as A
from audit.services import record
from core.email import send_email
from core.models import NotificationKind, User
from core.notifications import notify
from core.permissions import Perm, can, forget, users_with
from core.tenancy import by_secret
from labs.models import InventoryItem, LabMembership, hash_token
from monitoring.models import AlertKind, Reading, Sensor, SensorAlert

TOKEN_PREFIX = "lbs_"  # so a leaked one is easy to recognise in a log or a paste
RATE_PER_MINUTE = 12  # per sensor; a Shelly posts every few minutes, an ESP32 every 30 s or so
VALUE_RANGE = (-300.0, 1000.0)  # liquid nitrogen to an oven; anything else is a broken probe
MAX_AGE = timedelta(hours=24)  # a device that was offline may send what it buffered
MAX_AHEAD = timedelta(minutes=5)  # device clocks drift
FAR = 5.0  # with only one limit set, this far past it alerts on the first reading


# ---------------------------------------------------------------- settings


def _item(lab, item_id):
    if item_id is None:
        return None
    item = InventoryItem.objects.for_lab(lab).filter(pk=item_id).first()
    if item is None:
        raise ValidationError({"item": "Pick an item from this lab's inventory."})
    return item


def _recipients(lab, ids):
    users = list(
        User.objects.filter(
            pk__in=LabMembership.objects.for_lab(lab).filter(user_id__in=ids).values("user_id")
        )
    )
    if len(users) != len(set(ids)):
        raise ValidationError({"recipients": "Everyone here must be a member of the lab."})
    return users


def _check_limits(low, high):
    if low is not None and high is not None and low >= high:
        raise ValidationError({"high_limit": "The high limit must be above the low limit."})


@transaction.atomic
def create_sensor(*, lab, user, data, request=None):
    data = dict(data)
    item = _item(lab, data.pop("item", None))
    ids = data.pop("recipients", None)
    _check_limits(data.get("low_limit"), data.get("high_limit"))
    sensor = Sensor.objects.create(lab=lab, item=item, **data)
    if ids is None:  # by default the item's owner is told, as well as the PIs and admins
        ids = [item.owner_id] if item is not None and item.owner_id else []
    sensor.recipients.set(_recipients(lab, ids))
    record(A.SENSOR_CREATED, actor=user, lab=lab, target=sensor, request=request)
    return sensor


@transaction.atomic
def update_sensor(sensor, *, user, data, request=None):
    sensor = Sensor.objects.for_lab(sensor.lab_id).select_for_update().get(pk=sensor.pk)
    data = dict(data)
    changed = []
    if "item" in data:
        item = _item(sensor.lab, data.pop("item"))
        if item != sensor.item:
            sensor.item = item
            changed.append("item")
    if "recipients" in data:
        users = _recipients(sensor.lab, data.pop("recipients"))
        if {u.pk for u in users} != set(sensor.recipients.values_list("pk", flat=True)):
            sensor.recipients.set(users)
            changed.append("recipients")
    for key, value in data.items():
        if getattr(sensor, key) != value:
            setattr(sensor, key, value)
            changed.append(key)
    _check_limits(sensor.low_limit, sensor.high_limit)
    if not changed:
        return sensor
    sensor.save()
    if not sensor.active:  # paused: nothing is left open to nag about
        SensorAlert.objects.for_lab(sensor.lab_id).filter(
            sensor=sensor, ended_at__isnull=True
        ).update(ended_at=timezone.now())
    record(
        A.SENSOR_UPDATED,
        actor=user,
        lab=sensor.lab,
        target=sensor,
        request=request,
        metadata={"changed": sorted(changed)},
    )
    return sensor


@transaction.atomic
def delete_sensor(sensor, *, user, request=None):
    record(A.SENSOR_DELETED, actor=user, lab=sensor.lab, target=sensor, request=request)
    sensor.delete()  # its readings and alerts go with it


# ---------------------------------------------------------------- device tokens


@transaction.atomic
def issue_token(sensor, *, user, request=None) -> str:
    """A new 256-bit secret; any earlier one stops working at once."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    rotated = sensor.token_hash is not None
    sensor.token_hash = hash_token(token)
    sensor.token_created_at = timezone.now()
    sensor.save(update_fields=["token_hash", "token_created_at", "updated_at"])
    action = A.SENSOR_TOKEN_ROTATED if rotated else A.SENSOR_TOKEN_CREATED
    record(action, actor=user, lab=sensor.lab, target=sensor, request=request)
    return token


@transaction.atomic
def revoke_token(sensor, *, user, request=None) -> None:
    if sensor.token_hash is None:
        return
    sensor.token_hash = None
    sensor.token_created_at = None
    sensor.save(update_fields=["token_hash", "token_created_at", "updated_at"])
    record(A.SENSOR_TOKEN_REVOKED, actor=user, lab=sensor.lab, target=sensor, request=request)


def sensor_for_token(token: str):
    """The sensor a device token belongs to, or None. Looked up by the secret alone."""
    if not token or len(token) > 200:
        return None
    return by_secret(Sensor).filter(token_hash=hash_token(token)).select_related("lab").first()


def take_slot(sensor) -> bool:
    """At most RATE_PER_MINUTE readings per sensor per clock minute."""
    key = f"sensor-ingest:{sensor.pk}:{int(time.time() // 60)}"
    cache.add(key, 0, 90)
    try:
        return cache.incr(key) <= RATE_PER_MINUTE
    except ValueError:  # the key expired between add and incr
        return True


def clean_reading(raw_value, raw_at, now):
    """(value, at) from what a device sent, or ValueError with a short message for the device."""
    if isinstance(raw_value, bool) or not isinstance(raw_value, int | float | str):
        raise ValueError("Send value as a number.")
    try:
        value = float(raw_value) if len(str(raw_value)) <= 32 else math.nan
    except (ValueError, OverflowError):
        raise ValueError("Send value as a number.") from None
    lo, hi = VALUE_RANGE
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"value must be a number from {lo:g} to {hi:g}.")
    if raw_at in (None, ""):
        return value, now
    try:
        at = parse_datetime(raw_at) if isinstance(raw_at, str) and len(raw_at) <= 40 else None
    except ValueError:
        at = None
    if at is None:
        raise ValueError("Send at as an ISO 8601 time, like 2026-11-26T14:05:00Z.")
    if timezone.is_naive(at):
        at = at.replace(tzinfo=UTC)
    if at > now + MAX_AHEAD:
        raise ValueError("at is in the future. Check the device clock.")
    if at < now - MAX_AGE:
        raise ValueError("at is more than 24 hours old.")
    return value, at


# ---------------------------------------------------------------- readings and alerts


def _open(sensor, kind):
    alert = (
        SensorAlert.objects.for_lab(sensor.lab_id)
        .filter(sensor=sensor, kind=kind, ended_at__isnull=True)
        .first()
    )
    if alert is not None:
        alert.sensor = sensor  # the locked row, with the reading being judged
    return alert


def _direction(sensor, value):
    if sensor.high_limit is not None and value > sensor.high_limit:
        return AlertKind.HIGH
    if sensor.low_limit is not None and value < sensor.low_limit:
        return AlertKind.LOW
    return None


def is_far(sensor, value) -> bool:
    """Far out alerts on one reading: past a limit by half the allowed band (or by FAR with one
    limit). A door opened for a moment is a small blip that the second reading clears."""
    lo, hi = sensor.low_limit, sensor.high_limit
    margin = (hi - lo) / 2 if lo is not None and hi is not None else FAR
    return (hi is not None and value > hi + margin) or (lo is not None and value < lo - margin)


def _end(alert, at, events):
    alert.ended_at = at
    alert.save(update_fields=["ended_at", "updated_at"])
    events.append((alert, False))


def _judge(sensor, before, value, at) -> list:
    """Opens and ends alerts for a new latest reading (`before` is the one it replaces); returns
    [(alert, opened)]. Two readings in a row past the same limit open an alert, or one far out."""
    events = []
    silent = _open(sensor, AlertKind.SILENT)
    if silent is not None:
        _end(silent, at, events)
    direction = _direction(sensor, value) if sensor.active else None
    for kind in (AlertKind.HIGH, AlertKind.LOW):
        alert = _open(sensor, kind)
        if alert is not None and kind != direction:
            _end(alert, at, events)
    if direction is None:
        return events
    alert = _open(sensor, direction)
    if alert is not None:
        worse = max if direction == AlertKind.HIGH else min
        alert.peak = worse(alert.peak if alert.peak is not None else value, value)
        alert.save(update_fields=["peak", "updated_at"])
    elif (before is not None and _direction(sensor, before) == direction) or is_far(sensor, value):
        alert = SensorAlert.objects.create(
            lab_id=sensor.lab_id,
            sensor=sensor,
            kind=direction,
            value=value,
            peak=value,
            started_at=at,
        )
        events.append((alert, True))
    return events


def record_reading(sensor, value, at) -> None:
    """Store one reading. Only a reading newer than the last one can raise or end an alert, so
    readings a device sends late are kept for the chart but never judged."""
    with transaction.atomic():
        sensor = (
            Sensor.objects.for_lab(sensor.lab_id)
            .select_for_update(of=("self",))  # not the lab row
            .select_related("lab")
            .get(pk=sensor.pk)
        )
        Reading.objects.create(sensor=sensor, at=at, value=value)
        if sensor.last_at is not None and at <= sensor.last_at:
            return
        before = sensor.last_value
        sensor.last_value, sensor.last_at = value, at
        events = _judge(sensor, before, value, at)
        sensor.save(update_fields=["last_value", "last_at", "updated_at"])
        for alert, opened in events:
            announce(alert, opened)


def mark_silent(sensor, now) -> bool:
    """Open a "quiet" alert if the sensor has reported before but not for its silence window."""
    with transaction.atomic():
        sensor = (
            Sensor.objects.for_lab(sensor.lab_id)
            .select_for_update(of=("self",))  # not the lab row
            .select_related("lab")
            .get(pk=sensor.pk)
        )
        window = timedelta(minutes=sensor.silent_after_minutes)
        if not sensor.active or sensor.last_at is None or sensor.last_at > now - window:
            return False
        if _open(sensor, AlertKind.SILENT) is not None:
            return False
        alert = SensorAlert.objects.create(
            lab_id=sensor.lab_id,
            sensor=sensor,
            kind=AlertKind.SILENT,
            value=sensor.last_value,
            started_at=now,
        )
        announce(alert, True)
        return True


def recipients(sensor) -> list:
    """The PIs and lab admins, and the people picked on the sensor, while they are in the lab."""
    people = {u.pk: u for u in users_with(Perm.MANAGE_LAB, sensor.lab)}
    people.update({u.pk: u for u in sensor.recipients.filter(is_active=True)})
    out = []
    for user in people.values():
        forget(user)
        if can(user, Perm.VIEW_LAB, sensor.lab):
            out.append(user)
    return out


def _minutes(alert) -> str:
    n = max(1, round((alert.ended_at - alert.started_at).total_seconds() / 60))
    return f"{n} minute{'s' * (n != 1)}" if n < 120 else f"{round(n / 60)} hours"


def message(alert, opened) -> tuple[str, str]:
    s = alert.sensor
    if alert.kind == AlertKind.SILENT:
        if opened:
            return (
                f"{s.name} has gone quiet",
                f"No reading for {s.silent_after_minutes} minutes. The last one was "
                f"{s.show(s.last_value)}. Check the sensor's power and Wi-Fi, and the "
                "equipment itself.",
            )
        return f"{s.name} is reporting again", f"Latest reading: {s.show(s.last_value)}."
    if opened:
        high = alert.kind == AlertKind.HIGH
        limit = s.high_limit if high else s.low_limit
        side = "above" if high else "below"
        return (
            f"{s.name} is at {s.show(alert.value)}",
            f"That is {side} its limit of {s.show(limit)}. Check it now, then acknowledge the "
            "alert so the others know someone is on it.",
        )
    return (
        f"{s.name} is back in range",
        f"Now {s.show(s.last_value)}. It was out of range for {_minutes(alert)}, at worst "
        f"{s.show(alert.peak)}.",
    )


def announce(alert, opened) -> None:
    """An in-app notification and an email to each recipient, once per alert and change.
    The email skips quiet hours on purpose: a thawing -80 cannot wait until morning."""
    sensor = alert.sensor
    title, body = message(alert, opened)
    link = f"{settings.FRONTEND_URL}/labs/{sensor.lab_id}/monitoring/{sensor.pk}"
    for user in recipients(sensor):
        created = notify(
            lab=sensor.lab,
            recipient=user,
            kind=NotificationKind.SENSOR_ALERT,
            title=title,
            body=body,
            target=sensor,
            dedupe_key=f"sensor-alert:{alert.pk}:{'open' if opened else 'end'}",
        )
        if created:
            send_email("notification", user.email, {"title": title, "body": f"{body}\n\n{link}"})


@transaction.atomic
def acknowledge(alert, *, user, note="", request=None):
    alert = SensorAlert.objects.for_lab(alert.lab_id).select_for_update().get(pk=alert.pk)
    if alert.acknowledged_at is not None:
        raise ValidationError({"detail": "Someone has already acknowledged this alert."})
    alert.acknowledged_by = user
    alert.acknowledged_at = timezone.now()
    alert.note = note
    alert.save(update_fields=["acknowledged_by", "acknowledged_at", "note", "updated_at"])
    record(
        A.SENSOR_ALERT_ACKNOWLEDGED,
        actor=user,
        lab=alert.lab,
        target=alert,
        request=request,
        metadata={"kind": alert.kind, "sensor": str(alert.sensor_id)},
    )
    return alert


# ---------------------------------------------------------------- charts


def series(sensor_ids, since, bucket: timedelta) -> dict:
    """{sensor_id: [{t, min, max, avg}]} in `bucket`-wide steps since `since`, one query for all."""
    step = bucket.total_seconds()
    out, cur = {}, {}
    rows = (
        Reading.objects.filter(sensor_id__in=sensor_ids, at__gte=since)
        .order_by("sensor_id", "at")
        .values_list("sensor_id", "at", "value")
    )
    for sid, at, value in rows.iterator():
        slot = int(at.timestamp() // step)
        last = cur.get(sid)
        if last is None or last[0] != slot:
            last = cur[sid] = [slot, value, value, 0.0, 0]
            out.setdefault(sid, []).append(last)
        last[1], last[2] = min(last[1], value), max(last[2], value)
        last[3] += value
        last[4] += 1
    return {
        sid: [
            {
                "t": datetime.fromtimestamp(slot * step, UTC),
                "min": lo,
                "max": hi,
                "avg": round(total / n, 3),
            }
            for slot, lo, hi, total, n in points
        ]
        for sid, points in out.items()
    }
