"""Google Meet and Zoom calls, and Google Calendar both ways (D253 to D256). Every Google and Zoom
call goes through the patched HTTP layer; nothing leaves the process."""

import base64
import datetime
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from rest_framework.test import APIClient

from integrations import registry, services
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_calendar, google_drive, zoom
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response
from labs.models import GoogleCalendarSync, Meeting, SyncedEvent
from projects.models import ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db

GCAL = google_calendar.API
EVENTS = f"{GCAL}/calendars/primary/events"
SCOPES = " ".join(registry.bundle_scopes(google_calendar.PROVIDER))  # D262: one Google sign-in
ZOOM_SCOPES = " ".join(zoom.PROVIDER.scopes)
START = datetime.datetime(2030, 3, 4, 15, 0, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
        "zoom": {"client_id": "zm-client", "client_secret": "zm-secret"},
    }


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def connect_google(transport, user, lab, email="pi@uni.edu"):
    request = make_request(user)
    url = services.start_connect(request, lab, "google_calendar")
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on("POST", google_calendar.PROVIDER.token_url, token_reply("g-at", "g-rt", SCOPES))
    transport.on(  # D264: one answer names the account for Drive and for Calendar
        "GET",
        google_drive.PROVIDER.identity_url,
        response(200, {"user": {"permissionId": "perm-" + email, "emailAddress": email}}),
    )
    return services.complete_connect(request, state=state, code="code")


def connect_zoom(transport, user, lab):
    request = make_request(user)
    url = services.start_connect(request, lab, "zoom")
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on("POST", zoom.PROVIDER.token_url, token_reply("z-at", "z-rt", ZOOM_SCOPES))
    transport.on(
        "GET", zoom.PROVIDER.identity_url, response(200, {"id": "zu1", "email": "pi@uni.edu"})
    )
    return services.complete_connect(request, state=state, code="code")


def meeting_body(**over):
    return {
        "title": "Weekly sync",
        "starts_at": START.isoformat(),
        "ends_at": (START + datetime.timedelta(minutes=45)).isoformat(),
        "notes": "PRIVATE NOTES",
        **over,
    }


# ---------------------------------------------------------------- connecting


def test_zoom_sends_its_app_credentials_as_basic_auth(transport, lab_users):
    lab, users = lab_users
    account = connect_zoom(transport, users["pi"], lab)
    assert account.status == AccountStatus.ACTIVE
    [sent] = transport.sent("POST", zoom.PROVIDER.token_url)
    pair = base64.b64encode(b"zm-client:zm-secret").decode()
    assert sent["headers"]["Authorization"] == f"Basic {pair}"
    assert "client_secret" not in sent["data"]


def test_google_calendar_connects_with_only_its_two_event_scopes(transport, lab_users):
    lab, users = lab_users
    account = connect_google(transport, users["pi"], lab)
    assert set(account.granted_scopes) == set(google_calendar.PROVIDER.scopes)
    assert all("calendar." in s for s in account.granted_scopes)


# ---------------------------------------------------------------- one Google sign-in (D262)


def accounts_of(lab, user):
    rows = ConnectedAccount.objects.for_lab(lab).filter(user=user)
    return {r.provider: r for r in rows}


def test_one_google_sign_in_connects_drive_calendar_and_meet(transport, lab_users):
    lab, users = lab_users
    start = services.start_connect(make_request(users["pi"]), lab, "google_calendar")
    asked = set(parse_qs(urlsplit(start).query)["scope"][0].split())
    assert asked == set(SCOPES.split())
    assert "https://www.googleapis.com/auth/drive.file" in asked  # one consent for all of it

    connect_google(transport, users["pi"], lab)
    rows = accounts_of(lab, users["pi"])
    assert set(rows) == {"google_drive", "google_calendar"}
    assert all(r.status == AccountStatus.ACTIVE for r in rows.values())
    # each service keeps only its own scopes and names the account the way it does
    assert set(rows["google_drive"].granted_scopes) == set(google_drive.PROVIDER.scopes)
    assert set(rows["google_calendar"].granted_scopes) == set(google_calendar.PROVIDER.scopes)
    assert rows["google_calendar"].external_account_id == "pi@uni.edu"
    assert rows["google_drive"].external_account_id == "perm-pi@uni.edu"
    assert rows["google_drive"].access_token() == rows["google_calendar"].access_token()


def test_connecting_from_drive_gives_calendar_and_meet_too(transport, lab_users):
    lab, users = lab_users
    request = make_request(users["pi"])
    url = services.start_connect(request, lab, "google_drive")
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on("POST", google_drive.PROVIDER.token_url, token_reply("t", "r", SCOPES))
    transport.on(
        "GET",
        google_drive.PROVIDER.identity_url,
        response(200, {"user": {"permissionId": "p9", "emailAddress": "pi@uni.edu"}}),
    )
    account = services.complete_connect(request, state=state, code="code")
    assert account.provider == "google_drive"  # the one that was asked for comes back
    assert set(accounts_of(lab, users["pi"])) == {"google_drive", "google_calendar"}


def test_google_must_grant_everything_asked_or_nothing_is_stored(transport, lab_users):
    lab, users = lab_users
    request = make_request(users["pi"])
    url = services.start_connect(request, lab, "google_calendar")
    state = parse_qs(urlsplit(url).query)["state"][0]
    only_drive = "https://www.googleapis.com/auth/drive.file"  # the person unticked Calendar
    transport.on("POST", google_calendar.PROVIDER.token_url, token_reply("t", "r", only_drive))
    with pytest.raises(services.OAuthError) as err:
        services.complete_connect(request, state=state, code="code")
    assert err.value.code == "scope_not_granted"
    assert accounts_of(lab, users["pi"]) == {}


def test_a_refresh_returning_the_whole_grant_keeps_both_accounts_working(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    for name, row in accounts_of(lab, users["pi"]).items():
        transport.on(
            "POST",
            google_drive.PROVIDER.token_url,
            token_reply(f"fresh-{name}", None, SCOPES),  # Google names the whole grant
        )
        services.refresh_access_token(row)
        row.refresh_from_db()
        assert row.status == AccountStatus.ACTIVE and row.access_token() == f"fresh-{name}"
        assert set(row.granted_scopes) == set(registry.PROVIDERS[name].scopes)


def test_disconnecting_one_disconnects_the_whole_google_sign_in(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    transport.on("POST", google_drive.PROVIDER.revoke_url, response(200, {}))
    services.disconnect(accounts_of(lab, users["pi"])["google_calendar"], actor=users["pi"])
    rows = accounts_of(lab, users["pi"])
    assert {r.status for r in rows.values()} == {AccountStatus.REVOKED}
    assert all(not r.access_token_ct and not r.refresh_token_ct for r in rows.values())
    assert len(transport.sent("POST", google_drive.PROVIDER.revoke_url)) == 1  # revoked once


def test_another_persons_google_is_not_disconnected(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab, email="pi@uni.edu")
    connect_google(transport, users["member"], lab, email="m@uni.edu")
    transport.on("POST", google_drive.PROVIDER.revoke_url, response(200, {}))
    services.disconnect(accounts_of(lab, users["pi"])["google_drive"], actor=users["pi"])
    assert {r.status for r in accounts_of(lab, users["member"]).values()} == {AccountStatus.ACTIVE}


def test_a_provider_sharing_a_grant_must_share_one_google_app():
    assert google_calendar.PROVIDER.client() == google_drive.PROVIDER.client()
    assert set(google_drive.PROVIDER.bundle) == {"google_calendar"}
    assert set(google_calendar.PROVIDER.bundle) == {"google_drive"}


# ---------------------------------------------------------------- calls on meetings (D254)


def test_a_meet_meeting_gets_its_link_from_google_and_never_sends_notes(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    transport.on(
        "POST",
        EVENTS,
        response(200, {"id": "ev1", "hangoutLink": "https://meet.google.com/abc-defg-hij"}),
    )
    body = meeting_body(video="google_meet", attendees=[str(users["member"].pk)])
    r = api(users["pi"]).post(f"/api/labs/{lab.pk}/calendar/meetings/", body, "json")
    assert r.status_code == 201, r.content
    assert r.json()["join_url"] == "https://meet.google.com/abc-defg-hij"
    assert r.json()["video_provider"] == "google_meet"
    assert r.json()["call_owner"] == str(users["pi"].pk)
    [sent] = transport.sent("POST", EVENTS)
    assert sent["params"] == {"conferenceDataVersion": 1, "sendUpdates": "none"}
    assert "PRIVATE NOTES" not in json.dumps(sent["json"])
    assert {a["email"] for a in sent["json"]["attendees"]} == {
        users["pi"].email,
        users["member"].email,
    }


def test_a_meeting_needs_the_account_connected_first(transport, lab_users):
    lab, users = lab_users
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="zoom"), "json"
    )
    assert r.status_code == 400 and "Connect Zoom" in r.json()["video"][0]
    assert Meeting.objects.for_lab(lab).count() == 0


def test_when_google_refuses_nothing_is_kept_here(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    transport.on("POST", EVENTS, response(403, {"error": {}}))
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="google_meet"), "json"
    )
    assert r.status_code == 400
    assert Meeting.objects.for_lab(lab).count() == 0


def test_a_zoom_meeting_changes_and_is_removed_through_zoom(transport, lab_users):
    lab, users = lab_users
    connect_zoom(transport, users["pi"], lab)
    transport.on(
        "POST",
        f"{zoom.API}/users/me/meetings",
        response(201, {"id": 8812, "join_url": "https://us05web.zoom.us/j/8812?pwd=x"}),
    )
    client = api(users["pi"])
    r = client.post(f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="zoom"), "json")
    assert r.status_code == 201, r.content
    assert r.json()["join_url"].startswith("https://us05web.zoom.us/j/8812")
    sent = transport.sent("POST", f"{zoom.API}/users/me/meetings")[0]["json"]
    assert sent["duration"] == 45 and "agenda" not in sent

    url = f"/api/labs/{lab.pk}/calendar/meetings/{r.json()['id']}/"
    transport.on("PATCH", f"{zoom.API}/meetings/8812", response(204))
    assert client.patch(url, {"title": "Moved"}, "json").status_code == 200
    assert transport.sent("PATCH", f"{zoom.API}/meetings/8812")[0]["json"]["topic"] == "Moved"
    assert client.patch(url, {"notes": "only here"}, "json").status_code == 200
    assert len(transport.sent("PATCH", f"{zoom.API}/meetings/8812")) == 1  # notes stay here

    transport.on("DELETE", f"{zoom.API}/meetings/8812", response(204))
    assert client.delete(url).status_code == 204
    assert Meeting.objects.for_lab(lab).count() == 0


def test_only_the_person_whose_account_holds_the_call_can_change_it(transport, lab_users):
    lab, users = lab_users
    connect_zoom(transport, users["pi"], lab)
    transport.on(
        "POST",
        f"{zoom.API}/users/me/meetings",
        response(201, {"id": 1, "join_url": "https://zoom.us/j/1"}),
    )
    body = meeting_body(video="zoom", attendees=[str(users["member"].pk)])
    meeting_id = api(users["pi"]).post(f"/api/labs/{lab.pk}/calendar/meetings/", body, "json")
    url = f"/api/labs/{lab.pk}/calendar/meetings/{meeting_id.json()['id']}/"
    member = api(users["member"])
    assert member.patch(url, {"title": "Mine now"}, "json").status_code == 403
    assert member.delete(url).status_code == 403
    assert Meeting.objects.for_lab(lab).get().title == "Weekly sync"


def test_a_disconnected_organiser_leaves_a_plain_meeting(transport, lab_users):
    lab, users = lab_users
    account = connect_zoom(transport, users["pi"], lab)
    transport.on(
        "POST",
        f"{zoom.API}/users/me/meetings",
        response(201, {"id": 1, "join_url": "https://zoom.us/j/1"}),
    )
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/",
        meeting_body(video="zoom", attendees=[str(users["member"].pk)]),
        "json",
    )
    ConnectedAccount.objects.for_lab(lab).filter(pk=account.pk).update(status=AccountStatus.REVOKED)
    url = f"/api/labs/{lab.pk}/calendar/meetings/{r.json()['id']}/"
    assert api(users["member"]).patch(url, {"title": "Ours"}, "json").status_code == 200
    assert transport.sent("PATCH", f"{zoom.API}/meetings/1") == []


# ---------------------------------------------------------------- Google into the app (D256)


def test_your_google_events_are_shown_to_you_only_and_app_meets_left_out(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    Meeting.objects.create(
        lab=lab,
        title="Made here",
        starts_at=START,
        ends_at=START + datetime.timedelta(hours=1),
        created_by=users["pi"],
        video_provider="google_meet",
        external_id="made-here",
        video_account=ConnectedAccount.objects.for_lab(lab).get(provider="google_calendar"),
    )
    items = [
        {
            "id": "g1",
            "summary": "Dentist",
            "start": {"dateTime": "2030-03-05T09:00:00Z"},
            "end": {"dateTime": "2030-03-05T10:00:00Z"},
            "htmlLink": "https://www.google.com/calendar/event?eid=g1",
        },
        {
            "id": "g2",
            "summary": "Holiday",
            "start": {"date": "2030-03-06"},
            "end": {"date": "2030-03-09"},
        },
        {"id": "g3", "status": "cancelled", "start": {"date": "2030-03-07"}},
        {"id": "made-here", "summary": "dup", "start": {"date": "2030-03-04"}},
        {
            "id": "g4",
            "summary": "Bad link",
            "start": {"date": "2030-03-08"},
            "htmlLink": "https://evil.example/x",
        },
    ]
    transport.on("GET", EVENTS, response(200, {"items": items}))
    q = {"from": "2030-03-01", "to": "2030-03-31"}
    rows = api(users["pi"]).get(f"/api/labs/{lab.pk}/calendar/google/events/", q).json()
    assert [r["title"] for r in rows] == ["Dentist", "Holiday", "Bad link"]
    assert rows[1]["date"] == "2030-03-06" and rows[1]["end_date"] == "2030-03-08"
    assert rows[2]["url"] == ""  # only Google's own address becomes a link
    assert api(users["member"]).get(f"/api/labs/{lab.pk}/calendar/google/events/", q).json() == []


def test_switching_google_events_off_stops_reading_them(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    client = api(users["pi"])
    assert (
        client.patch(
            f"/api/labs/{lab.pk}/calendar/google/", {"show_google_events": False}, "json"
        ).json()["show_google_events"]
        is False
    )
    q = {"from": "2030-03-01", "to": "2030-03-31"}
    assert client.get(f"/api/labs/{lab.pk}/calendar/google/events/", q).json() == []
    assert transport.sent("GET", EVENTS) == []


# ---------------------------------------------------------------- the app into Google (D255)


@pytest.fixture
def pushing(transport, lab_users, make_project, monkeypatch):
    lab, users = lab_users
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda: datetime.date(2030, 3, 1))
    project = make_project(lab, "Sleep")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["member"], role=ProjectRole.CONTRIBUTOR
    )
    task = Task.objects.create(
        lab=lab,
        project=project,
        title="Clean data",
        created_by=users["member"],
        assignee=users["member"],
        due_date=datetime.date(2030, 3, 10),
        description="SECRET TASK TEXT",
    )
    connect_google(transport, users["member"], lab, email="m@uni.edu")
    transport.on("POST", f"{GCAL}/calendars", response(200, {"id": "appcal@group"}))
    return lab, users, task


def run_sync(user, lab):
    return api(user).post(f"/api/labs/{lab.pk}/calendar/google/sync/").json()


def test_sync_adds_changes_and_removes_your_items_in_the_apps_own_calendar(transport, pushing):
    lab, users, task = pushing
    events = f"{GCAL}/calendars/appcal%40group/events"
    transport.on("POST", events, response(200, {"id": "pushed1"}))
    out = run_sync(users["member"], lab)
    assert (out["added"], out["changed"], out["removed"], out["last_error"]) == (1, 0, 0, "")
    [sent] = transport.sent("POST", events)
    assert sent["json"]["summary"] == "Clean data (Sleep)"
    assert sent["json"]["start"] == {"date": "2030-03-10"}
    assert "SECRET TASK TEXT" not in json.dumps(sent["json"])

    assert run_sync(users["member"], lab)["added"] == 0  # nothing changed: no calls
    assert len(transport.sent("POST", events)) == 1

    Task.objects.for_lab(lab).filter(pk=task.pk).update(title="Clean the data")
    transport.on("PATCH", f"{events}/pushed1", response(200, {"id": "pushed1"}))
    assert run_sync(users["member"], lab)["changed"] == 1

    Task.objects.for_lab(lab).filter(pk=task.pk).update(status="done")
    transport.on("DELETE", f"{events}/pushed1", response(204))
    assert run_sync(users["member"], lab)["removed"] == 1
    assert SyncedEvent.objects.for_lab(lab).count() == 0


def test_turning_a_kind_off_removes_it_from_google(transport, pushing):
    lab, users, _ = pushing
    events = f"{GCAL}/calendars/appcal%40group/events"
    transport.on("POST", events, response(200, {"id": "pushed1"}))
    run_sync(users["member"], lab)
    api(users["member"]).patch(
        f"/api/labs/{lab.pk}/calendar/google/", {"push_tasks": False}, "json"
    )
    transport.on("DELETE", f"{events}/pushed1", response(204))
    assert run_sync(users["member"], lab)["removed"] == 1


def test_a_calendar_deleted_in_google_is_made_again(transport, pushing):
    lab, users, _ = pushing
    events = f"{GCAL}/calendars/appcal%40group/events"
    transport.on("POST", events, response(404, {}))
    transport.on("GET", events, response(404, {}))
    out = run_sync(users["member"], lab)
    assert out["last_error"]
    assert GoogleCalendarSync.objects.for_lab(lab).get().app_calendar_id == ""
    transport.on("POST", f"{GCAL}/calendars", response(200, {"id": "newcal"}))
    transport.on("POST", f"{GCAL}/calendars/newcal/events", response(200, {"id": "p2"}))
    assert run_sync(users["member"], lab)["added"] == 1


def test_the_scheduled_run_skips_people_who_push_nothing(transport, pushing):
    from labs import video_calendar

    lab, users, _ = pushing
    api(users["member"]).patch(
        f"/api/labs/{lab.pk}/calendar/google/",
        {"push_tasks": False, "push_deadlines": False, "push_meetings": False},
        "json",
    )
    assert video_calendar.push_all() == 0
    assert transport.sent("POST", f"{GCAL}/calendars") == []


def test_video_options_say_what_you_can_make(transport, lab_users):
    lab, users = lab_users
    url = f"/api/labs/{lab.pk}/calendar/video-options/"
    assert api(users["pi"]).get(url).json() == {
        "google_meet": False,
        "zoom": False,
        "google_meet_available": True,
        "zoom_available": True,
    }
    connect_zoom(transport, users["pi"], lab)
    assert api(users["pi"]).get(url).json()["zoom"] is True


# ---------------------------------------------------------------- the account lookup (D264)


def test_connecting_never_reads_the_primary_calendar_record(transport, lab_users):
    """Our scopes cannot read `calendars/primary` itself, so naming the account must not use it:
    asking for it made Google refuse and the connect fail."""
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    asked = [u for _, u, _ in transport.calls]
    assert not [u for u in asked if u.rstrip("/").endswith("/calendars/primary")]
    rows = accounts_of(lab, users["pi"])
    assert rows["google_calendar"].external_email == "pi@uni.edu"
    assert rows["google_calendar"].external_account_id == "pi@uni.edu"


def test_calendar_account_falls_back_to_the_permission_id_without_an_email(transport, lab_users):
    lab, users = lab_users
    request = make_request(users["pi"])
    state = parse_qs(urlsplit(services.start_connect(request, lab, "google_calendar")).query)[
        "state"
    ][0]
    transport.on("POST", google_calendar.PROVIDER.token_url, token_reply("t", "r", SCOPES))
    transport.on(
        "GET", google_drive.PROVIDER.identity_url, response(200, {"user": {"permissionId": "p77"}})
    )
    services.complete_connect(request, state=state, code="code")
    assert accounts_of(lab, users["pi"])["google_calendar"].external_account_id == "p77"


@pytest.mark.parametrize("status", [401, 403])
def test_google_refusing_to_name_the_account_says_so_and_stores_nothing(
    transport, lab_users, status
):
    lab, users = lab_users
    request = make_request(users["pi"])
    state = parse_qs(urlsplit(services.start_connect(request, lab, "google_calendar")).query)[
        "state"
    ][0]
    transport.on("POST", google_calendar.PROVIDER.token_url, token_reply("t", "r", SCOPES))
    transport.on("GET", google_drive.PROVIDER.identity_url, response(status, {"error": {}}))
    with pytest.raises(services.OAuthError) as err:
        services.complete_connect(request, state=state, code="code")
    assert err.value.code == "identity_forbidden"
    assert accounts_of(lab, users["pi"]) == {}


def test_a_calendar_api_that_is_not_switched_on_is_named_not_hidden(transport, lab_users):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    off = {"error": {"errors": [{"reason": "accessNotConfigured"}], "code": 403}}
    transport.on("POST", EVENTS, response(403, off))
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="google_meet"), "json"
    )
    assert r.status_code == 400
    assert "enable the Calendar API" in r.json()["video"][0]
    assert Meeting.objects.for_lab(lab).count() == 0
