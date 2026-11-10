"""Meetings, "my" calendar and the .ics feeds (D230, D231). Who reaches each endpoint is in
tests/test_permission_matrix.py; this covers what the matrix can't: what the rows and the feed
contain, and that a feed follows its owner's access at every fetch."""

import logging
import re
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from assistant.services import revoke_all
from assistant.tests.reauth import sign_in
from audit.models import AuditAction, AuditEvent
from core.models import User
from ethics.models import EthicsApproval
from labs import lab_calendar
from labs.models import CalendarFeedToken, LabMembership, LabRole, Meeting, hash_token
from projects.models import ProjectDeadline, ProjectMembership, ProjectRole, Task
from provenance.models import FundingRecord

pytestmark = pytest.mark.django_db

DAY = timezone.now().date() + timezone.timedelta(days=10)
SPAN = {"from": str(DAY), "to": str(DAY)}


def api(user):
    client = APIClient()
    sign_in(client, user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Feed Lab")
    users = {}
    for name, role in [("pi", LabRole.PI), ("member", LabRole.MEMBER), ("viewer", LabRole.VIEWER)]:
        users[name] = make_user()
        join(users[name], lab, role)
    mine = make_project(lab, "Mine")
    other = make_project(lab, "Other")
    ProjectMembership.objects.create(
        lab=lab, project=mine, user=users["member"], role=ProjectRole.CONTRIBUTOR
    )
    return lab, users, mine, other


def url(lab, tail):
    return f"/api/labs/{lab.pk}/{tail}"


def meeting_body(**over):
    return {
        "title": "Group meeting",
        "starts_at": "2030-06-15T14:00:00Z",
        "ends_at": "2030-06-15T15:00:00Z",
        **over,
    }


def make_meeting(lab, user, *attendees, **over):
    fields = {
        "title": "Private catch-up",
        "starts_at": f"{DAY}T14:00:00Z",
        "ends_at": f"{DAY}T15:00:00Z",
        **over,
    }
    meeting = Meeting.objects.create(lab=lab, created_by=user, **fields)
    meeting.attendees.set([user, *attendees])
    return meeting


def calendar(user, lab, **extra):
    return api(user).get(url(lab, "calendar/"), {**SPAN, **extra}).json()


# ---------------------------------------------------------------- meetings


def test_only_the_people_on_a_meeting_see_it_even_the_pi_does_not(world):
    lab, u, *_ = world
    make_meeting(lab, u["member"])
    assert [r["title"] for r in calendar(u["member"], lab)] == ["Private catch-up"]
    assert calendar(u["pi"], lab) == []


def test_making_a_meeting_puts_the_organiser_on_it_and_audits_it(world):
    lab, u, *_ = world
    client = api(u["member"])
    body = meeting_body(attendees=[str(u["viewer"].pk)], join_url="https://us02web.zoom.us/j/123")
    created = client.post(url(lab, "calendar/meetings/"), body, "json")
    assert created.status_code == 201
    assert set(created.json()["attendees"]) == {str(u["member"].pk), str(u["viewer"].pk)}
    AuditEvent.objects.get(action=AuditAction.MEETING_CREATED, lab=lab)


def test_an_edit_keeps_the_organiser_and_names_what_changed(world):
    lab, u, *_ = world
    meeting = make_meeting(lab, u["member"], u["viewer"])
    target = url(lab, f"calendar/meetings/{meeting.pk}/")
    response = api(u["member"]).patch(target, {"attendees": []}, "json")
    assert response.status_code == 200
    assert response.json()["attendees"] == [str(u["member"].pk)]
    event = AuditEvent.objects.get(action=AuditAction.MEETING_UPDATED, lab=lab)
    assert event.metadata == {"changed": ["attendees"]}


def test_someone_not_on_a_meeting_gets_404_to_change_it(world):
    lab, u, *_ = world
    meeting = make_meeting(lab, u["member"])
    target = url(lab, f"calendar/meetings/{meeting.pk}/")
    assert api(u["pi"]).patch(target, {"notes": "x"}, "json").status_code == 404


@pytest.mark.parametrize(
    ("link", "ok"),
    [
        ("https://zoom.us/j/1", True),
        ("https://uni.zoom.us/j/1?pwd=abc", True),
        ("https://meet.google.com/abc-defg-hij", True),
        ("", True),
        ("http://zoom.us/j/1", False),
        ("https://zoom.us.evil.example/j/1", False),
        ("https://evilzoom.us/j/1", False),
        ("https://zoom.us@evil.example/j/1", False),
        ("javascript:alert(1)", False),
    ],
)
def test_join_link_must_be_zoom_or_meet_over_https(world, link, ok):
    lab, u, *_ = world
    response = api(u["member"]).post(
        url(lab, "calendar/meetings/"), meeting_body(join_url=link), "json"
    )
    assert (response.status_code == 201) == ok, response.content
    if not ok:
        assert "join_url" in response.json()


def test_a_meeting_cannot_end_before_it_starts_or_include_outsiders(world, make_user):
    lab, u, *_ = world
    client = api(u["member"])
    backwards = meeting_body(ends_at="2030-06-15T13:00:00Z")
    assert client.post(url(lab, "calendar/meetings/"), backwards, "json").status_code == 400
    stranger = meeting_body(attendees=[str(make_user().pk)])
    response = client.post(url(lab, "calendar/meetings/"), stranger, "json")
    assert response.status_code == 400 and "attendees" in response.json()
    assert not Meeting.objects.for_lab(lab).exists()  # the refused save left nothing behind


# ---------------------------------------------------------------- my calendar


@pytest.fixture
def dated(world):
    lab, u, mine, other = world
    for project, tag in ((mine, "mine"), (other, "other")):
        ProjectDeadline.objects.create(lab=lab, project=project, title=f"D {tag}", due_date=DAY)
    Task.objects.create(
        lab=lab,
        project=mine,
        title="T assigned",
        due_date=DAY,
        assignee=u["member"],
        created_by=u["pi"],
    )
    Task.objects.create(
        lab=lab, project=mine, title="T unassigned", due_date=DAY, created_by=u["pi"]
    )
    return world


def test_my_calendar_is_my_meetings_tasks_and_project_deadlines_only(dated):
    lab, u, mine, _ = dated
    make_meeting(lab, u["member"], title="Stand-up")
    FundingRecord.objects.create(
        lab=lab, project=mine, funder="F", end_date=DAY, status="active", created_by=u["pi"]
    )
    titles = {r["title"] for r in calendar(u["member"], lab, mine="true")}
    assert titles == {"Stand-up", "T assigned", "D mine"}


def test_a_pi_only_gets_deadlines_of_projects_they_are_on_in_my_calendar(dated):
    lab, u, *_ = dated
    assert calendar(u["pi"], lab, mine="true") == []
    assert {"D mine", "D other"} <= {r["title"] for r in calendar(u["pi"], lab)}


# ---------------------------------------------------------------- the .ics feed


def feed_url():
    return reverse("labs:calendar-ics")


def get_feed(token, **extra):
    return APIClient().get(feed_url(), {"token": token, **extra})


def issue(user, lab):
    response = api(user).post(url(lab, "calendar/feed/"), {}, "json")
    assert response.status_code == 201
    return response.json()["token"]


def add_funding(lab, project, user):
    FundingRecord.objects.create(
        lab=lab,
        project=project,
        funder="Secret Funder",
        end_date=DAY,
        status="active",
        created_by=user,
    )


def test_token_is_unguessable_hashed_and_kept_out_of_the_audit_log(world):
    lab, u, *_ = world
    token = issue(u["member"], lab)
    assert len(token) >= 43
    row = CalendarFeedToken.objects.for_lab(lab).get(user=u["member"])
    assert row.token_hash == hash_token(token) and token not in row.token_hash
    event = AuditEvent.objects.get(action=AuditAction.CALENDAR_FEED_CREATED, lab=lab)
    assert token not in f"{event.metadata} {event.target_repr}"
    status = api(u["member"]).get(url(lab, "calendar/feed/")).json()
    assert status["active"] is True and "token" not in status


def test_feed_is_text_calendar_for_a_calendar_apps_accept_header(world):
    lab, u, *_ = world
    response = APIClient().get(
        feed_url(), {"token": issue(u["pi"], lab)}, HTTP_ACCEPT="text/calendar"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar; charset=utf-8"
    assert response["Cache-Control"] == "private, no-store"
    assert response.content.startswith(b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")


def test_missing_and_unknown_tokens_get_nothing(world):
    assert APIClient().get(feed_url()).status_code == 401
    assert get_feed("not-a-real-token").status_code == 401


def test_a_session_alone_does_not_open_a_feed(world):
    lab, u, *_ = world
    issue(u["pi"], lab)
    assert api(u["pi"]).get(feed_url()).status_code == 401


def test_revoking_stops_the_link_at_once(world):
    lab, u, *_ = world
    token = issue(u["member"], lab)
    assert get_feed(token).status_code == 200
    assert api(u["member"]).delete(url(lab, "calendar/feed/")).status_code == 204
    assert get_feed(token).status_code == 401
    AuditEvent.objects.get(action=AuditAction.CALENDAR_FEED_REVOKED, lab=lab)


def test_a_new_link_replaces_the_old_one(world):
    lab, u, *_ = world
    first = issue(u["member"], lab)
    second = issue(u["member"], lab)
    assert first != second
    assert get_feed(first).status_code == 401
    assert get_feed(second).status_code == 200


def test_making_a_link_needs_a_recent_sign_in(world):
    lab, u, *_ = world
    u["member"].set_password("Correct-horse-1")
    u["member"].save()
    client = APIClient()
    sign_in(client, u["member"], seconds_ago=3600, reauthenticated=False)
    assert client.post(url(lab, "calendar/feed/"), {}, "json").status_code == 401


def test_feed_follows_the_owner_being_demoted_at_the_next_fetch(world):
    lab, u, mine, _ = world
    add_funding(lab, mine, u["pi"])
    token = issue(u["pi"], lab)
    assert b"Secret Funder" in get_feed(token).content
    LabMembership.objects.for_lab(lab).filter(user=u["pi"]).update(role=LabRole.LAB_ADMIN)
    response = get_feed(token)
    assert response.status_code == 200 and b"Secret Funder" not in response.content


def test_feed_shows_funding_only_to_pis(world):
    lab, u, mine, _ = world
    add_funding(lab, mine, u["pi"])
    assert b"Secret Funder" not in get_feed(issue(u["member"], lab)).content


def test_feed_never_holds_a_hidden_project_or_restricted_ethics(world):
    lab, u, mine, other = world
    ProjectDeadline.objects.create(lab=lab, project=other, title="Hidden deadline", due_date=DAY)
    ProjectDeadline.objects.create(lab=lab, project=mine, title="Seen deadline", due_date=DAY)
    EthicsApproval.objects.create(
        lab=lab,
        approval_number="E9",
        board="B",
        title="Restricted one",
        approval_date="2025-01-01",
        expiry_date=DAY,
        restricted=True,
        created_by=u["pi"],
    ).projects.add(other)
    body = get_feed(issue(u["member"], lab)).content
    assert b"Seen deadline" in body
    assert b"Hidden deadline" not in body and b"Restricted one" not in body


def test_feed_stops_when_the_owner_leaves_the_lab_and_is_scoped_to_its_lab(
    world, make_lab, make_project, join
):
    lab, u, mine, _ = world
    ProjectDeadline.objects.create(lab=lab, project=mine, title="Lab A only", due_date=DAY)
    token = issue(u["member"], lab)
    other_lab = make_lab("Other Lab")
    join(u["member"], other_lab, LabRole.PI)
    ProjectDeadline.objects.create(
        lab=other_lab, project=make_project(other_lab, "B"), title="Lab B item", due_date=DAY
    )
    assert b"Lab B item" not in get_feed(token).content
    LabMembership.objects.for_lab(lab).filter(user=u["member"]).delete()
    assert get_feed(token).status_code == 404


def test_security_events_and_deactivation_end_every_feed(world):
    lab, u, *_ = world
    token = issue(u["member"], lab)
    revoke_all(u["member"], reason="password_changed")
    assert get_feed(token).status_code == 401
    event = AuditEvent.objects.get(action=AuditAction.CALENDAR_FEED_REVOKED, lab=lab)
    assert event.actor_id is None and event.actor_label == "security:password_changed"

    pi_token = issue(u["pi"], lab)
    pi = User.objects.get(pk=u["pi"].pk)
    pi.is_active = False
    pi.save()
    assert get_feed(pi_token).status_code in (401, 404)


def test_feed_token_is_not_written_to_the_app_log(world, caplog):
    lab, u, *_ = world
    token = issue(u["member"], lab)
    with caplog.at_level(logging.DEBUG):
        get_feed(token)
        get_feed(token + "x")
    assert token not in caplog.text


@pytest.mark.parametrize("path", ["/deploy/docker-compose.prod.yml", "Dockerfile.prod"])
def test_production_access_log_drops_query_strings(path):
    """The token is in the query string, so an access log format with it would leak every token."""
    text = Path(path).read_text(encoding="utf-8")
    fmt = re.search(r'"--access-logformat", "(.*?)"\]', text).group(1)
    assert "%(U)s" in fmt
    assert not {"%(r)s", "%(q)s", "%(f)s"} & set(re.findall(r"%\(\w+\)s", fmt))


def test_ics_escapes_folds_and_ends_all_day_events_the_next_day():
    id_ = "00000000-0000-0000-0000-000000000001"
    item = {
        "kind": "deadline",
        "id": id_,
        "title": 'Long; tricky, title\\é "' + "x" * 80 + "\nsecond",
        "date": timezone.datetime(2030, 6, 30).date(),
        "end_date": None,
        "project_name": None,
        "done": False,
        "starts_at": None,
        "ends_at": None,
        "join_url": "",
    }
    done = {**item, "id": "done", "title": "Finished", "done": True}
    text = lab_calendar.render_ics("Lab", [item, done])
    assert "Finished" not in text
    assert text.endswith("END:VCALENDAR\r\n")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    joined = text.replace("\r\n ", "")
    assert "SUMMARY:Long\\; tricky\\, title\\\\é" in joined
    assert "\\nsecond" in joined and "\nsecond" not in joined
    assert "DTSTART;VALUE=DATE:20300630\r\n" in joined
    assert "DTEND;VALUE=DATE:20300701\r\n" in joined


def test_a_meeting_in_the_feed_is_timed_in_utc_with_its_join_link(world):
    lab, u, *_ = world
    make_meeting(
        lab,
        u["member"],
        title="Zoom catch-up",
        starts_at=f"{DAY}T14:00:00-03:00",
        ends_at=f"{DAY}T15:30:00-03:00",
        join_url="https://zoom.us/j/99",
    )
    body = get_feed(issue(u["member"], lab)).content.decode().replace("\r\n ", "")
    assert f"DTSTART:{DAY:%Y%m%d}T170000Z" in body
    assert f"DTEND:{DAY:%Y%m%d}T183000Z" in body
    assert "https://zoom.us/j/99" in body
