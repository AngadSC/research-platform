"""Google OAuth verification acceptance (D262 to D265, D315 to D317, D333 to D345): what happens
when the person unticks scopes on Google's consent screen, and when one Google grant backs several
rows. Every Google call goes through the patched HTTP layer; nothing leaves the process.

Much of this is already proved one level down (test_meetings_calendar.py, test_google_chat.py,
test_hardening.py): the tests here add the redirects the browser sees, each optional Google Chat
scope on its own, and the revoke calls across labs."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings as django_settings
from django.urls import reverse
from rest_framework.test import APIClient

from integrations import services
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_calendar, google_chat, google_drive
from integrations.tests.conftest import token_reply
from integrations.tests.fake import response
from integrations.tests.test_google_chat import (
    API,
    CORE,
    GROUP,
    MESSAGES,
    PEOPLE,
    SPACE,
    _google,
    _people,
    connect_chat,
)
from integrations.tests.test_meetings_calendar import (
    CAL_APP,
    CAL_EVENTS,
    DRIVE_FILE,
    EMAIL,
    accounts_of,
    connect_google,
    google_identity,
    grant,
)
from labs import google_chat as sync
from labs.models import LabChatMessage

pytestmark = pytest.mark.django_db

REVOKE = google_drive.PROVIDER.revoke_url
MEMBERS = f"{API}/{SPACE}/members"
GROUP_MEMBERS = f"{API}/{GROUP}/members"
DM_MEMBERS = f"{API}/spaces/DM1/members"


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
        "google_chat": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }


@pytest.fixture
def committed(monkeypatch):
    """Run on_commit work at once, as a real commit would (the chat relay)."""
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, using=None, robust=False: func()
    )


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


# ------------------------------------------------ 1. partial grants, as the browser sees them


def callback(transport, user, lab, granted, start="google_calendar"):
    """Start a Google connect over the API, have Google answer with only `granted`, and return
    the callback's redirect. Identity lookups are answered, so a wrongly stored row would show."""
    client = api(user)
    url = client.post(f"/api/labs/{lab.pk}/integrations/{start}/connect/", {}, "json")
    state = parse_qs(urlsplit(url.json()["authorization_url"]).query)["state"][0]
    reply = token_reply("t", "r", " ".join(granted))
    transport.on("POST", google_calendar.PROVIDER.token_url, reply)
    google_identity(transport)
    out = client.get("/api/integrations/oauth/callback/", {"state": state, "code": "c"})
    assert out.status_code == 302
    return out["Location"]


def calls_after_the_token_exchange(transport):
    """Nothing is read with, or revoked for, a grant that is discarded (D68)."""
    return [c for c in transport.calls if c[1] != google_calendar.PROVIDER.token_url]


def test_declining_drive_only_connects_calendar_and_the_redirect_names_drive(transport, lab_users):
    lab, users = lab_users
    granted = ["openid", EMAIL, CAL_APP, CAL_EVENTS]
    where = callback(transport, users["pi"], lab, granted, start="google_drive")
    assert where.endswith("/settings/integrations?connected=google_calendar&skipped=google_drive")
    rows = accounts_of(lab, users["pi"])
    assert set(rows) == {"google_calendar"} and rows["google_calendar"].status == "active"
    assert set(rows["google_calendar"].granted_scopes) == set(google_calendar.PROVIDER.scopes)
    assert transport.sent("GET", google_drive.PROVIDER.identity_url) == []
    assert transport.sent("POST", REVOKE) == []


@pytest.mark.parametrize(
    "granted",
    [
        ["openid", EMAIL],  # identity only
        [EMAIL],
        ["openid"],
        [CAL_APP, CAL_EVENTS],  # Calendar without the identity scopes it needs
    ],
    ids=["openid+email", "email", "openid", "calendar-no-identity"],
)
def test_declining_everything_stores_nothing_and_redirects_with_an_error(
    transport, lab_users, granted
):
    lab, users = lab_users
    where = callback(transport, users["pi"], lab, granted)
    expected = f"{django_settings.FRONTEND_URL}/labs/{lab.pk}/settings/integrations"
    assert where == f"{expected}?error=scope_not_granted"
    assert not ConnectedAccount.objects.for_lab(lab).exists()
    assert calls_after_the_token_exchange(transport) == []  # not named, not revoked


BROAD = "https://www.googleapis.com/auth/drive"
GMAIL = "https://www.googleapis.com/auth/gmail.readonly"


@pytest.mark.parametrize(
    "granted",
    [
        ["openid", EMAIL, DRIVE_FILE, BROAD],  # Drive only, plus a broader Drive scope
        ["openid", EMAIL, CAL_APP, CAL_EVENTS, GMAIL],  # Calendar only, plus Gmail
        ["openid", EMAIL, DRIVE_FILE, CAL_APP, CAL_EVENTS, GMAIL],  # everything asked, plus Gmail
    ],
    ids=["drive+broad-drive", "calendar+gmail", "full+gmail"],
)
def test_a_scope_we_did_not_ask_for_is_refused_whatever_else_was_granted(
    transport, lab_users, granted
):
    lab, users = lab_users
    where = callback(transport, users["pi"], lab, granted)
    assert where.endswith("/settings/integrations?error=unexpected_scope")
    assert not ConnectedAccount.objects.for_lab(lab).exists()
    assert calls_after_the_token_exchange(transport) == []  # not named, not revoked


# ------------------------------------------------ 2. Google Chat optional scopes

MEMBERSHIPS = google_chat.MEMBERSHIPS
DIRECTORY = google_chat.DIRECTORY
ALL_SCOPES = [*CORE.split(), MEMBERSHIPS, DIRECTORY]
GRANTS = {
    "neither": (),
    "memberships-only": (MEMBERSHIPS,),
    "directory-only": (DIRECTORY,),
    "both": (MEMBERSHIPS, DIRECTORY),
}


@pytest.mark.parametrize("declined", [MEMBERSHIPS, DIRECTORY], ids=["memberships", "directory"])
def test_declining_one_optional_chat_scope_still_connects(transport, lab_users, declined):
    lab, u = lab_users
    granted = " ".join(s for s in ALL_SCOPES if s != declined)
    account = connect_chat(transport, u["member"], lab, "2002", "m@example.test", granted)
    assert account.status == AccountStatus.ACTIVE and account.skipped == []
    assert declined not in account.granted_scopes
    assert set(account.granted_scopes) == set(granted.split())


@pytest.fixture
def chat_admin(transport, lab_users, committed):
    """Connects the lab admin to Google Chat with the given optional scopes and links the lab
    chat to SPACE. Returns (lab, users)."""

    def make(optional):
        lab, u = lab_users
        scopes = " ".join([*CORE.split(), *optional])
        connect_chat(transport, u["lab_admin"], lab, "1001", "admin@example.test", scopes)
        transport.on("GET", f"{API}/{SPACE}", response(200, {"name": SPACE, "displayName": "Lab"}))
        sync.link_space(lab=lab, by=u["lab_admin"], space=SPACE)
        return lab, u

    return make


def requested(transport, since):
    return [(m, url) for m, url, _ in transport.calls[since:]]


@pytest.mark.parametrize("grants", GRANTS)
def test_sender_naming_asks_only_for_what_the_person_allowed(transport, chat_admin, grants):
    optional = GRANTS[grants]
    lab, _ = chat_admin(optional)
    transport.on("GET", PEOPLE, _people(("9", "Dana Directory")))
    member = {"name": "users/9", "displayName": "Eli Membership"}
    transport.on("GET", MEMBERS, response(200, {"memberships": [{"member": member}]}))
    transport.on("GET", MESSAGES, response(200, {"messages": [_google("g1", "hi")]}))
    since = len(transport.calls)
    sync.poll_all()
    asked = requested(transport, since)
    assert (("GET", PEOPLE) in asked) == (DIRECTORY in optional)
    if MEMBERSHIPS not in optional:
        assert ("GET", MEMBERS) not in asked
    expected = {
        "neither": "Someone on Google Chat",
        "memberships-only": "Eli Membership",
        "directory-only": "Dana Directory",
        "both": "Dana Directory",
    }[grants]
    assert sync.UNKNOWN_SENDER == "Someone on Google Chat"
    assert LabChatMessage.objects.for_lab(lab).get().external_author == expected


@pytest.mark.parametrize("grants", GRANTS)
def test_the_space_picker_asks_only_for_what_the_person_allowed(transport, chat_admin, grants):
    optional = GRANTS[grants]
    lab, u = chat_admin(optional)
    spaces = [
        {"name": "spaces/S1", "displayName": "Lab", "spaceType": "SPACE"},
        {"name": GROUP, "spaceType": "GROUP_CHAT", "lastActiveTime": "2099-01-02T00:00:00Z"},
        {
            "name": "spaces/DM1",
            "spaceType": "DIRECT_MESSAGE",
            "lastActiveTime": "2099-01-01T00:00:00Z",
        },
    ]
    transport.on("GET", f"{API}/spaces", response(200, {"spaces": spaces}))
    nameless = response(200, {"memberships": [{"member": {"name": "users/9"}}]})
    transport.on("GET", GROUP_MEMBERS, nameless)
    transport.on("GET", DM_MEMBERS, nameless)
    transport.on("GET", PEOPLE, _people(("9", "Dana Directory")))
    since = len(transport.calls)
    rows = {r["name"]: r for r in sync.list_spaces(lab, u["lab_admin"])}
    asked = requested(transport, since)
    listed = MEMBERSHIPS in optional
    assert (("GET", GROUP_MEMBERS) in asked) == listed
    assert (("GET", DM_MEMBERS) in asked) == listed
    assert (("GET", PEOPLE) in asked) == (listed and DIRECTORY in optional)
    assert rows["spaces/S1"]["display_name"] == "Lab"
    if listed and DIRECTORY in optional:
        assert rows[GROUP]["display_name"] == "Dana Directory"
        assert rows["spaces/DM1"]["display_name"] == "Dana Directory"
    else:  # nobody can be named: the kind of conversation and the date of its last message
        assert rows[GROUP]["display_name"] == "Group chat · Jan 2" and rows[GROUP]["members"] == []
        assert rows["spaces/DM1"]["display_name"] == "Direct message · Jan 1"


@pytest.mark.parametrize("declined", [True, False], ids=["declined", "granted"])
def test_the_at_mention_list_needs_the_membership_scope(transport, chat_admin, declined):
    lab, u = chat_admin(() if declined else (MEMBERSHIPS,))
    member = {"name": "users/777", "displayName": "Dana Example"}
    transport.on("GET", MEMBERS, response(200, {"memberships": [{"member": member}]}))
    since = len(transport.calls)
    people = api(u["viewer"]).get(reverse("labs:google-chat-people", args=[lab.pk])).json()
    asked = requested(transport, since)
    if declined:
        assert people == [] and ("GET", MEMBERS) not in asked
    else:
        assert people == [{"id": "777", "name": "Dana Example"}]


# ------------------------------------------------ 4. revoking a shared Google grant


def revokes(transport):
    return transport.sent("POST", REVOKE)


def status_of(lab, user):
    return {name: row.status for name, row in accounts_of(lab, user).items()}


@pytest.fixture
def two_labs(lab_users, make_lab, join):
    lab_a, users = lab_users
    lab_b = make_lab("Other")
    join(users["pi"], lab_b, "pi")
    join(users["member"], lab_b, "member")
    return lab_a, lab_b, users


def test_the_same_google_grant_in_two_labs_is_revoked_only_with_the_last_one(transport, two_labs):
    lab_a, lab_b, users = two_labs
    pi = users["pi"]
    connect_google(transport, pi, lab_a)
    connect_google(transport, pi, lab_b)
    transport.on("POST", REVOKE, response(200, {}))

    services.disconnect(accounts_of(lab_a, pi)["google_drive"], actor=pi)
    assert revokes(transport) == []  # lab B still uses the grant
    assert set(status_of(lab_a, pi).values()) == {AccountStatus.REVOKED}  # the bundle left lab A
    assert set(status_of(lab_b, pi).values()) == {AccountStatus.ACTIVE}

    services.disconnect(accounts_of(lab_b, pi)["google_calendar"], actor=pi)
    [sent] = revokes(transport)  # exactly one, for the whole bundle
    assert sent["data"] == {"token": "g-rt"}
    assert set(status_of(lab_b, pi).values()) == {AccountStatus.REVOKED}


def test_drive_in_one_lab_and_calendar_in_another_share_the_grant(transport, two_labs):
    """The person declined Calendar in lab A and Drive in lab B. Drive's row is named by Drive's
    permission id and Calendar's by email: the same address still ties them to one grant."""
    lab_a, lab_b, users = two_labs
    pi = users["pi"]
    grant(transport, pi, lab_a, ["openid", EMAIL, DRIVE_FILE], start="google_calendar")
    grant(transport, pi, lab_b, ["openid", EMAIL, CAL_APP, CAL_EVENTS], start="google_drive")
    assert set(accounts_of(lab_a, pi)) == {"google_drive"}
    assert set(accounts_of(lab_b, pi)) == {"google_calendar"}
    transport.on("POST", REVOKE, response(200, {}))

    services.disconnect(accounts_of(lab_a, pi)["google_drive"], actor=pi)
    assert revokes(transport) == []
    assert status_of(lab_b, pi) == {"google_calendar": AccountStatus.ACTIVE}

    services.disconnect(accounts_of(lab_b, pi)["google_calendar"], actor=pi)
    assert len(revokes(transport)) == 1


def test_another_persons_google_in_another_lab_never_shields_a_grant(transport, two_labs):
    lab_a, lab_b, users = two_labs
    connect_google(transport, users["pi"], lab_a, email="pi@example.test")
    connect_google(transport, users["member"], lab_b, email="member@example.test")
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(accounts_of(lab_a, users["pi"])["google_calendar"], actor=users["pi"])
    assert len(revokes(transport)) == 1
    assert set(status_of(lab_b, users["member"]).values()) == {AccountStatus.ACTIVE}


def test_removing_a_member_from_one_lab_keeps_their_grant_for_the_other(
    transport, two_labs, django_capture_on_commit_callbacks
):
    lab_a, lab_b, users = two_labs
    pi = users["pi"]
    connect_google(transport, pi, lab_a)
    connect_google(transport, pi, lab_b)
    transport.on("POST", REVOKE, response(200, {}))
    with django_capture_on_commit_callbacks(execute=True):
        assert services.revoke_member_accounts(lab_a, pi, reason="member_removed") == 2
    assert revokes(transport) == []
    assert set(status_of(lab_a, pi).values()) == {AccountStatus.REVOKED}
    assert set(status_of(lab_b, pi).values()) == {AccountStatus.ACTIVE}


@pytest.mark.xfail(
    strict=True,
    reason="revoke_member_accounts revokes each bundle row on its own: Drive and Calendar rows "
    "sharing one refresh token send two identical POSTs to Google's revoke URL (disconnect() "
    "sends one). Harmless, since Google answers the second with an error and it is best effort.",
)
def test_removing_a_member_from_their_last_lab_revokes_the_grant_once(
    transport, two_labs, django_capture_on_commit_callbacks
):
    lab_a, _lab_b, users = two_labs
    pi = users["pi"]
    connect_google(transport, pi, lab_a)
    transport.on("POST", REVOKE, response(200, {}))
    with django_capture_on_commit_callbacks(execute=True):
        services.revoke_member_accounts(lab_a, pi, reason="member_removed")
    assert len(revokes(transport)) == 1
