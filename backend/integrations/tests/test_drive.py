"""Google Drive on the integrations framework (ARCHITECTURE section 9, D64, D70, D76). Every
Google call goes through the patched HTTP layer; nothing leaves the process."""

import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from audit.models import AuditEvent
from integrations import jobs, services
from integrations.http import AccountUnavailable, IntegrationError
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink
from integrations.providers import google_drive
from integrations.tests.fake import response
from projects.models import ProjectMembership
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db

DRIVE = google_drive.PROVIDER
FILE_ID = "1AbC-dEf_9"
FILE_URL = f"https://www.googleapis.com/drive/v3/files/{FILE_ID}?fields={google_drive.FIELDS}"
SCOPE = "https://www.googleapis.com/auth/drive.file"
MD5 = "d41d8cd98f00b204e9800998ecf8427e"
LONG_AGO = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)


def recheck(client, lab, url):
    """POST a check as if the last one was long ago (a check within 60 s is a 429, D78)."""
    ExternalLink.objects.for_lab(lab).update(
        last_checked_at=timezone.now() - datetime.timedelta(hours=1)
    )
    return client.post(url)


def drive_file(**over):
    return {
        "id": FILE_ID,
        "name": "raw.csv",
        "mimeType": "text/csv",
        "modifiedTime": "2030-01-01T10:00:00.000Z",
        "md5Checksum": MD5.upper(),
        "version": "7",
        "webViewLink": f"https://drive.google.com/file/d/{FILE_ID}/view",
        "trashed": False,
        **over,
    }


@pytest.fixture(autouse=True)
def drive_configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
    }
    settings.INTEGRATION_PUBLIC = {"google_drive": {"api_key": "pk", "app_id": "123"}}


@pytest.fixture
def world(lab_users, make_project):
    lab, users = lab_users
    client = Client()
    client.force_login(users["pi"])
    return lab, users, make_project(lab), client


def api(lab, path):
    return f"/api/labs/{lab.pk}/{path}"


def connect_drive(client, lab, transport, *, access="gd-access", ext_id="perm-1"):
    resp = client.post(api(lab, "integrations/google_drive/connect/"), {}, "application/json")
    assert resp.status_code == 200, resp.content
    url = resp.json()["authorization_url"]
    body = {"access_token": access, "refresh_token": "gd-refresh", "expires_in": 3600}
    transport.on("POST", DRIVE.token_url, response(200, {**body, "scope": SCOPE}))
    who = {"user": {"permissionId": ext_id, "emailAddress": "pi@example.org"}}
    transport.on("GET", DRIVE.identity_url, response(200, who))
    state = parse_qs(urlsplit(url).query)["state"][0]
    cb = client.get("/api/integrations/oauth/callback/", {"state": state, "code": "c"})
    assert cb.status_code == 302 and "connected=google_drive" in cb["Location"], cb["Location"]
    return url


def link_file(client, lab, project, **target):
    return client.post(
        api(lab, f"projects/{project.pk}/external-links/"),
        {"provider": "google_drive", "external_id": FILE_ID, **target},
        "application/json",
    )


def test_drive_end_to_end(world, transport):
    lab, users, project, client = world
    dataset = DatasetRecord.objects.create(
        lab=lab, project=project, name="Survey", version_label="v1", created_by=users["pi"]
    )

    # providers: configured, with the Picker's public settings and nothing secret
    providers = client.get(api(lab, "integrations/providers/")).json()
    drive = next(p for p in providers if p["name"] == "google_drive")
    assert drive["configured"] and drive["account"] is None
    assert drive["public_config"] == {"api_key": "pk", "app_id": "123"}
    assert "gd-secret" not in str(providers)

    # no account yet: no picker token
    assert client.get(api(lab, "integrations/google/picker-token/")).status_code == 404

    connect_drive(client, lab, transport)

    # D70: the access token only, never cached, an hour at most
    tok = client.get(api(lab, "integrations/google/picker-token/"))
    assert tok.status_code == 200 and tok["Cache-Control"] == "no-store"
    assert tok.json()["access_token"] == "gd-access"
    assert tok.json()["scope"] == SCOPE and 0 < tok.json()["expires_in"] <= 3600
    assert "gd-refresh" not in tok.content.decode()

    # link a file to the dataset record: the md5 is copied into its version fields
    transport.on("GET", FILE_URL, response(200, drive_file()))
    created = link_file(client, lab, project, dataset=str(dataset.pk))
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["url"].startswith("https://drive.google.com/") and body["version_note"] == "copied"
    assert body["status"] == "ok" and body["provider_label"] == "Google Drive"
    dataset.refresh_from_db()
    assert dataset.checksum == f"md5:{MD5}" and dataset.version_label == "v1"
    assert AuditEvent.objects.filter(action="dataset.updated", target_id=str(dataset.pk)).exists()

    # the lineage response carries the link and its status on the dataset node
    def node_links():
        graph = client.get(api(lab, f"projects/{project.pk}/lineage/")).json()
        node = next(n for n in graph["nodes"] if n["id"] == f"dataset:{dataset.pk}")
        return node["meta"]["external_links"]

    assert [(x["title"], x["status"]) for x in node_links()] == [("raw.csv", "ok")]

    # the file changes: refresh shows "changed since linked"
    check = api(lab, f"external-links/{body['id']}/check/")
    changed_file = drive_file(
        md5Checksum="a" * 32, version="8", modifiedTime="2030-01-02T10:00:00Z"
    )
    transport.on("GET", FILE_URL, response(200, changed_file))
    changed = recheck(client, lab, check).json()
    assert changed["changed_since_linked"] and changed["status"] == "changed"
    assert node_links()[0]["status"] == "changed"
    dataset.refresh_from_db()
    assert dataset.checksum == f"md5:{MD5}"  # D20/D76: a new version is a new row

    # accepting records the new values as seen; nothing else moves
    accepted = client.post(api(lab, f"external-links/{body['id']}/accept-change/")).json()
    assert accepted["status"] == "ok" and accepted["linked_version"] == "8"
    assert AuditEvent.objects.filter(action="external_link.change_accepted").exists()

    # the file is deleted (404): "no longer available"
    transport.on("GET", FILE_URL, response(404, {"error": {"code": 404}}))
    gone = recheck(client, lab, check).json()
    assert gone["status"] == "unavailable" and gone["unavailable_since"]
    assert node_links()[0]["status"] == "unavailable"

    # it comes back: cleared
    transport.on("GET", FILE_URL, response(200, changed_file))
    assert recheck(client, lab, check).json()["status"] == "ok"


def test_never_broad_scopes_and_never_file_contents(world, transport):
    lab, users, project, client = world
    url = connect_drive(client, lab, transport)
    assert parse_qs(urlsplit(url).query)["scope"] == [SCOPE]
    assert DRIVE.scopes == (SCOPE,)
    broad = (
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.readonly",
    )
    for scope in broad:  # the registry refuses anything else
        resp = client.post(
            api(lab, "integrations/google_drive/connect/"), {"scopes": [scope]}, "application/json"
        )
        assert resp.status_code == 400 and resp.json()["code"] == "invalid_scope"
    transport.on(
        "GET", FILE_URL, response(200, drive_file(mimeType="application/vnd.google-apps.document"))
    )
    link_id = link_file(client, lab, project).json()["id"]
    recheck(client, lab, api(lab, f"external-links/{link_id}/check/"))
    transport.on("POST", DRIVE.revoke_url, response(200, {}))
    services.disconnect(ConnectedAccount.objects.for_lab(lab).get(), actor=users["pi"])
    urls = [u for _, u, _ in transport.calls]
    for u in urls:
        assert "alt=media" not in u and "/export" not in u and "download" not in u.lower(), u
        if "/files/" in u:  # only the metadata read, with the fixed field list
            assert u == FILE_URL
    assert DRIVE.revoke_url in urls  # disconnect uses Google's revoke endpoint
    assert all("alt" not in (kw.get("params") or {}) for _, _, kw in transport.calls)


def test_ids_are_checked(world, transport):
    lab, _, project, client = world
    connect_drive(client, lab, transport)
    for bad in ("a/b", "../x", "a?alt=media", "a b", "a.b", ""):
        resp = client.post(
            api(lab, f"projects/{project.pk}/external-links/"),
            {"provider": "google_drive", "external_id": bad},
            "application/json",
        )
        assert resp.status_code == 400, bad
    assert not [c for c in transport.calls if "/files/" in c[1]]


def test_version_copy_rule(world, transport):
    """D76: copy while empty; never overwrite; a file with no md5 falls back to its version."""
    lab, users, project, client = world
    connect_drive(client, lab, transport)

    def record(name, checksum=""):
        return DatasetRecord.objects.create(
            lab=lab,
            project=project,
            name=name,
            version_label="v1",
            checksum=checksum,
            created_by=users["pi"],
        )

    def link(dataset, **file):
        transport.on("GET", FILE_URL, response(200, drive_file(**file)))
        return link_file(client, lab, project, dataset=str(dataset.pk)).json()["version_note"]

    own = record("kept", "sha256:" + "ab" * 32)
    assert link(own, md5Checksum=MD5) == "kept"
    own.refresh_from_db()
    assert own.checksum == "sha256:" + "ab" * 32
    assert link(record("same", f"md5:{MD5}")) == "same"
    native = record("native")
    assert link(native, md5Checksum=None) == "copied"
    native.refresh_from_db()
    assert native.checksum == "drive-version:7"
    bare = record("none")
    assert link(bare, md5Checksum=None, version="") == "none"
    bare.refresh_from_db()
    assert bare.checksum == ""


def test_unavailable_and_transient_answers(world, transport):
    lab, _, project, client = world
    connect_drive(client, lab, transport)
    account = ConnectedAccount.objects.for_lab(lab).get()
    forbidden = response(403, {"error": {"errors": [{"reason": "forbidden"}]}})
    for reply in (
        response(404),
        forbidden,
        response(403, {}),
        response(200, drive_file(trashed=True)),
    ):
        transport.on("GET", FILE_URL, reply)
        assert DRIVE.fetch_item(account, FILE_ID) is None
    throttled = response(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}]}})
    for reply in (
        throttled,
        response(418),
        response(200, {"name": "x"}),
    ):
        transport.on("GET", FILE_URL, reply)
        with pytest.raises(IntegrationError):
            DRIVE.fetch_item(account, FILE_ID)
    # linking a missing file is a clear error, not a crash
    transport.on("GET", FILE_URL, response(404))
    assert link_file(client, lab, project).status_code == 400
    # a transient failure on refresh is a 502 and changes nothing
    transport.on("GET", FILE_URL, response(200, drive_file()))
    link_id = link_file(client, lab, project).json()["id"]
    transport.on("GET", FILE_URL, response(500))
    assert recheck(client, lab, api(lab, f"external-links/{link_id}/check/")).status_code == 502
    assert ExternalLink.objects.for_lab(lab).get().unavailable_since is None


def test_daily_job_uses_linker_token_and_skips_inactive(world, transport, monkeypatch):
    lab, users, project, client = world
    monkeypatch.setattr(services, "CHECK_PAUSE", 0)
    connect_drive(client, lab, transport)
    transport.on("GET", FILE_URL, response(200, drive_file()))
    link = link_file(client, lab, project).json()
    gone = ConnectedAccount.objects.create(
        lab=lab,
        user=users["member"],
        provider="google_drive",
        external_account_id="p2",
        status=AccountStatus.EXPIRED,
        connected_at=LONG_AGO,
    )
    stranded = ExternalLink.objects.create(
        lab=lab,
        project=project,
        provider="google_drive",
        external_id="zz",
        url="https://drive.google.com/x",
        title="Stranded",
        linked_by=users["member"],
        connected_account=gone,
    )
    transport.on("GET", FILE_URL, response(200, drive_file(version="9")))
    before = len(transport.calls)
    assert jobs.check_links() == {"checked": 1, "skipped": 1, "failed": 0}
    assert transport.sent("GET", FILE_URL)[-1]["headers"]["Authorization"] == "Bearer gd-access"
    assert len(transport.calls) == before + 1  # the stranded link made no call
    stranded.refresh_from_db()
    assert stranded.last_checked_at is None
    listed = client.get(api(lab, f"projects/{project.pk}/external-links/")).json()
    by_id = {x["id"]: x for x in listed}
    assert by_id[str(stranded.pk)]["check_blocked"] == "linker_inactive"
    assert by_id[link["id"]]["check_blocked"] == "" and by_id[link["id"]]["status"] == "changed"
    # one failing link never stops the job
    transport.on("GET", FILE_URL, response(500))
    assert jobs.check_links()["failed"] == 1
    # an account that went inactive since the list was read is left alone
    row = ExternalLink.objects.for_lab(lab).get(pk=link["id"])
    ConnectedAccount.objects.for_lab(lab).filter(pk=row.connected_account_id).update(
        status="expired"
    )
    stale = row.last_checked_at
    assert (
        services.check_link(ExternalLink.objects.for_lab(lab).get(pk=row.pk)).last_checked_at
        == stale
    )


def test_check_without_provider_support_is_a_noop(world):
    lab, users, project, _ = world
    link = ExternalLink.objects.create(
        lab=lab,
        project=project,
        provider="web",
        external_id="x",
        url="https://x.test",
        title="t",
        linked_by=users["pi"],
    )
    assert services.check_link(link) is link and link.last_checked_at is None


# ---- security review (D78)


def _member_link(lab, users, project, transport):
    """A Drive link made by the `member`, whose account is active."""
    ProjectMembership.objects.create(project=project, user=users["member"], role="contributor")
    member = Client()
    member.force_login(users["member"])
    connect_drive(member, lab, transport, ext_id="perm-m")
    transport.on("GET", FILE_URL, response(200, drive_file()))
    return member, link_file(member, lab, project).json()


def test_check_is_blocked_once_the_linker_loses_project_access(world, transport):
    lab, users, project, client = world
    _, link = _member_link(lab, users, project, transport)
    ProjectMembership.objects.for_lab(lab).filter(
        user=users["member"]
    ).delete()  # account untouched
    row = ExternalLink.objects.for_lab(lab).get(pk=link["id"])
    before = len(transport.calls)
    assert jobs.check_links() == {"checked": 0, "skipped": 1, "failed": 0}
    resp = recheck(client, lab, api(lab, f"external-links/{row.pk}/check/"))
    assert resp.status_code == 200 and resp.json()["check_blocked"] == "linker_access_lost"
    assert len(transport.calls) == before  # the linker's token was never used
    assert ExternalLink.objects.for_lab(
        lab
    ).get().last_checked_at < timezone.now() - datetime.timedelta(minutes=30)


def test_check_is_refused_within_a_minute_and_per_user(world, transport, monkeypatch):
    lab, users, project, client = world
    connect_drive(client, lab, transport)
    transport.on("GET", FILE_URL, response(200, drive_file()))
    url = api(lab, f"external-links/{link_file(client, lab, project).json()['id']}/check/")
    resp = client.post(url)  # the link was just checked at creation
    assert resp.status_code == 429 and 0 < int(resp["Retry-After"]) <= 61
    assert recheck(client, lab, url).status_code == 200
    assert client.post(url).status_code == 429  # and again straight after
    # the per-user throttle (scope link_check) applies on top
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"link_check": "2/hour"})
    cache.clear()
    codes = [recheck(client, lab, url).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def _grant(transport, scope):
    body = {"access_token": "gd-access", "refresh_token": "gd-refresh", "expires_in": 3600}
    transport.on("POST", DRIVE.token_url, response(200, {**body, "scope": scope}))


def test_connect_does_not_ask_google_to_merge_earlier_grants(world, transport):
    lab, users, project, client = world
    url = client.post(
        api(lab, "integrations/google_drive/connect/"), {}, "application/json"
    ).json()["authorization_url"]
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == [SCOPE] and "include_granted_scopes" not in query


def test_extra_granted_scopes_are_refused_on_connect_and_refresh(world, transport):
    lab, users, project, client = world
    url = client.post(
        api(lab, "integrations/google_drive/connect/"), {}, "application/json"
    ).json()["authorization_url"]
    _grant(transport, f"{SCOPE} https://www.googleapis.com/auth/drive")
    transport.on("GET", DRIVE.identity_url, response(200, {"user": {"permissionId": "p"}}))
    state = parse_qs(urlsplit(url).query)["state"][0]
    cb = client.get("/api/integrations/oauth/callback/", {"state": state, "code": "c"})
    assert "error=unexpected_scope" in cb["Location"]
    assert not ConnectedAccount.objects.for_lab(lab).exists()  # discarded, never stored
    assert not [c for c in transport.calls if c[1] == DRIVE.revoke_url]  # and not revoked (D68)

    # a refresh that comes back with a merged scope wipes the tokens
    connect_drive(client, lab, transport)
    account = ConnectedAccount.objects.for_lab(lab).get()
    _grant(transport, f"{SCOPE} openid email")
    with pytest.raises(AccountUnavailable):
        services.refresh_access_token(account)
    assert account.status == AccountStatus.ERROR and account.access_token_ct == ""
    event = AuditEvent.objects.get(action="integration.refresh_failed")
    assert event.metadata["reason"] == "unexpected_scope"


def test_picker_token_reports_granted_scopes_audits_and_throttles(world, transport, monkeypatch):
    lab, users, project, client = world
    connect_drive(client, lab, transport)
    ConnectedAccount.objects.for_lab(lab).update(granted_scopes=[SCOPE, "x.read"])
    url = api(lab, "integrations/google/picker-token/")
    tok = client.get(url)
    assert tok.json()["scope"] == f"{SCOPE} x.read"
    event = AuditEvent.objects.get(action="integration.picker_token_issued")
    assert event.actor_id == users["pi"].pk and event.metadata == {"provider": "google_drive"}
    assert "gd-access" not in str(list(AuditEvent.objects.values()))
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"picker_token": "2/hour"})
    cache.clear()
    assert [client.get(url).status_code for _ in range(3)] == [200, 200, 429]


@pytest.mark.parametrize(
    ("mime", "editor"),
    [
        ("application/vnd.google-apps.document", f"document/d/{FILE_ID}/edit"),
        ("application/vnd.google-apps.spreadsheet", f"spreadsheets/d/{FILE_ID}/edit"),
        ("application/vnd.google-apps.presentation", None),
        ("text/csv", None),
    ],
)
def test_only_docs_and_sheets_get_an_editor_frame(world, transport, mime, editor):
    lab, users, project, client = world
    connect_drive(client, lab, transport)
    transport.on(
        "GET",
        FILE_URL,
        response(200, drive_file(mimeType=mime, webViewLink="https://docs.google.com/x")),
    )
    link = link_file(client, lab, project).json()
    assert link["editor_url"] == (f"https://docs.google.com/{editor}" if editor else "")
    # a file that is gone has nothing to open
    ExternalLink.objects.for_lab(lab).update(unavailable_since=timezone.now())
    assert (
        client.get(api(lab, f"projects/{project.pk}/external-links/")).json()[0]["editor_url"] == ""
    )


def test_link_hosts_are_pinned_to_google_and_never_rendered_otherwise(world, transport):
    lab, users, project, client = world
    connect_drive(client, lab, transport)
    for bad in (
        "https://evil.example/file",
        "http://drive.google.com/file",
        "https://drive.google.com.evil.example/x",
        "https://drive.google.com:8443/x",
        "javascript:alert(1)",
    ):
        transport.on("GET", FILE_URL, response(200, drive_file(webViewLink=bad)))
        resp = link_file(client, lab, project)
        assert resp.status_code == 400 and "url" in resp.json(), bad
    assert not ExternalLink.objects.for_lab(lab).exists()
    transport.on("GET", FILE_URL, response(200, drive_file()))
    link = link_file(client, lab, project).json()
    assert link["url"].startswith("https://drive.google.com/")
    # a stored link that fails the pin (older data) is blanked on the way out
    ExternalLink.objects.for_lab(lab).update(url="https://evil.example/x")
    listed = client.get(api(lab, f"projects/{project.pk}/external-links/")).json()
    assert listed[0]["url"] == ""
