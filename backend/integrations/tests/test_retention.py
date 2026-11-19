"""What a revoke leaves behind, and deletion requests (Google verification item 10). Every Google
call goes through the fake transport; nothing leaves the process."""

import importlib
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from integrations import registry, services
from integrations.models import AccountStatus, ConnectedAccount
from integrations.providers import google_calendar, google_chat, google_drive
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response
from labs.models import (
    ChatSource,
    GoogleCalendarSync,
    GoogleChatBridge,
    LabChatMessage,
    LabMembership,
    SyncedEvent,
)

pytestmark = pytest.mark.django_db

GCAL = google_calendar.API
REVOKE = google_drive.PROVIDER.revoke_url
SCOPES = " ".join(registry.bundle_scopes(google_calendar.PROVIDER))
APP_CAL = f"{GCAL}/calendars/appcal%40group"


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
        "google_chat": {"client_id": "gc-client", "client_secret": "gc-secret"},
    }


def connect_google(transport, user, lab, email="pi@example.test"):
    request = make_request(user)
    url = services.start_connect(request, lab, "google_calendar")
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on("POST", google_calendar.PROVIDER.token_url, token_reply("g-at", "g-rt", SCOPES))
    transport.on(
        "GET",
        google_drive.PROVIDER.identity_url,
        response(200, {"user": {"permissionId": "perm-" + email, "emailAddress": email}}),
    )
    transport.on(
        "GET", google_calendar.IDENTITY_URL, response(200, {"sub": "sub-" + email, "email": email})
    )
    services.complete_connect(request, state=state, code="code")
    return rows(lab, user)


def connect_chat(transport, user, lab, sub, email):
    request = make_request(user)
    url = services.start_connect(request, lab, "google_chat")
    state = parse_qs(urlsplit(url).query)["state"][0]
    scopes = " ".join(google_chat.PROVIDER.scopes)
    transport.on("POST", google_chat.PROVIDER.token_url, token_reply("gc-at", "gc-rt", scopes))
    transport.on(
        "GET", google_chat.PROVIDER.identity_url, response(200, {"sub": sub, "email": email})
    )
    return services.complete_connect(request, state=state, code="code")


def rows(lab, user):
    return {a.provider: a for a in ConnectedAccount.objects.for_lab(lab).filter(user=user)}


def with_app_calendar(lab, account):
    sync = GoogleCalendarSync.objects.create(
        lab=lab, user=account.user, account=account, push_tasks=True, app_calendar_id="appcal@group"
    )
    SyncedEvent.objects.create(lab=lab, sync=sync, key="task:1", event_id="e1", fingerprint="f")
    return sync


def assert_cleared(account):
    account.refresh_from_db()
    assert account.status == AccountStatus.REVOKED
    assert (account.external_email, account.granted_scopes) == ("", [])
    assert account.external_account_id.startswith("revoked:")
    assert not account.access_token_ct and not account.refresh_token_ct
    assert "example.test" not in str(account)
    assert not GoogleCalendarSync.objects.for_lab(account.lab_id).filter(account=account).exists()


# ---------------------------------------------------------------- every revoke path clears


def test_own_disconnect_clears_the_bundle_and_its_calendar_settings(transport, lab_users):
    lab, u = lab_users
    mine = connect_google(transport, u["pi"], lab)
    with_app_calendar(lab, mine["google_calendar"])
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(mine["google_drive"], actor=u["pi"])
    for account in mine.values():
        assert_cleared(account)
    assert SyncedEvent.objects.for_lab(lab).count() == 0
    assert len(transport.sent("POST", REVOKE)) == 1
    assert not transport.sent("DELETE", APP_CAL)  # not asked: the calendar stays in Google
    event = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DISCONNECTED).first()
    assert "app_calendar" not in event.metadata and "example.test" not in event.target_repr


def test_an_admin_revoke_clears_and_never_deletes_their_calendar(transport, lab_users):
    lab, u = lab_users
    theirs = connect_google(transport, u["member"], lab, email="m@example.test")
    with_app_calendar(lab, theirs["google_calendar"])
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(theirs["google_calendar"], actor=u["lab_admin"], delete_app_calendar=True)
    for account in theirs.values():
        assert_cleared(account)
    assert not transport.sent("DELETE", APP_CAL)  # only the owner may ask for that


def test_member_removal_and_the_orphan_sweep_clear(
    transport, lab_users, django_capture_on_commit_callbacks
):
    lab, u = lab_users
    removed = connect_google(transport, u["member"], lab, email="m@example.test")
    with_app_calendar(lab, removed["google_calendar"])
    orphan = connect_google(transport, u["viewer"], lab, email="v@example.test")
    transport.on("POST", REVOKE, response(200, {}))
    with django_capture_on_commit_callbacks(execute=True):
        assert services.revoke_member_accounts(lab, u["member"], reason="member_removed") == 2
    LabMembership.objects.for_lab(lab).filter(user=u["viewer"]).delete()
    with django_capture_on_commit_callbacks(execute=True):
        assert services.revoke_orphaned_accounts() == 2
    for account in [*removed.values(), *orphan.values()]:
        assert_cleared(account)
    assert transport.sent("POST", REVOKE)  # the grants were revoked at Google, after commit


# ---------------------------------------------------------------- clearing never mis-revokes


def test_a_grant_still_used_in_another_lab_survives_and_goes_with_the_last(
    transport, lab_users, make_lab, join, django_capture_on_commit_callbacks
):
    lab_a, u = lab_users
    lab_b = make_lab("Other")
    join(u["pi"], lab_b, "pi")
    in_a = connect_google(transport, u["pi"], lab_a)
    in_b = connect_google(transport, u["pi"], lab_b)
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(in_a["google_drive"], actor=u["pi"])
    assert transport.sent("POST", REVOKE) == []
    assert {r.status for r in rows(lab_b, u["pi"]).values()} == {AccountStatus.ACTIVE}
    assert rows(lab_b, u["pi"])["google_drive"].external_email == "pi@example.test"
    with django_capture_on_commit_callbacks(execute=True):  # the provider call runs after commit
        services.revoke_member_accounts(lab_b, u["pi"], reason="member_removed")
    assert len(transport.sent("POST", REVOKE)) >= 1
    for account in [*in_a.values(), *in_b.values()]:
        assert_cleared(account)


def test_after_commit_a_sibling_in_another_lab_still_matches_by_the_old_email(
    transport, lab_users, make_lab, join, django_capture_on_commit_callbacks
):
    """Drive (named by permissionId) in lab A, Calendar (named by email) in lab B: the revoke
    after commit must still see lab A's Drive row, though lab B's row has been cleared."""
    lab_a, u = lab_users
    lab_b = make_lab("Other")
    join(u["pi"], lab_b, "pi")
    connect_google(transport, u["pi"], lab_a)
    connect_google(transport, u["pi"], lab_b)
    ConnectedAccount.objects.for_lab(lab_a).filter(provider="google_calendar").delete()
    ConnectedAccount.objects.for_lab(lab_b).filter(provider="google_drive").delete()
    transport.on("POST", REVOKE, response(200, {}))
    with django_capture_on_commit_callbacks(execute=True):
        services.revoke_member_accounts(lab_b, u["pi"], reason="member_removed")
    assert transport.sent("POST", REVOKE) == []
    assert rows(lab_a, u["pi"])["google_drive"].status == AccountStatus.ACTIVE


def test_reconnecting_the_same_google_account_reuses_its_row(transport, lab_users):
    lab, u = lab_users
    before = connect_google(transport, u["pi"], lab)
    transport.on("POST", REVOKE, response(200, {}))
    services.disconnect(before["google_calendar"], actor=u["pi"])
    after = connect_google(transport, u["pi"], lab)
    for name, account in after.items():
        assert account.pk == before[name].pk  # links and meetings keep pointing at it (D69)
        assert account.status == AccountStatus.ACTIVE
        assert account.external_email == "pi@example.test"
    assert after["google_calendar"].external_account_id == "pi@example.test"


# ---------------------------------------------------------------- the app calendar in Google


def disconnect_api(user, lab, account, body=None):
    client = APIClient()
    client.force_login(user)
    url = f"/api/labs/{lab.pk}/integrations/accounts/{account.pk}/"
    return client.delete(url, body, format="json") if body else client.delete(url)


def test_asked_the_app_calendar_is_deleted_before_the_grant_is_revoked(transport, lab_users):
    lab, u = lab_users
    mine = connect_google(transport, u["pi"], lab)
    with_app_calendar(lab, mine["google_calendar"])
    transport.on("DELETE", APP_CAL, response(204))
    transport.on("POST", REVOKE, response(200, {}))
    resp = disconnect_api(u["pi"], lab, mine["google_drive"], {"delete_app_calendar": True})
    assert resp.status_code == 200
    watched = {("DELETE", APP_CAL), ("POST", REVOKE)}
    order = [(m, url) for m, url, _ in transport.calls if (m, url) in watched]
    assert order == [("DELETE", APP_CAL), ("POST", REVOKE)]
    assert_cleared(mine["google_calendar"])
    events = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DISCONNECTED)
    assert {e.metadata["app_calendar"] for e in events} == {"deleted"}


def test_a_failed_calendar_delete_never_blocks_the_disconnect(transport, lab_users):
    lab, u = lab_users
    mine = connect_google(transport, u["pi"], lab)
    with_app_calendar(lab, mine["google_calendar"])
    transport.on("DELETE", APP_CAL, response(403, {}))
    transport.on("POST", REVOKE, response(200, {}))
    resp = disconnect_api(u["pi"], lab, mine["google_calendar"], {"delete_app_calendar": True})
    assert resp.status_code == 200
    for account in mine.values():
        assert_cleared(account)
    event = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DISCONNECTED).first()
    assert event.metadata["app_calendar"] == "failed"


def test_without_an_app_calendar_nothing_is_called(transport, lab_users):
    lab, u = lab_users
    mine = connect_google(transport, u["pi"], lab)
    transport.on("POST", REVOKE, response(200, {}))
    disconnect_api(u["pi"], lab, mine["google_drive"], {"delete_app_calendar": True})
    assert not [c for c in transport.calls if c[0] == "DELETE"]
    event = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DISCONNECTED).first()
    assert event.metadata["app_calendar"] == "none"


# ---------------------------------------------------------------- deletion requests


@pytest.fixture
def requester(transport, lab_users, make_lab, join):
    """The PI has Google and Chat in two labs, a Chat link, a calendar and a message from Google
    with their picture; the member has the same in lab one and must be untouched."""
    lab, u = lab_users
    other = make_lab("Other")
    join(u["pi"], other, "pi")
    for where in (lab, other):
        google = connect_google(transport, u["pi"], where)
        with_app_calendar(where, google["google_calendar"])
    chat = connect_chat(transport, u["pi"], lab, "1001", "pi@example.test")
    GoogleChatBridge.objects.create(
        lab=lab, account=chat, created_by=u["pi"], space="spaces/AAAA", cursor="x"
    )
    kept = connect_google(transport, u["member"], lab, email="m@example.test")
    with_app_calendar(lab, kept["google_calendar"])
    for who in (u["pi"], u["member"]):
        LabChatMessage.objects.create(
            lab=lab,
            author=who,
            body="hi",
            source=ChatSource.GOOGLE_CHAT,
            external_avatar="https://lh3.googleusercontent.com/a/x",
        )
    LabChatMessage.objects.create(
        lab=lab, body="from outside", source=ChatSource.GOOGLE_CHAT, external_author="Out Sider"
    )
    transport.on("POST", REVOKE, response(200, {}))
    transport.on("POST", google_chat.PROVIDER.revoke_url, response(200, {}))
    return lab, other, u, kept


def snapshot(*labs):
    return [
        (
            sorted(
                ConnectedAccount.objects.for_lab(lab).values_list(
                    "external_account_id", "external_email", "status"
                )
            ),
            GoogleCalendarSync.objects.for_lab(lab).count(),
            GoogleChatBridge.objects.for_lab(lab).count(),
            sorted(LabChatMessage.objects.for_lab(lab).values_list("external_avatar", flat=True)),
        )
        for lab in labs
    ]


def test_a_dry_run_changes_nothing(transport, requester):
    lab, other, u, _ = requester
    before = snapshot(lab, other)
    call_command(
        "delete_integration_data",
        email=u["pi"].email,
        lab=str(lab.pk),
        chat_name="Out Sider",
        dry_run=True,
    )
    assert snapshot(lab, other) == before
    assert not AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DATA_DELETED).exists()
    assert not transport.sent("POST", REVOKE)


def test_a_deletion_request_anonymises_that_person_only_and_audits_each_lab(
    transport, requester, django_capture_on_commit_callbacks
):
    lab, other, u, kept = requester
    with django_capture_on_commit_callbacks(execute=True):
        call_command("delete_integration_data", email="PI@example.test")  # their Google address
    mine = [*rows(lab, u["pi"]).values(), *rows(other, u["pi"]).values()]
    assert len(mine) == 5
    for account in mine:
        assert account.status == AccountStatus.REVOKED
        assert account.external_account_id == f"deleted:{account.pk}"
        assert (account.external_email, account.granted_scopes) == ("", [])
    for where in (lab, other):
        assert not GoogleCalendarSync.objects.for_lab(where).filter(user=u["pi"]).exists()
    assert not GoogleChatBridge.objects.for_lab(lab).exists()
    assert transport.sent("POST", REVOKE)
    events = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DATA_DELETED)
    assert {e.lab_id for e in events} == {lab.pk, other.pk}
    assert all(e.actor is None and "example.test" not in str(e.metadata) for e in events)
    # The member's connection, calendar and picture are untouched.
    for account in kept.values():
        account.refresh_from_db()
        assert account.status == AccountStatus.ACTIVE and account.external_email
    assert GoogleCalendarSync.objects.for_lab(lab).filter(user=u["member"]).exists()
    assert LabChatMessage.objects.for_lab(lab).get(author=u["member"]).external_avatar


def test_a_deletion_request_by_account_email_clears_their_chat_pictures_and_a_named_sender(
    transport, requester, django_capture_on_commit_callbacks
):
    lab, other, u, _ = requester
    with django_capture_on_commit_callbacks(execute=True):
        call_command(
            "delete_integration_data", email=u["pi"].email, lab=str(lab.pk), chat_name="Out Sider"
        )
    assert LabChatMessage.objects.for_lab(lab).get(author=u["pi"]).external_avatar == ""
    assert not LabChatMessage.objects.for_lab(lab).filter(external_author="Out Sider").exists()
    assert {r.status for r in rows(lab, u["pi"]).values()} == {AccountStatus.REVOKED}
    # --lab keeps it to that lab
    assert {r.status for r in rows(other, u["pi"]).values()} == {AccountStatus.ACTIVE}


def test_revoked_rows_from_before_are_cleared_by_the_migration(transport, lab_users):
    lab, u = lab_users
    old = connect_google(transport, u["pi"], lab)["google_calendar"]
    with_app_calendar(lab, old)
    ConnectedAccount.objects.for_lab(lab).filter(pk=old.pk).update(status=AccountStatus.REVOKED)
    migration = importlib.import_module("integrations.migrations.0005_clear_revoked_accounts")
    state = MigrationExecutor(connection).loader.project_state(
        ("integrations", "0005_clear_revoked_accounts")
    )
    migration.clear_revoked(state.apps, None)
    old.refresh_from_db()
    assert old.external_account_id == services.retired_id("pi@example.test")
    assert old.external_email == "" and old.granted_scopes == []
    assert not GoogleCalendarSync.objects.for_lab(lab).exists()
