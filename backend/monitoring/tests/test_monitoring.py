"""Sensors: token scope, ingest checks, alerts, silence, roll-up, audit, and the demo seed."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from assistant.tests.reauth import sign_in
from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from labs.models import InventoryItem, LabRole
from monitoring import demo, jobs, services
from monitoring.models import AlertKind, Reading, ReadingHour, Sensor, SensorAlert

pytestmark = pytest.mark.django_db
INGEST = "/api/sensors/ingest/"


@pytest.fixture
def world(make_lab, make_user, join):
    lab, other = make_lab("Wet"), make_lab("Other")
    pi, member, viewer = make_user(), make_user(), make_user()
    outsider = make_user()
    join(pi, lab, LabRole.PI)
    join(member, lab, LabRole.MEMBER)
    join(viewer, lab, LabRole.VIEWER)
    join(outsider, other, LabRole.PI)
    item = InventoryItem.objects.create(lab=lab, name="-80", category="equipment", owner=member)
    sensor = Sensor.objects.create(
        lab=lab, item=item, name="-80 Freezer B", low_limit=-90, high_limit=-70
    )
    sensor.recipients.set([member])
    theirs = Sensor.objects.create(lab=other, name="Theirs")
    return {
        "lab": lab,
        "other": other,
        "pi": pi,
        "member": member,
        "viewer": viewer,
        "outsider": outsider,
        "sensor": sensor,
        "theirs": theirs,
    }


def api(user=None):
    client = APIClient()
    if user is not None:
        sign_in(client, user)
    return client


def token_for(sensor, user):
    return services.issue_token(sensor, user=user)


def post(token, value, **extra):
    body = {"value": value, **extra}
    return APIClient().post(INGEST, body, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")


def refresh(sensor):
    return Sensor.objects.for_lab(sensor.lab_id).get(pk=sensor.pk)


def alerts(sensor):
    return list(
        SensorAlert.objects.for_lab(sensor.lab_id).filter(sensor=sensor).order_by("started_at")
    )


def readings(sensor):
    return list(Reading.objects.filter(sensor=sensor).values_list("value", flat=True))


# ---------------------------------------------------------------- tokens and ingest


def test_token_writes_only_its_own_sensor(world):
    token = token_for(world["sensor"], world["pi"])
    assert token.startswith("lbs_") and len(token) > 40
    assert refresh(world["sensor"]).token_hash != token  # only the hash is kept
    assert post(token, -80.5).status_code == 204
    assert readings(world["sensor"]) == [-80.5]
    assert readings(world["theirs"]) == []
    # the GET form Shelly uses, with the token in the address
    resp = APIClient().get(INGEST, {"token": token, "value": "-80.1"})
    assert resp.status_code == 204 and resp.content == b""
    assert refresh(world["sensor"]).last_value == -80.1


def test_token_reads_nothing(world):
    token = token_for(world["sensor"], world["pi"])
    bearer = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    lab = world["lab"].pk
    for url in (f"/api/labs/{lab}/sensors/", f"/api/labs/{lab}/sensors/{world['sensor'].pk}/"):
        assert APIClient().get(url, **bearer).status_code == 401
    resp = APIClient().get(INGEST, {"token": token})  # no value: an error, and nothing else
    assert resp.status_code == 400
    assert set(resp.json()) == {"error"} and "-80" not in resp.content.decode()


def test_a_session_is_not_a_token(world):
    client = api(world["pi"])
    assert client.post(INGEST, {"value": -80}, format="json").status_code == 401
    assert readings(world["sensor"]) == []


def test_revoked_and_rotated_tokens_stop_working(world):
    sensor, pi = world["sensor"], world["pi"]
    old = token_for(sensor, pi)
    new = token_for(refresh(sensor), pi)
    assert post(old, -80).status_code == 401
    assert post(new, -80).status_code == 204
    services.revoke_token(refresh(sensor), user=pi)
    assert post(new, -80).status_code == 401
    assert post("", -80).status_code == 401
    assert post("lbs_" + "x" * 43, -80).status_code == 401


def test_rate_limit_per_sensor(world):
    token = token_for(world["sensor"], world["pi"])
    codes = [post(token, -80).status_code for _ in range(services.RATE_PER_MINUTE + 1)]
    assert codes[:-1] == [204] * services.RATE_PER_MINUTE and codes[-1] == 429
    other = token_for(world["theirs"], world["outsider"])  # each sensor has its own allowance
    assert post(other, 4).status_code == 204


@pytest.mark.parametrize(
    "body",
    [
        {"value": "nan"},
        {"value": "inf"},
        {"value": True},
        {"value": "cold"},
        {"value": 5000},
        {"value": [1]},
        {"value": "1" * 40},
        {},
        {"value": 1, "at": "yesterday"},
        {"value": 1, "at": (timezone.now() + timedelta(hours=1)).isoformat()},
        {"value": 1, "at": (timezone.now() - timedelta(days=2)).isoformat()},
    ],
)
def test_bad_readings_are_refused(world, body):
    token = token_for(world["sensor"], world["pi"])
    resp = APIClient().post(INGEST, body, format="json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 400 and "error" in resp.json()
    assert readings(world["sensor"]) == []


def test_late_reading_is_kept_but_not_judged(world):
    token = token_for(world["sensor"], world["pi"])
    assert post(token, -80).status_code == 204
    earlier = (timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")  # naive is UTC
    assert post(token, -20, at=earlier).status_code == 204
    sensor = refresh(world["sensor"])
    assert sorted(readings(sensor)) == [-80, -20]
    assert sensor.last_value == -80 and alerts(sensor) == []


def test_inventory_off_turns_monitoring_off(world):
    token = token_for(world["sensor"], world["pi"])
    world["lab"].inventory_enabled = False
    world["lab"].save()
    assert post(token, -80).status_code == 403
    assert api(world["pi"]).get(f"/api/labs/{world['lab'].pk}/sensors/").status_code == 403
    world["sensor"].last_at = timezone.now() - timedelta(days=1)
    world["sensor"].save()
    assert jobs.check_silent_sensors() == 0


# ---------------------------------------------------------------- alerts


def notes(user, lab):
    qs = Notification.objects.for_lab(lab).filter(
        recipient=user, kind=NotificationKind.SENSOR_ALERT
    )
    return list(qs.order_by("-created_at"))


def test_two_readings_out_of_range_alert_once_then_back_in_range(world, mailoutbox):
    sensor, member, pi, viewer = world["sensor"], world["member"], world["pi"], world["viewer"]
    lab = world["lab"]
    with TestCase.captureOnCommitCallbacks(execute=True):
        services.record_reading(sensor, -68, timezone.now())  # one blip: a door opened
    assert alerts(sensor) == []
    with TestCase.captureOnCommitCallbacks(execute=True):
        services.record_reading(sensor, -66, timezone.now())
        services.record_reading(sensor, -61, timezone.now())  # still the same alert
    [alert] = alerts(sensor)
    assert (alert.kind, alert.value, alert.peak, alert.ended_at) == ("high", -66, -61, None)
    # the PI and the chosen member are told; the viewer was not picked
    assert [n.title for n in notes(member, lab)] == ["-80 Freezer B is at -66 °C"]
    assert len(notes(pi, lab)) == 1 and notes(viewer, lab) == []
    assert sorted(m.subject for m in mailoutbox) == ["-80 Freezer B is at -66 °C"] * 2
    assert notes(member, lab)[0].target_id == sensor.pk
    with TestCase.captureOnCommitCallbacks(execute=True):
        services.record_reading(sensor, -80, timezone.now())
    [alert] = alerts(sensor)
    assert alert.ended_at is not None
    assert notes(member, lab)[0].title == "-80 Freezer B is back in range"
    assert "at worst -61 °C" in notes(member, lab)[0].body
    assert len(mailoutbox) == 4


def test_far_out_alerts_on_the_first_reading(world):
    sensor = world["sensor"]
    services.record_reading(sensor, -50, timezone.now())  # 20 past a 20-wide band
    assert [a.kind for a in alerts(sensor)] == [AlertKind.HIGH]
    services.record_reading(refresh(sensor), -95, timezone.now())  # straight to too cold
    kinds = [(a.kind, a.ended_at is None) for a in alerts(sensor)]
    assert kinds == [(AlertKind.HIGH, False)]  # high ended; low needs two in a row
    services.record_reading(refresh(sensor), -96, timezone.now())
    assert [(a.kind, a.ended_at is None) for a in alerts(sensor)][-1] == (AlertKind.LOW, True)


def test_paused_sensor_never_alerts(world):
    sensor = world["sensor"]
    services.record_reading(sensor, -50, timezone.now())
    services.update_sensor(sensor, user=world["pi"], data={"active": False})
    assert all(a.ended_at for a in alerts(sensor))  # pausing ends what was open
    services.record_reading(sensor, -40, timezone.now())
    services.record_reading(sensor, -40, timezone.now())
    assert len(alerts(sensor)) == 1


def test_acknowledge_is_audited_and_once(world):
    sensor, member = world["sensor"], world["member"]
    services.record_reading(sensor, -50, timezone.now())
    [alert] = alerts(sensor)
    url = f"/api/labs/{world['lab'].pk}/sensors/alerts/{alert.pk}/acknowledge/"
    resp = api(member).post(url, {"note": "Door was ajar"}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["acknowledged_by"]["id"] == str(member.pk)
    assert resp.json()["note"] == "Door was ajar"
    event = AuditEvent.objects.get(action=AuditAction.SENSOR_ALERT_ACKNOWLEDGED)
    assert (event.actor, event.target_id) == (member, alert.pk)
    assert api(world["pi"]).post(url, {}, format="json").status_code == 400
    assert api(world["viewer"]).post(url, {}, format="json").status_code == 403
    other_url = f"/api/labs/{world['other'].pk}/sensors/alerts/{alert.pk}/acknowledge/"
    assert api(world["outsider"]).post(other_url, {}, format="json").status_code == 404


# ---------------------------------------------------------------- silence and roll-up


def test_quiet_sensor_alerts_once_and_clears_on_a_reading(world, mailoutbox):
    sensor, member, lab = world["sensor"], world["member"], world["lab"]
    assert jobs.check_silent_sensors() == 0  # never reported: still being set up
    services.record_reading(sensor, -80, timezone.now() - timedelta(minutes=31))
    with TestCase.captureOnCommitCallbacks(execute=True):
        assert jobs.check_silent_sensors() == 1
        assert jobs.check_silent_sensors() == 0  # no repeat while it stays quiet
    assert notes(member, lab)[0].title == "-80 Freezer B has gone quiet"
    assert mailoutbox[-1].subject == "-80 Freezer B has gone quiet"
    services.record_reading(sensor, -80, timezone.now())
    [alert] = alerts(sensor)
    assert alert.kind == AlertKind.SILENT and alert.ended_at is not None
    assert notes(member, lab)[0].title == "-80 Freezer B is reporting again"


def test_old_readings_roll_up_hourly(world):
    sensor = world["sensor"]
    old = (timezone.now() - timedelta(days=40)).replace(minute=0, second=0, microsecond=0)
    for minute, value in ((5, -80), (25, -78), (55, -82)):
        Reading.objects.create(sensor=sensor, at=old + timedelta(minutes=minute), value=value)
    Reading.objects.create(sensor=sensor, at=timezone.now(), value=-79)
    assert jobs.roll_up_readings() == 3
    assert readings(sensor) == [-79]
    hour = ReadingHour.objects.get(sensor=sensor)
    assert (hour.hour, hour.low, hour.high, hour.mean, hour.count) == (old, -82, -78, -80, 3)
    assert jobs.roll_up_readings() == 0


# ---------------------------------------------------------------- the API


def test_create_defaults_and_audit(world):
    lab, pi, member = world["lab"], world["pi"], world["member"]
    item = InventoryItem.objects.for_lab(lab).get()
    url = f"/api/labs/{lab.pk}/sensors/"
    body = {"name": "Freezer A", "item": str(item.pk), "low_limit": -90, "high_limit": -70}
    resp = api(pi).post(url, body, format="json")
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert [r["id"] for r in data["recipients"]] == [str(member.pk)]  # the item's owner
    assert data["status"] == "waiting" and data["has_token"] is False
    assert data["unit_symbol"] == "°C" and data["item"]["name"] == "-80"
    sensor_url = f"{url}{data['id']}/"
    assert api(pi).patch(sensor_url, {"high_limit": -95}, format="json").status_code == 400
    outsider = str(world["outsider"].pk)
    resp = api(pi).patch(sensor_url, {"recipients": [outsider]}, format="json")
    assert resp.status_code == 400 and "recipients" in resp.json()
    their_item = InventoryItem.objects.create(lab=world["other"], name="x", category="equipment")
    resp = api(pi).patch(sensor_url, {"item": str(their_item.pk)}, format="json")
    assert resp.status_code == 400 and "item" in resp.json()
    assert api(pi).patch(sensor_url, {"name": "Freezer A2"}, format="json").status_code == 200
    resp = api(pi).post(f"{sensor_url}token/")
    assert resp.status_code == 201 and resp.json()["token"].startswith("lbs_")
    assert api(pi).post(f"{sensor_url}token/").status_code == 201
    assert api(pi).delete(f"{sensor_url}token/").status_code == 204
    assert api(pi).delete(sensor_url).status_code == 204
    actions = list(
        AuditEvent.objects.filter(lab=lab).order_by("occurred_at").values_list("action", flat=True)
    )
    assert actions == [
        AuditAction.SENSOR_CREATED,
        AuditAction.SENSOR_UPDATED,
        AuditAction.SENSOR_TOKEN_CREATED,
        AuditAction.SENSOR_TOKEN_ROTATED,
        AuditAction.SENSOR_TOKEN_REVOKED,
        AuditAction.SENSOR_DELETED,
    ]
    assert not any("lbs_" in str(e.metadata) for e in AuditEvent.objects.all())


def test_making_a_token_needs_a_recent_sign_in(world):
    client = APIClient()
    sign_in(client, world["pi"], seconds_ago=3600, reauthenticated=False)
    url = f"/api/labs/{world['lab'].pk}/sensors/{world['sensor'].pk}/token/"
    assert client.post(url).status_code == 401
    assert refresh(world["sensor"]).token_hash is None


def test_list_detail_and_test_reading(world):
    lab, sensor, pi = world["lab"], world["sensor"], world["pi"]
    url = f"/api/labs/{lab.pk}/sensors/{sensor.pk}/"
    resp = api(pi).post(f"{url}test-reading/", {"value": -79.6}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["last_value"] == -79.6 and resp.json()["status"] == "ok"
    assert len(resp.json()["series"]) == 1
    services.record_reading(refresh(sensor), -40, timezone.now())
    listed = api(world["viewer"]).get(f"/api/labs/{lab.pk}/sensors/").json()
    assert [s["name"] for s in listed] == ["-80 Freezer B"]  # never the other lab's
    assert listed[0]["status"] == "out_of_range" and listed[0]["alert"]["kind"] == "high"
    detail = api(world["viewer"]).get(url).json()
    assert [a["kind"] for a in detail["history"]] == ["high"]
    item = InventoryItem.objects.for_lab(lab).get()
    by_item = api(pi).get(f"/api/labs/{lab.pk}/sensors/", {"item": str(item.pk)}).json()
    assert len(by_item) == 1
    assert api(pi).get(f"/api/labs/{lab.pk}/sensors/", {"item": "nope"}).json() == []


def test_series_buckets(world):
    sensor = world["sensor"]
    start = datetime(2030, 1, 1, tzinfo=UTC)
    for minute, value in ((1, -80), (2, -78), (21, -70)):
        Reading.objects.create(sensor=sensor, at=start + timedelta(minutes=minute), value=value)
    points = services.series([sensor.pk], start, timedelta(minutes=20))[sensor.pk]
    assert [(p["t"], p["min"], p["max"], p["avg"]) for p in points] == [
        (start, -80, -78, -79),
        (start + timedelta(minutes=20), -70, -70, -70),
    ]


# ---------------------------------------------------------------- demo tools


def test_simulate_sensor_spikes_and_recovers(world):
    sensor = world["sensor"]
    token = token_for(sensor, world["pi"])
    call_command("simulate_sensor", token, count=18, every=0, door_at=5, stdout=io.StringIO())
    values = readings(sensor)
    assert len(values) == 18 and max(values) > -70 and min(values) > -90
    [alert] = alerts(sensor)
    assert alert.kind == AlertKind.HIGH and alert.ended_at is not None


def test_demo_seed(world):
    lab = world["other"]
    demo.seed(lab, {"pi": world["outsider"]})
    sensors = {s.name: s for s in Sensor.objects.for_lab(lab)}
    assert {"-80 Freezer B", "Cold room", "Shaker incubator", "Theirs"} == set(sensors)
    freezer = sensors["-80 Freezer B"]
    [alert] = alerts(freezer)
    assert alert.acknowledged_by == world["outsider"] and alert.ended_at and alert.peak > -70
    assert len(readings(freezer)) > 1000
    assert jobs.check_silent_sensors() == 0
    assert all(a.ended_at for s in sensors.values() for a in alerts(s))
