"""Optional separate Calendar client (GOOGLE_VERIFICATION item 9). With
INTEGRATION_GOOGLE_CALENDAR_CLIENT_ID/_SECRET set, Calendar is its own Google sign-in, so the Drive
token handed to the Picker carries drive.file only. Without it, Drive and Calendar stay one grant
(D262) and the Picker says so. Every Google call goes through the patched HTTP layer."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.cache import cache
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from audit.models import AuditEvent
from core.models import Notification
from integrations import registry, services
from integrations.http import AccountUnavailable
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_calendar, google_drive
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response

pytestmark = pytest.mark.django_db

DRIVE, CAL = google_drive.PROVIDER, google_calendar.PROVIDER
TOKEN, REVOKE = DRIVE.token_url, DRIVE.revoke_url  # Google's, the same for both
DRIVE_SCOPES = " ".join(sorted(DRIVE.scopes))
CAL_SCOPES = " ".join(sorted(CAL.scopes))
EMAIL = "pi@example.test"


@pytest.fixture(autouse=True)
def drive_client(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
    }
    settings.INTEGRATION_PUBLIC = {"google_drive": {"api_key": "pk", "app_id": "123"}}


@pytest.fixture
def split(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_calendar": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }


def identities(transport):
    who = {"user": {"permissionId": "perm-pi", "emailAddress": EMAIL}}
    transport.on("GET", DRIVE.identity_url, response(200, who))
    transport.on("GET", CAL.identity_url, response(200, {"sub": "1", "email": EMAIL}))


def start(user, lab, name):
    request = make_request(user)
    url = services.start_connect(request, lab, name)
    return request, parse_qs(urlsplit(url).query)


def connect(transport, user, lab, name, scope, access):
    request, query = start(user, lab, name)
    transport.on("POST", TOKEN, token_reply(access, f"{access}-rt", scope))
    identities(transport)
    return services.complete_connect(request, state=query["state"][0], code="c")


def rows(lab, user):
    return {r.provider: r for r in ConnectedAccount.objects.for_lab(lab).filter(user=user)}


def picker(lab, user):
    client = Client()
    client.force_login(user)
    return client, f"/api/labs/{lab.pk}/integrations/google/picker-token/"


# ---------------------------------------------------------------- the switch itself


def test_without_a_calendar_client_drive_and_calendar_stay_one_sign_in():
    assert CAL.client() == DRIVE.client() == ("gd-client", "gd-secret")
    assert [m.name for m in registry.bundle_of(DRIVE)] == ["google_drive", "google_calendar"]
    assert set(registry.bundle_scopes(DRIVE)) == set(DRIVE.scopes) | set(CAL.scopes)


def test_a_half_configured_calendar_client_is_ignored(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_calendar": {"client_id": "gc-client", "client_secret": ""},
    }
    assert CAL.client() == DRIVE.client()
    assert len(registry.bundle_of(CAL)) == 2


def test_with_a_calendar_client_each_is_its_own_sign_in(split):
    assert CAL.client() == ("gc-client", "gc-secret") and DRIVE.client()[0] == "gd-client"
    assert registry.bundle_of(DRIVE) == [DRIVE] and registry.bundle_of(CAL) == [CAL]


def test_providers_list_shows_no_bundle_when_split(split, lab_users):
    lab, users = lab_users
    client, _ = picker(lab, users["pi"])
    listed = {
        p["name"]: p for p in client.get(f"/api/labs/{lab.pk}/integrations/providers/").json()
    }
    assert listed["google_drive"]["bundle"] == [] and listed["google_calendar"]["bundle"] == []
    assert listed["google_calendar"]["configured"]
    assert "gc-secret" not in str(listed)


def test_providers_list_shows_the_bundle_when_not_split(lab_users):
    lab, users = lab_users
    client, _ = picker(lab, users["pi"])
    listed = {
        p["name"]: p for p in client.get(f"/api/labs/{lab.pk}/integrations/providers/").json()
    }
    assert listed["google_drive"]["bundle"] == ["google_calendar"]
    assert listed["google_calendar"]["bundle"] == ["google_drive"]


# ---------------------------------------------------------------- connecting when split


def test_split_start_urls_ask_each_client_for_its_own_scopes(split, lab_users):
    lab, users = lab_users
    _, cal = start(users["pi"], lab, "google_calendar")
    assert cal["client_id"] == ["gc-client"] and cal["scope"] == [CAL_SCOPES]
    _, drive = start(users["pi"], lab, "google_drive")
    assert drive["client_id"] == ["gd-client"] and drive["scope"] == [DRIVE_SCOPES]
    with pytest.raises(services.OAuthError):  # Drive's client can't be asked for Calendar
        services.start_connect(
            make_request(users["pi"]), lab, "google_drive", scopes=[*DRIVE.scopes, *CAL.scopes]
        )


def test_split_callbacks_store_each_service_separately(split, transport, lab_users):
    lab, users = lab_users
    drive = connect(transport, users["pi"], lab, "google_drive", DRIVE_SCOPES, "gd-at")
    assert drive.skipped == [] and set(rows(lab, users["pi"])) == {"google_drive"}
    assert transport.sent("POST", TOKEN)[-1]["data"]["client_id"] == "gd-client"
    cal = connect(transport, users["pi"], lab, "google_calendar", CAL_SCOPES, "gc-at")
    assert cal.skipped == []
    sent = transport.sent("POST", TOKEN)[-1]["data"]
    assert (sent["client_id"], sent["client_secret"]) == ("gc-client", "gc-secret")
    got = rows(lab, users["pi"])
    assert (
        got["google_drive"].access_token() == "gd-at"
        and got["google_calendar"].access_token() == "gc-at"
    )
    assert got["google_drive"].granted_scopes == list(DRIVE.scopes)
    assert set(got["google_calendar"].granted_scopes) == set(CAL.scopes)


def test_split_drive_refuses_a_token_that_also_carries_calendar(split, transport, lab_users):
    """D78 stays strict: Drive's client now asks for drive.file only, so Calendar scopes back
    from it (an old bundled grant) are refused, never stored."""
    lab, users = lab_users
    both = " ".join(registry.bundle_scopes(DRIVE) + tuple(CAL.scopes))
    with pytest.raises(services.OAuthError) as err:
        connect(transport, users["pi"], lab, "google_drive", both, "gd-at")
    assert err.value.code == "unexpected_scope"
    assert not ConnectedAccount.objects.for_lab(lab).exists()


# ---------------------------------------------------------------- refresh when split


def test_split_calendar_refresh_sends_the_calendar_clients_credentials(split, transport, lab_users):
    lab, users = lab_users
    cal = connect(transport, users["pi"], lab, "google_calendar", CAL_SCOPES, "gc-at")
    transport.on("POST", TOKEN, token_reply("gc-fresh", None, CAL_SCOPES))
    services.refresh_access_token(cal)
    sent = transport.sent("POST", TOKEN)[-1]["data"]
    assert sent["grant_type"] == "refresh_token" and sent["refresh_token"] == "gc-at-rt"
    assert (sent["client_id"], sent["client_secret"]) == ("gc-client", "gc-secret")
    assert cal.status == AccountStatus.ACTIVE and cal.access_token() == "gc-fresh"


@pytest.mark.parametrize(
    ("code", "status"),
    [("invalid_grant", AccountStatus.EXPIRED), ("unauthorized_client", AccountStatus.ERROR)],
)
def test_a_calendar_row_from_before_the_split_asks_to_reconnect(
    settings, transport, lab_users, code, status
):
    """Its refresh token was issued to Drive's client, so Google refuses it with the Calendar
    client. Which error Google sends is not documented; either way the row is wiped, marked and
    the owner told to reconnect."""
    lab, users = lab_users
    connect(
        transport, users["pi"], lab, "google_calendar", " ".join(registry.bundle_scopes(CAL)), "old"
    )
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_calendar": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }
    cal = rows(lab, users["pi"])["google_calendar"]
    transport.on(
        "POST", TOKEN, response(401 if code == "unauthorized_client" else 400, {"error": code})
    )
    with pytest.raises(AccountUnavailable):
        services.refresh_access_token(cal)
    assert transport.sent("POST", TOKEN)[-1]["data"]["client_id"] == "gc-client"
    assert cal.status == status and not cal.access_token_ct and not cal.refresh_token_ct
    assert AuditEvent.objects.get(action="integration.refresh_failed").metadata["reason"] == code
    assert (
        Notification.objects.for_lab(lab)
        .filter(recipient=users["pi"], title__contains="Calendar")
        .exists()
    )
    # Drive is untouched by Calendar's failure
    assert rows(lab, users["pi"])["google_drive"].status == AccountStatus.ACTIVE


def test_a_drive_row_from_before_the_split_still_holding_calendar_is_wiped(
    settings, transport, lab_users
):
    """Its grant still names the Calendar scopes; Drive's client no longer asks for them, so the
    refresh is refused (D78) and the person reconnects Drive on its own."""
    lab, users = lab_users
    whole = " ".join(registry.bundle_scopes(DRIVE))
    connect(transport, users["pi"], lab, "google_drive", whole, "old")
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_calendar": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }
    drive = rows(lab, users["pi"])["google_drive"]
    transport.on("POST", TOKEN, token_reply("fresh", None, whole))
    with pytest.raises(AccountUnavailable):
        services.refresh_access_token(drive)
    assert transport.sent("POST", TOKEN)[-1]["data"]["client_id"] == "gd-client"
    assert drive.status == AccountStatus.ERROR and not drive.access_token_ct


# ---------------------------------------------------------------- disconnect when split


@pytest.mark.parametrize(
    ("gone", "kept"), [("google_drive", "google_calendar"), ("google_calendar", "google_drive")]
)
def test_split_disconnect_leaves_the_other_service_alone(split, transport, lab_users, gone, kept):
    lab, users = lab_users
    connect(transport, users["pi"], lab, "google_drive", DRIVE_SCOPES, "gd-at")
    connect(transport, users["pi"], lab, "google_calendar", CAL_SCOPES, "gc-at")
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(rows(lab, users["pi"])[gone], actor=users["pi"])
    got = rows(lab, users["pi"])
    assert got[gone].status == AccountStatus.REVOKED
    assert got[kept].status == AccountStatus.ACTIVE and got[kept].access_token_ct
    revoked = [kw["data"]["token"] for kw in transport.sent("POST", REVOKE)]
    assert revoked == ["gd-at-rt" if gone == "google_drive" else "gc-at-rt"]


# ---------------------------------------------------------------- the Picker token's scope


def test_bundled_picker_scope_names_the_calendar_scopes_the_token_carries(transport, lab_users):
    lab, users = lab_users
    connect(
        transport,
        users["pi"],
        lab,
        "google_drive",
        " ".join(registry.bundle_scopes(DRIVE)),
        "gd-at",
    )
    client, url = picker(lab, users["pi"])
    tok = client.get(url)
    assert tok.status_code == 200 and tok["Cache-Control"] == "no-store"
    assert tok.json()["access_token"] == "gd-at"
    assert tok.json()["scope"].split() == sorted(set(DRIVE.scopes) | set(CAL.scopes))


def test_bundled_picker_scope_ignores_a_calendar_at_another_address(transport, lab_users):
    lab, users = lab_users
    connect(transport, users["pi"], lab, "google_drive", DRIVE_SCOPES, "gd-at")  # Calendar declined
    connect(transport, users["lab_admin"], lab, "google_calendar", CAL_SCOPES, "m-at")
    ConnectedAccount.objects.for_lab(lab).filter(user=users["lab_admin"]).update(
        user=users["pi"], external_email="other@example.test", external_account_id="other"
    )
    client, url = picker(lab, users["pi"])
    assert client.get(url).json()["scope"] == DRIVE_SCOPES


def test_split_picker_scope_is_drive_only_and_still_audited_and_throttled(
    split, transport, lab_users, monkeypatch
):
    lab, users = lab_users
    client, url = picker(lab, users["pi"])
    assert client.get(url).status_code == 404  # no Drive account
    connect(transport, users["pi"], lab, "google_drive", DRIVE_SCOPES, "gd-at")
    connect(transport, users["pi"], lab, "google_calendar", CAL_SCOPES, "gc-at")
    tok = client.get(url)
    assert tok.status_code == 200 and tok["Cache-Control"] == "no-store"
    assert tok.json() | {"expires_in": 0} == {
        "access_token": "gd-at",
        "expires_in": 0,
        "scope": DRIVE_SCOPES,
    }
    event = AuditEvent.objects.get(action="integration.picker_token_issued")
    assert event.metadata == {"provider": "google_drive"}
    assert "gd-at" not in str(list(AuditEvent.objects.values()))
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"picker_token": "2/hour"})
    cache.clear()
    assert [client.get(url).status_code for _ in range(3)] == [200, 200, 429]
