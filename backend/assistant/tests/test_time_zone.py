"""D291: dates follow each person's own time zone, as their browser reports it, on the site and
through the connector. 8:02 pm in Edmonton is already tomorrow in UTC."""

import datetime
import json
import zoneinfo
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone

from assistant.tests.test_mcp import _base, data, pat, rpc  # noqa: F401 (_base is a fixture)
from core.middleware import user_zone

pytestmark = pytest.mark.django_db
EDMONTON = "America/Edmonton"


def late_evening():
    """03:02 UTC on a day near the real one (tokens and sessions stay valid): 8:02 pm the evening
    before in Edmonton. Returns the instant and the Edmonton date."""
    fake = timezone.now().replace(hour=3, minute=2, second=0, microsecond=0)
    return fake, fake.date() - datetime.timedelta(days=1)


def set_zone(user, name):
    user.preferences = {**user.preferences, "time_zone": name}
    user.save(update_fields=["preferences"])


def test_the_browser_zone_is_saved_and_a_bad_one_refused(world):
    c = Client()
    c.force_login(world.u.pi)
    # Chrome still reports the old Indian name; Postgres only knows the new one
    for name, saved in ((EDMONTON, EDMONTON), ("Asia/Calcutta", "Asia/Kolkata"), ("UTC", "UTC")):
        resp = c.patch("/api/me/", {"preferences": {"time_zone": name}}, "application/json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["preferences"]["time_zone"] == saved
    for bad in ("Mars/Olympus", "../etc/passwd", "zone.tab", "", 5, [], {}, ["UTC"]):
        resp = c.patch("/api/me/", {"preferences": {"time_zone": bad}}, "application/json")
        assert resp.status_code == 400
    world.u.pi.refresh_from_db()
    assert world.u.pi.preferences["time_zone"] == "UTC"


def test_unset_or_unknown_stored_zone_is_utc(world):
    assert user_zone(world.u.pi) is datetime.UTC
    set_zone(world.u.pi, "Nowhere/Special")  # stored before a tzdata change, say
    assert user_zone(world.u.pi) is datetime.UTC
    set_zone(world.u.pi, EDMONTON)
    assert str(user_zone(world.u.pi)) == EDMONTON


def test_a_session_request_runs_in_the_persons_zone(world):
    fake, local_day = late_evening()
    set_zone(world.u.pi, EDMONTON)
    c = Client()
    c.force_login(world.u.pi)
    url = f"/api/labs/{world.lab_a.pk}/projects/{world.p1.pk}/decisions/"
    with mock.patch("django.utils.timezone.now", return_value=fake):
        resp = c.post(url, {"title": "Use the mixed model"}, "application/json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["decided_on"] == local_day.isoformat()
    assert resp.json()["created_at"].endswith(("-06:00", "-07:00"))  # DRF writes local times
    assert timezone.get_current_timezone_name() == "UTC"  # nothing leaks past the request


def test_a_connector_request_runs_in_the_persons_zone(world):
    fake, local_day = late_evening()
    token = pat(world.u.pi, world.lab_a, access="write")
    call = {
        "name": "create_decision_draft",
        "arguments": {
            "lab_id": str(world.lab_a.pk),
            "project_id": str(world.p1.pk),
            "title": "Use the mixed model",
        },
    }
    with mock.patch("django.utils.timezone.now", return_value=fake):
        utc = data(rpc(token, "tools/call", call))
        set_zone(world.u.pi, EDMONTON)
        local = data(rpc(token, "tools/call", call))
    assert utc["created"]["decided_on"] == fake.date().isoformat()
    assert local["created"]["decided_on"] == local_day.isoformat()
    assert timezone.get_current_timezone_name() == "UTC"


def test_connector_results_show_times_in_the_persons_zone(world):
    set_zone(world.u.pi, EDMONTON)
    token = pat(world.u.pi, world.lab_a)
    args = {"lab_id": str(world.lab_a.pk), "task_id": str(world.a1.task.pk)}
    out = data(rpc(token, "tools/call", {"name": "get_task", "arguments": args}))
    assert out["created_at"].endswith(("-06:00", "-07:00")), out
    assert out["updates"][0]["at"].endswith(("-06:00", "-07:00"))


def test_every_canonical_zone_exists_in_postgres():
    from django.db import connection

    from core.middleware import _canonical

    with connection.cursor() as cur:
        cur.execute("SELECT name FROM pg_timezone_names")
        known = {row[0] for row in cur.fetchall()}
    assert set(_canonical().values()) <= known


def test_an_old_stored_zone_name_does_not_break_date_lookups(world):
    """Asia/Calcutta stored before names were canonical: SQL `AT TIME ZONE` would 500."""
    from labs.models import Meeting

    now = timezone.now()
    m = Meeting.objects.create(
        lab=world.lab_a,
        title="M",
        starts_at=now,
        ends_at=now + datetime.timedelta(hours=1),
        created_by=world.u.pi,
    )
    m.attendees.add(world.u.pi)
    set_zone(world.u.pi, "Asia/Calcutta")
    assert str(user_zone(world.u.pi)) == "Asia/Kolkata"
    c = Client(raise_request_exception=False)
    c.force_login(world.u.pi)
    base = f"/api/labs/{world.lab_a.pk}"
    assert c.get(f"{base}/contributions/").status_code == 200
    day = datetime.timedelta(days=1)
    resp = c.get(f"{base}/calendar/?from={now.date() - day}&to={now.date() + day}")
    assert resp.status_code == 200 and len(resp.json()) == 1


def test_a_bad_stored_zone_is_utc_not_an_error(world):
    for bad in ("America", "x" * 5000, ["UTC"]):
        set_zone(world.u.pi, bad)
        assert user_zone(world.u.pi) is datetime.UTC
    world.u.pi.preferences = "not a dict"
    assert user_zone(world.u.pi) is datetime.UTC


def test_an_extreme_date_is_refused_so_it_cannot_break_other_peoples_lists(world):
    set_zone(world.u.pi, EDMONTON)  # west of UTC, where year 1 overflows
    c = Client()
    c.force_login(world.u.pi)
    body = {"title": "M", "starts_at": "0001-01-01T00:00:00Z", "ends_at": "2026-01-01T00:00:00Z"}
    resp = c.post(f"/api/labs/{world.lab_a.pk}/calendar/meetings/", body, "application/json")
    assert resp.status_code == 400 and "starts_at" in resp.json()
    body = {"title": "M", "starts_at": "9999-12-31T23:59:00Z", "ends_at": "2026-01-01T00:00:00Z"}
    resp = c.post(f"/api/labs/{world.lab_a.pk}/calendar/meetings/", body, "application/json")
    assert resp.status_code == 400 and "starts_at" in resp.json()


def test_the_tool_encoder_survives_an_extreme_date():
    from assistant.tools import LocalTimeEncoder

    old = datetime.datetime(1, 1, 1, tzinfo=datetime.UTC)
    with timezone.override(zoneinfo.ZoneInfo(EDMONTON)):
        assert json.loads(json.dumps({"t": old}, cls=LocalTimeEncoder)) == {
            "t": "0001-01-01T00:00:00Z"
        }


def test_the_ai_spending_month_is_utc_whatever_the_zone():
    from assistant.ai import lab_keys

    fake = datetime.datetime(2026, 12, 1, 3, 0, tzinfo=datetime.UTC)  # still Nov 30 in Edmonton
    with (
        mock.patch("django.utils.timezone.now", return_value=fake),
        timezone.override(zoneinfo.ZoneInfo(EDMONTON)),
    ):
        assert lab_keys.this_month() == datetime.date(2026, 12, 1)


def test_two_saves_at_once_keep_both_preferences(world):
    """The second request's user object was read before the first save landed."""
    from rest_framework.test import APIClient

    from core.models import User

    stale = User.objects.get(pk=world.u.pi.pk)
    User.objects.filter(pk=stale.pk).update(preferences={"task_view": "list"})
    c = APIClient()
    c.force_authenticate(stale)
    resp = c.patch("/api/me/", {"preferences": {"time_zone": EDMONTON}}, format="json")
    assert resp.status_code == 200, resp.content
    stale.refresh_from_db()
    assert stale.preferences == {"task_view": "list", "time_zone": EDMONTON}
