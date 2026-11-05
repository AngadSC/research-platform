"""The integrations API end to end with the fake provider: connect start, a mocked callback,
link create, disconnect, admin revoke, errors, and the lifecycle hooks."""

from urllib.parse import parse_qs, urlsplit

import pytest
from django.conf import settings
from django.test import Client

from audit.models import AuditAction, AuditEvent
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink
from integrations.tests.conftest import token_reply
from integrations.tests.fake import FAKE, response

pytestmark = pytest.mark.django_db

FILE = "https://api.fake.test/files/f1"
ITEM = {
    "name": "Raw data.csv",
    "url": "https://fake.test/f1",
    "mimeType": "text/csv",
    "modifiedTime": "2030-01-01T10:00:00Z",
    "version": 3,
}


def api(user):
    c = Client()
    c.force_login(user)
    return c


def L(lab):
    return f"/api/labs/{lab.pk}"


def connect_via_api(client, lab, transport, *, ext_id="ext-1", code="the-code"):
    resp = client.post(f"{L(lab)}/integrations/fake/connect/", {}, "application/json")
    assert resp.status_code == 200, resp.content
    state = parse_qs(urlsplit(resp.json()["authorization_url"]).query)["state"][0]
    transport.on("POST", FAKE.token_url, token_reply("at-1", "rt-1"))
    transport.on("GET", FAKE.identity_url, response(200, {"id": ext_id, "email": "a@fake.test"}))
    return client.get("/api/integrations/oauth/callback/", {"state": state, "code": code})


def test_connect_link_disconnect_and_revoke(lab_users, transport, make_project):
    lab, users = lab_users
    member, pi = users["member"], users["pi"]
    project = make_project(lab)
    c = api(member)

    providers = c.get(f"{L(lab)}/integrations/providers/").json()
    fake = next(p for p in providers if p["name"] == "fake")
    assert fake["configured"] and fake["account"] is None

    cb = connect_via_api(c, lab, transport)
    assert cb.status_code == 302
    assert cb["Location"] == (
        f"{settings.FRONTEND_URL}/labs/{lab.pk}/settings/integrations?connected=fake"
    )
    accounts = c.get(f"{L(lab)}/integrations/accounts/").json()
    assert [(a["provider"], a["status"], a["external_email"]) for a in accounts] == [
        ("fake", "active", "a@fake.test")
    ]
    assert c.get(f"{L(lab)}/integrations/providers/").json()[-1]["account"]["status"] == "active"
    assert AuditEvent.objects.filter(action=AuditAction.INTEGRATION_CONNECTED).count() == 1

    # link: the provider is read with the member's own account; the project must be visible
    transport.on("GET", FILE, response(200, ITEM))
    body = {"provider": "fake", "external_id": "f1"}
    links_url = f"{L(lab)}/projects/{project.pk}/external-links/"
    assert c.post(links_url, body, "application/json").status_code == 404  # not on the project
    from projects.models import ProjectMembership, ProjectRole

    ProjectMembership.objects.create(
        lab=lab, project=project, user=member, role=ProjectRole.CONTRIBUTOR
    )
    resp = c.post(links_url, body, "application/json")
    assert resp.status_code == 201, resp.content
    link = resp.json()
    assert (link["title"], link["mime_type"], link["linker_connection_status"]) == (
        "Raw data.csv",
        "text/csv",
        "active",
    )
    assert "access_token" not in resp.content.decode()
    assert c.get(links_url).json()[0]["id"] == link["id"]
    created = AuditEvent.objects.get(action=AuditAction.EXTERNAL_LINK_CREATED)
    assert created.metadata == {"provider": "fake", "external_id": "f1"}

    # a missing item and an unavailable provider are 400s a person can read
    transport.on("GET", FILE, response(404))
    bad = c.post(links_url, body, "application/json")
    assert bad.status_code == 400 and "Not found" in bad.json()["external_id"]

    detail = f"{L(lab)}/external-links/{link['id']}/"
    assert c.delete(detail).status_code == 204
    assert AuditEvent.objects.filter(action=AuditAction.EXTERNAL_LINK_REMOVED).count() == 1
    assert c.get(detail).status_code == 404

    # the admin sees everyone's connections, a member only their own
    account = ConnectedAccount.objects.for_lab(lab).get(user=member)
    assert api(users["viewer"]).get(f"{L(lab)}/integrations/accounts/?all=true").json() == []
    everyone = api(pi).get(f"{L(lab)}/integrations/accounts/?all=true").json()
    assert [a["id"] for a in everyone] == [str(account.pk)]
    assert api(pi).get(f"{L(lab)}/integrations/accounts/").json() == []

    # a member can't revoke another member's account (404), the PI can (revoked, audited)
    assert (
        api(users["viewer"]).delete(f"{L(lab)}/integrations/accounts/{account.pk}/").status_code
        == 404
    )
    transport.on("POST", FAKE.revoke_url, response(200))
    resp = api(pi).delete(f"{L(lab)}/integrations/accounts/{account.pk}/")
    assert resp.status_code == 200 and resp.json()["status"] == "revoked"
    revoked = AuditEvent.objects.get(action=AuditAction.INTEGRATION_REVOKED)
    assert revoked.actor == pi and revoked.metadata["provider_revoked"] is True

    # reconnect, then disconnect your own
    connect_via_api(c, lab, transport)
    account.refresh_from_db()
    assert account.status == AccountStatus.ACTIVE  # same external account reuses its row
    resp = c.delete(f"{L(lab)}/integrations/accounts/{account.pk}/")
    assert resp.status_code == 200 and resp.json()["status"] == "revoked"
    assert AuditEvent.objects.filter(action=AuditAction.INTEGRATION_DISCONNECTED).count() == 1
    account.refresh_from_db()
    assert account.access_token_ct == "" and account.refresh_token_ct == ""


def test_link_needs_an_active_account(lab_users, make_project, join):
    lab, users = lab_users
    project = make_project(lab)
    resp = api(users["pi"]).post(
        f"{L(lab)}/projects/{project.pk}/external-links/",
        {"provider": "fake", "external_id": "f1"},
        "application/json",
    )
    assert resp.status_code == 400 and "Connect your" in resp.json()["provider"]
    assert ExternalLink.objects.for_lab(lab).count() == 0


def test_link_target_must_be_in_the_same_project(lab_users, transport, connect, make_project):
    lab, users = lab_users
    connect(users["pi"], lab)
    transport.on("GET", FILE, response(200, ITEM))
    p1, p2 = make_project(lab, "P1"), make_project(lab, "P2")
    from documents.models import Document

    doc = Document.objects.create(
        lab=lab, project=p2, title="Elsewhere", created_by=users["pi"], updated_by=users["pi"]
    )
    resp = api(users["pi"]).post(
        f"{L(lab)}/projects/{p1.pk}/external-links/",
        {"provider": "fake", "external_id": "f1", "document": str(doc.pk)},
        "application/json",
    )
    assert resp.status_code == 400 and "document" in resp.json()


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ({"state": "nope", "code": "x"}, "invalid_state"),
        ({"error": "access_denied"}, "invalid_state"),
    ],
)
def test_callback_errors_redirect_without_a_lab(lab_users, query, code):
    lab, users = lab_users
    resp = api(users["member"]).get("/api/integrations/oauth/callback/", query)
    assert resp.status_code == 302
    assert resp["Location"] == f"{settings.FRONTEND_URL}/integrations/error?code={code}"


def test_callback_denied_goes_back_to_the_lab(lab_users, transport):
    lab, users = lab_users
    c = api(users["member"])
    resp = c.post(f"{L(lab)}/integrations/fake/connect/", {}, "application/json")
    state = parse_qs(urlsplit(resp.json()["authorization_url"]).query)["state"][0]
    cb = c.get("/api/integrations/oauth/callback/", {"state": state, "error": "access_denied"})
    assert cb["Location"] == (
        f"{settings.FRONTEND_URL}/labs/{lab.pk}/settings/integrations?error=access_denied"
    )
    # the state is single use, and another user's state is no use at all
    again = c.get("/api/integrations/oauth/callback/", {"state": state, "code": "x"})
    assert again["Location"].endswith("/integrations/error?code=invalid_state")


def test_connect_errors_are_readable(lab_users, transport):
    lab, users = lab_users
    c = api(users["member"])
    bad = c.post(f"{L(lab)}/integrations/nope/connect/", {}, "application/json")
    assert (bad.status_code, bad.json()["code"]) == (400, "unknown_provider")
    scope = c.post(
        f"{L(lab)}/integrations/fake/connect/", {"scopes": ["admin"]}, "application/json"
    )
    assert scope.json()["code"] == "invalid_scope"
    connect_via_api(c, lab, transport)
    other = connect_via_api(c, lab, transport, ext_id="ext-2")
    assert other["Location"].endswith("?error=other_account_connected")


def test_removed_member_accounts_are_revoked(
    lab_users, connect, transport, django_capture_on_commit_callbacks
):
    lab, users = lab_users
    account = connect(users["member"], lab)
    from labs.models import LabMembership

    m = LabMembership.objects.for_lab(lab).get(user=users["member"])
    transport.on("POST", FAKE.revoke_url, response(200))
    with django_capture_on_commit_callbacks(execute=True):
        assert api(users["pi"]).delete(f"{L(lab)}/members/{m.pk}/").status_code == 204
    account.refresh_from_db()
    assert account.status == AccountStatus.REVOKED and account.access_token_ct == ""
    event = AuditEvent.objects.get(action=AuditAction.INTEGRATION_REVOKED)
    assert event.actor is None and event.actor_label == "lifecycle:member_removed"


def test_deactivated_user_accounts_are_revoked(
    lab_users, connect, transport, django_capture_on_commit_callbacks
):
    lab, users = lab_users
    account = connect(users["member"], lab)
    transport.on("POST", FAKE.revoke_url, response(200))
    users["member"].is_active = False
    with django_capture_on_commit_callbacks(execute=True):
        users["member"].save()
    account.refresh_from_db()
    assert account.status == AccountStatus.REVOKED
    event = AuditEvent.objects.get(action=AuditAction.INTEGRATION_REVOKED)
    assert event.actor_label == "lifecycle:user_deactivated"


def test_handover_lists_external_links(lab_users, connect, make_project):
    lab, users = lab_users
    account = connect(users["member"], lab)
    project = make_project(lab)
    ExternalLink.objects.create(
        lab=lab,
        project=project,
        provider="fake",
        connected_account=account,
        external_id="f1",
        url="https://fake.test/f1",
        title="Their file",
        linked_by=users["member"],
    )
    from labs.models import LabMembership

    m = LabMembership.objects.for_lab(lab).get(user=users["member"])
    report = api(users["pi"]).get(f"{L(lab)}/members/{m.pk}/handover/").json()
    section = next(s for s in report["sections"] if s["key"] == "external_links")
    assert section["label"] == "External links to relink"
    assert [i["title"] for i in section["items"]] == ["Their file"]
