"""Zoom's event webhook (app deauthorization), and what disconnecting Zoom keeps and clears."""

import base64
import hashlib
import hmac
import json
import time
from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from integrations import services
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import zoom
from integrations.tests.fake import response
from integrations.tests.test_meetings_calendar import connect_google, connect_zoom, meeting_body
from labs.models import Meeting

pytestmark = pytest.mark.django_db

URL = "/api/integrations/zoom/events/"
SECRET = "zoom-secret-token"


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_ZOOM_WEBHOOK_SECRET = SECRET
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
        "zoom": {"client_id": "zm-client", "client_secret": "zm-secret"},
    }


def post(event, payload, *, stamp=None, secret=SECRET, signature=None):
    body = json.dumps({"event": event, "payload": payload})
    stamp = str(int(time.time()) if stamp is None else stamp)
    sig = (
        signature
        or "v0="
        + hmac.new(secret.encode(), f"v0:{stamp}:{body}".encode(), hashlib.sha256).hexdigest()
    )
    return APIClient(enforce_csrf_checks=True).post(
        URL,
        body,
        content_type="application/json",
        headers={"x-zm-request-timestamp": stamp, "x-zm-signature": sig},
    )


def deauth(user_id="zu1", client_id="zm-client", **kw):
    return post(
        "app_deauthorized", {"user_id": user_id, "account_id": "a", "client_id": client_id}, **kw
    )


def test_unset_secret_is_404(settings):
    settings.INTEGRATION_ZOOM_WEBHOOK_SECRET = ""
    assert deauth().status_code == 404


def test_bad_or_stale_signature_does_nothing(transport, lab_users):
    lab, users = lab_users
    account = connect_zoom(transport, users["pi"], lab)
    assert deauth(secret="wrong").status_code == 401
    assert deauth(signature="v0=00").status_code == 401
    assert deauth(stamp=int(time.time()) - 301).status_code == 401
    assert deauth(stamp="soon").status_code == 401
    account.refresh_from_db()
    assert account.status == AccountStatus.ACTIVE


def test_url_validation_answers_with_the_encrypted_token():
    r = post("endpoint.url_validation", {"plainToken": "abc"})
    assert r.status_code == 200
    assert r.json() == {
        "plainToken": "abc",
        "encryptedToken": hmac.new(SECRET.encode(), b"abc", hashlib.sha256).hexdigest(),
    }


def test_deauthorized_retires_only_the_right_rows(transport, lab_users):
    lab, users = lab_users
    mine = connect_zoom(transport, users["pi"], lab)
    other_user = connect_zoom(transport, users["lab_admin"], lab)
    ConnectedAccount.objects.for_lab(lab).filter(pk=other_user.pk).update(external_account_id="zu2")
    google = connect_google(transport, users["member"], lab)
    ConnectedAccount.objects.for_lab(lab).filter(pk=google.pk).update(external_account_id="zu1")
    assert deauth(client_id="someone-else").status_code == 200
    mine.refresh_from_db()
    assert mine.status == AccountStatus.ACTIVE  # another client's event
    assert deauth("zu1").status_code == 200
    mine.refresh_from_db()
    other_user.refresh_from_db()
    google.refresh_from_db()
    assert mine.status == AccountStatus.REVOKED
    assert (mine.external_email, mine.granted_scopes) == ("", [])
    assert mine.external_account_id == services.retired_id("zu1")
    assert other_user.status == AccountStatus.ACTIVE
    assert google.status == AccountStatus.ACTIVE  # same id, another provider
    assert transport.sent("POST", zoom.PROVIDER.revoke_url) == []  # the grant is already gone
    event = AuditEvent.objects.get(action=AuditAction.INTEGRATION_REVOKED)
    assert event.actor is None and event.lab_id == lab.pk


def test_deauthorized_also_retires_expired_and_error_rows(transport, lab_users):
    lab, users = lab_users
    a = connect_zoom(transport, users["pi"], lab)
    b = connect_zoom(transport, users["lab_admin"], lab)
    ConnectedAccount.objects.for_lab(lab).filter(pk=b.pk).update(external_account_id="zu1")
    ConnectedAccount.objects.for_lab(lab).filter(pk=a.pk).update(status=AccountStatus.EXPIRED)
    ConnectedAccount.objects.for_lab(lab).filter(pk=b.pk).update(status=AccountStatus.ERROR)
    assert deauth("zu1").status_code == 200
    for row in (a, b):
        row.refresh_from_db()
        assert row.status == AccountStatus.REVOKED


def test_a_payload_that_is_not_an_object_is_a_400():
    assert post("app_deauthorized", ["x"]).status_code == 400


def test_other_events_are_acknowledged(transport, lab_users):
    assert post("meeting.started", {"x": 1}).status_code == 200


def test_disconnect_revokes_with_basic_auth_clears_and_keeps_meetings(transport, lab_users):
    lab, users = lab_users
    account = connect_zoom(transport, users["pi"], lab)
    transport.on(
        "POST",
        f"{zoom.API}/users/me/meetings",
        response(201, {"id": 77, "join_url": "https://zoom.us/j/77"}),
    )
    client = APIClient()
    client.force_login(users["pi"])
    r = client.post(f"/api/labs/{lab.pk}/calendar/meetings/", meeting_body(video="zoom"), "json")
    assert r.status_code == 201
    transport.on("POST", zoom.PROVIDER.revoke_url, response(200, {}))
    services.disconnect(account, actor=users["pi"])
    [sent] = transport.sent("POST", zoom.PROVIDER.revoke_url)
    pair = base64.b64encode(b"zm-client:zm-secret").decode()
    assert sent["headers"]["Authorization"] == f"Basic {pair}"
    row = ConnectedAccount.objects.for_lab(lab).get(pk=account.pk)
    assert row.status == AccountStatus.REVOKED
    assert row.external_account_id == services.retired_id("zu1")
    assert (row.external_email, row.granted_scopes) == ("", [])
    assert not row.access_token() and not row.refresh_token()
    meeting = Meeting.objects.for_lab(lab).get()
    assert (meeting.join_url, meeting.external_id, meeting.video_provider) == (
        "https://zoom.us/j/77",
        "77",
        "zoom",
    )


def test_a_deletion_request_finds_zoom_by_the_zoom_address(transport, lab_users):
    lab, users = lab_users
    account = connect_zoom(transport, users["pi"], lab)  # Zoom address pi@example.test
    assert users["pi"].email != "pi@example.test"
    transport.on("POST", zoom.PROVIDER.revoke_url, response(200, {}))
    out = StringIO()
    call_command("delete_integration_data", email="PI@example.test", stdout=out)
    account.refresh_from_db()
    assert account.status == AccountStatus.REVOKED
    assert account.external_account_id == f"deleted:{account.pk}"
    assert account.external_email == ""
