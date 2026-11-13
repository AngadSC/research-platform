"""D291: dates follow each person's own time zone, as their browser reports it, on the site and
through the connector. 8:02 pm in Edmonton is already tomorrow in UTC."""

import datetime
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
    for name in (EDMONTON, "Asia/Calcutta", "UTC"):  # Chrome still reports the old Indian name
        resp = c.patch("/api/me/", {"preferences": {"time_zone": name}}, "application/json")
        assert resp.status_code == 200, resp.content
        assert resp.json()["preferences"]["time_zone"] == name
    for bad in ("Mars/Olympus", "../etc/passwd", "zone.tab", "", 5):
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
