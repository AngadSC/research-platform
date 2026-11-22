"""Zoom meetings with email guests: labbenchos mails them, Zoom never sees the addresses."""

import json

import pytest
from django.core import mail

from core.email import _render_and_send
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import zoom
from integrations.tests.fake import response
from integrations.tests.test_meetings_calendar import (
    EVENTS,
    api,
    configured,  # noqa: F401  (autouse fixture)
    connect_google,
    connect_zoom,
    meeting_body,
)
from labs.lab_calendar import _call_owner
from labs.models import Meeting

pytestmark = pytest.mark.django_db

ZOOM_NEW = f"{zoom.API}/users/me/meetings"
ZOOM_ONE = f"{zoom.API}/meetings/5"


@pytest.fixture
def mails(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "labs.admin_services.send_email",
        lambda template, to, context=None: sent.append((template, list(to), context)),
    )
    return sent


def zoom_meeting(transport, users, lab, **over):
    connect_zoom(transport, users["pi"], lab)
    transport.on("POST", ZOOM_NEW, response(201, {"id": 5, "join_url": "https://zoom.us/j/5"}))
    body = meeting_body(video="zoom", guests=["a@guest.example", "b@guest.example"], **over)
    r = api(users["pi"]).post(f"/api/labs/{lab.pk}/calendar/meetings/", body, "json")
    assert r.status_code == 201, r.content
    return r.json()


def test_zoom_guests_are_mailed_and_never_sent_to_zoom(transport, lab_users, mails):
    lab, users = lab_users
    made = zoom_meeting(transport, users, lab)
    [sent] = transport.sent("POST", ZOOM_NEW)
    assert "guest.example" not in json.dumps(sent["json"])
    [(template, to, ctx)] = mails
    assert (template, to) == ("meeting_guest_invite", ["a@guest.example", "b@guest.example"])
    assert ctx["join_url"] == "https://zoom.us/j/5" and ctx["title"] == "Weekly sync"
    assert ctx["starts_at"] == "Mon 04 Mar 2030, 15:00 UTC" and ctx["starts_iso"]
    assert "PRIVATE NOTES" not in json.dumps(ctx)
    assert made["guest_emails"] == ["a@guest.example", "b@guest.example"]


def test_changes_to_a_zoom_meeting_mail_the_right_guests(transport, lab_users, mails):
    lab, users = lab_users
    made = zoom_meeting(transport, users, lab)
    mails.clear()
    transport.on("PATCH", ZOOM_ONE, response(204))
    transport.on("DELETE", ZOOM_ONE, response(204))
    client, url = api(users["pi"]), f"/api/labs/{lab.pk}/calendar/meetings/{made['id']}/"

    assert client.patch(url, {"title": "Moved"}, "json").status_code == 200
    assert [(t, to) for t, to, _ in mails] == [
        ("meeting_guest_update", ["a@guest.example", "b@guest.example"])
    ]
    mails.clear()
    assert client.patch(url, {"notes": "only here"}, "json").status_code == 200
    assert mails == []

    mails.clear()  # b leaves, c arrives; the time is unchanged
    r = client.patch(url, {"guests": ["a@guest.example", "c@guest.example"]}, "json")
    assert r.status_code == 200, r.content
    assert sorted((t, tuple(to)) for t, to, _ in mails) == [
        ("meeting_guest_cancel", ("b@guest.example",)),
        ("meeting_guest_invite", ("c@guest.example",)),
    ]
    mails.clear()
    assert client.delete(url).status_code == 204
    assert [(t, to) for t, to, _ in mails] == [
        ("meeting_guest_cancel", ["a@guest.example", "c@guest.example"])
    ]


def test_meet_guests_get_googles_mail_and_none_from_us(transport, lab_users, mails):
    lab, users = lab_users
    connect_google(transport, users["pi"], lab)
    transport.on(
        "POST", EVENTS, response(200, {"id": "e", "hangoutLink": "https://meet.google.com/a-b-c"})
    )
    body = meeting_body(video="google_meet", guests=["a@guest.example"])
    r = api(users["pi"]).post(f"/api/labs/{lab.pk}/calendar/meetings/", body, "json")
    assert r.status_code == 201, r.content
    transport.on("PATCH", f"{EVENTS}/e", response(200, {}))
    transport.on("DELETE", f"{EVENTS}/e", response(204))
    url = f"/api/labs/{lab.pk}/calendar/meetings/{r.json()['id']}/"
    assert api(users["pi"]).patch(url, {"title": "Moved"}, "json").status_code == 200
    assert api(users["pi"]).delete(url).status_code == 204
    assert mails == []


def test_guests_with_a_pasted_link_are_refused(transport, lab_users, mails):
    lab, users = lab_users
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/",
        meeting_body(join_url="https://zoom.us/j/1", guests=["a@guest.example"]),
        "json",
    )
    assert r.status_code == 400
    assert r.json()["guests"] == "Inviting people by email needs a Google Meet or Zoom call."
    assert Meeting.objects.for_lab(lab).count() == 0 and mails == []


def test_the_guest_emails_render(settings):
    ctx = {
        "title": "Sync <b>",
        "starts_at": "Mon 04 Mar 2030, 15:00 UTC",
        "ends_at": "Mon 04 Mar 2030, 15:45 UTC",
        "join_url": "https://zoom.us/j/5",
        "organiser": "Pat",
        "lab_name": "Lab",
    }
    for name, word in (("invite", "Invitation"), ("update", "Updated"), ("cancel", "Cancelled")):
        mail.outbox.clear()
        _render_and_send(f"meeting_guest_{name}", "a@guest.example", ctx)
        [m] = mail.outbox
        assert m.subject.startswith(word) and "Sync <b>" in m.subject
        assert "Mon 04 Mar 2030, 15:00 UTC" in m.body


def test_the_call_owner_is_empty_once_the_organiser_disconnects(transport, lab_users, mails):
    lab, users = lab_users
    made = zoom_meeting(transport, users, lab)
    assert made["call_owner"] == str(users["pi"].pk)
    ConnectedAccount.objects.for_lab(lab).update(status=AccountStatus.REVOKED)
    assert _call_owner(Meeting.objects.for_lab(lab).get()) is None


def test_zoom_says_why_it_refused(transport, lab_users):
    lab, users = lab_users
    connect_zoom(transport, users["pi"], lab)
    transport.on(
        "POST", ZOOM_NEW, response(400, {"code": 300, "message": "  Invalid start time.  "})
    )
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="zoom"), "json"
    )
    assert r.status_code == 400
    assert r.json()["video"] == ["Zoom refused the change: Invalid start time."]
