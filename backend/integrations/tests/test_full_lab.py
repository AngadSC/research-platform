"""Every integration at full-lab scale: the seeded 20-person, 9-project lab (core.seed_full) with
every provider connected, links in every state, the Google Chat bridge, calendar sync and video
meetings. All provider HTTP is mocked at the transport; nothing leaves the process."""

import dataclasses
import hashlib
import hmac
import json
import time
from collections import Counter
from datetime import timedelta
from urllib.parse import quote, unquote, urlsplit

import pytest
import requests
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from core.seed_full import integrations as seed_integrations
from core.seed_full import people
from integrations import http, jobs, registry, services
from integrations.models import (
    TARGET_FIELDS,
    AccountStatus,
    ConnectedAccount,
    ExternalLink,
    Webhook,
)
from integrations.providers import (
    AuthType,
    google_calendar,
    google_chat,
    google_drive,
    monday,
    todoist,
    trello,
    zoom,
)
from integrations.tests.fake import FakeTransport, response
from labs import google_chat as chat_sync
from labs import services as lab_services
from labs import video_calendar
from labs.models import (
    ChatSource,
    GoogleCalendarSync,
    GoogleChatBridge,
    LabChatMessage,
    LabMembership,
    Meeting,
    SyncedEvent,
)
from projects import handover
from projects.models import Task

pytestmark = pytest.mark.django_db

ZOOM_SECRET = "zoom-secret-token"
REAL = {"google_drive", "zenodo", "box", "figshare"}  # these run their own fetch_item
CHAT = google_chat.API
LAB_SPACE = "spaces/FAKELABCHAT01"
CHAT_MESSAGES = f"{CHAT}/{LAB_SPACE}/messages"
EVENTS = f"{google_calendar.API}/calendars/primary/events"
ZOOM_MEETINGS = f"{zoom.API}/users/me/meetings"


# ---------------------------------------------------------------- the lab and its remote world


@pytest.fixture(autouse=True)
def configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
        "google_chat": {"client_id": "gc-client", "client_secret": "gc-secret"},
        "zoom": {"client_id": "zm-client", "client_secret": "zm-secret"},
    }
    settings.INTEGRATION_OPTIONAL_PROVIDERS = ["todoist", "trello", "monday"]
    settings.INTEGRATION_ZOOM_WEBHOOK_SECRET = ZOOM_SECRET


@pytest.fixture(autouse=True)
def committed(monkeypatch):
    """Run on_commit work at once, as a real commit would (chat relay, provider revokes)."""
    monkeypatch.setattr(
        "django.db.transaction.on_commit", lambda func, using=None, robust=False: func()
    )


@pytest.fixture
def seeded():
    """The lab exactly as the seed leaves it: no tokens anywhere."""
    ctx = people.build("x")
    seed_integrations.seed(ctx)
    return ctx


@pytest.fixture
def full(seeded):
    """The same lab with canary tokens on every active account, so calls and leaks show up."""
    for row in ConnectedAccount.objects.for_lab(seeded.lab).filter(status=AccountStatus.ACTIVE):
        oauth = registry.PROVIDERS[row.provider].auth_type == AuthType.OAUTH2
        row.set_tokens(
            access=access_token(row),
            refresh=f"CANARY-refresh-{row.pk}",
            expires_at=timezone.now() + timedelta(hours=1) if oauth else None,
        )
        row.save()
    return seeded


def access_token(row):
    return f"CANARY-access-{row.pk}"


def account(ctx, who, provider):
    return ConnectedAccount.objects.for_lab(ctx.lab).get(user=ctx.people[who], provider=provider)


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def lab_url(ctx, path):
    return f"/api/labs/{ctx.lab.pk}/{path}"


BODIES = {
    "stub": lambda p, i, v: {
        "title": f"Remote {i}",
        "url": f"https://{p}.example.invalid/{i}",
        "modified": "2030-01-01T00:00:00Z",
        "version": v,
    },
    "google_drive": lambda p, i, v: {
        "id": i,
        "name": "Remote file",
        "mimeType": "text/csv",
        "modifiedTime": "2030-01-01T10:00:00.000Z",
        "version": v,
        "webViewLink": f"https://drive.google.com/file/d/{i}/view",
        "trashed": False,
    },
    "zenodo": lambda p, i, v: {
        "metadata": {"title": "Remote record", "version": v},
        "files": [],
        "links": {"html": f"https://zenodo.org/records/{i}"},
        "updated": "2030-01-01T10:00:00+00:00",
    },
    "figshare": lambda p, i, v: {
        "title": "Remote article",
        "url_public_html": f"https://figshare.com/articles/{i}",
        "modified_date": "2030-01-01T10:00:00Z",
        "version": v,
        "files": [],
    },
    "box": lambda p, i, v: {
        "id": i,
        "name": "Remote box file",
        "modified_at": "2030-01-01T10:00:00+00:00",
        "etag": v,
        "item_status": "active",
    },
}


class Remote(FakeTransport):
    """Every provider's item endpoint, answering by what the test says the remote now holds.
    `mode[(provider, id)]` is ok | changed | gone (default ok), `down[provider]` is "503" or
    "timeout", and an access token in `dead` is answered 401. Anything else goes to the usual
    routes (`on`) and `prefix` handlers, and an unexpected request fails the test."""

    def __init__(self):
        super().__init__()
        self.mode, self.down, self.dead, self.prefix = {}, {}, set(), []

    def when(self, method, prefix, reply):
        self.prefix.append((method, prefix, reply))

    @staticmethod
    def item(host, path):
        if path.startswith("/fake-item/"):
            provider, _, ext_id = path.removeprefix("/fake-item/").partition("/")
            return provider, unquote(ext_id)
        for provider, h, start in [
            ("google_drive", "www.googleapis.com", "/drive/v3/files/"),
            ("zenodo", "zenodo.org", "/api/records/"),
            ("figshare", "api.figshare.com", "/v2/articles/"),
            ("box", "api.box.com", "/2.0/files/"),
        ]:
            if host == h and path.startswith(start):
                return provider, unquote(path.removeprefix(start))
        return None

    def request(self, method, url, **kwargs):
        parts = urlsplit(url)
        hit = self.item(parts.hostname, parts.path) if method == "GET" else None
        if hit is None:
            for m, prefix, reply in self.prefix:
                if m == method and url.startswith(prefix):
                    self.calls.append((method, url, kwargs))
                    return reply(kwargs) if callable(reply) else reply
            return super().request(method, url, **kwargs)
        self.calls.append((method, url, kwargs))
        provider, ext_id = hit
        auth = (kwargs.get("headers") or {}).get("Authorization", "")
        if any(token in auth for token in self.dead):
            return response(401, {})
        if self.down.get(provider) == "timeout":
            raise requests.ConnectionError("timed out")
        if self.down.get(provider):
            return response(503, {})
        mode = self.mode.get((provider, ext_id), "ok")
        if mode == "gone":
            return response(404, {})
        body = BODIES.get(provider, BODIES["stub"])
        return response(200, body(provider, ext_id, "v2" if mode == "changed" else "v1"))

    def asked(self, token):
        """Requests that carried this access token."""
        return [
            c for c in self.calls if token in (c[2].get("headers") or {}).get("Authorization", "")
        ]


def stub_fetch(name):
    """A provider's `fetch_item` that asks its own host for one item through the real HTTP layer
    (host allowlist, retries, 5xx and timeouts), so the job's behaviour is what is tested; each
    provider's own parsing has its own tests."""

    def fetch(acct, external_id):
        provider = registry.PROVIDERS[name]
        host = acct.instance_host if provider.needs_instance_url else sorted(provider.api_hosts)[0]
        resp = http.send(
            "GET",
            f"https://{host}/fake-item/{name}/{quote(external_id, safe='')}",
            provider=provider,
            account=acct,
        )
        if resp.status_code in (403, 404):
            return None
        if resp.status_code != 200:
            raise http.IntegrationError("the provider did not return the item")
        data = resp.json()
        return {
            "title": data["title"],
            "url": data["url"],
            "mime_type": "",
            "modified_at": None,
            "version": data["version"],
            "checksum": "",
        }

    return fetch


@pytest.fixture
def remote(monkeypatch, transport):
    """The remote world, and every provider that has `fetch_item` (bar the REAL ones) reading it."""
    world = Remote()
    monkeypatch.setattr(http, "_session", world)
    for name in registry.ENABLED:
        provider = registry.PROVIDERS[name]
        if provider.fetch_item and name not in REAL:
            new = dataclasses.replace(provider, fetch_item=stub_fetch(name))
            monkeypatch.setitem(registry.PROVIDERS, name, new)
    return world


# ---------------------------------------------------------------- Part 1: the seed itself


def link_kind(link):
    return next((f for f in TARGET_FIELDS if getattr(link, f"{f}_id")), "project")


def test_the_seed_connects_every_provider_in_every_state(seeded):
    lab = seeded.lab
    accounts = ConnectedAccount.objects.for_lab(lab)
    links = ExternalLink.objects.for_lab(lab)
    n_accounts = Counter(accounts.values_list("provider", flat=True))
    n_links = Counter(links.values_list("provider", flat=True))
    for name in registry.ENABLED:
        provider = registry.PROVIDERS[name]
        if provider.needs_account:
            assert n_accounts[name] >= 2, name
        if provider.fetch_item or provider.auth_type == AuthType.LINK_ONLY:
            assert n_links[name] >= 1, name
    assert {a.status for a in accounts} == set(AccountStatus.values)
    assert {link.status for link in links} == {"ok", "changed", "unavailable"}
    assert {link_kind(link) for link in links} == {"project", *TARGET_FIELDS}
    assert {link.project.name for link in links} == {p.name for p in seeded.projects.values()}

    for link in links:
        provider = registry.PROVIDERS[link.provider]
        assert link_kind(link) in provider.link_targets, link
        assert provider.valid_external_id(link.external_id), link
        assert urlsplit(link.url).hostname.endswith(".invalid")
        assert (link.connected_account_id is not None) == provider.needs_account, link
    for row in accounts:
        assert not (row.access_token_ct or row.refresh_token_ct or row.token_expires_at), row
        if row.instance_url:  # Qualtrics insists on a qualtrics.com address
            assert row.instance_host.endswith((".invalid", ".qualtrics.com"))
        if row.status == AccountStatus.REVOKED:
            assert row.external_account_id.startswith("revoked:") and not row.external_email

    # the lab-level bits
    assert GoogleChatBridge.objects.for_lab(lab).filter(project__isnull=True).count() == 1
    assert GoogleChatBridge.objects.for_lab(lab).filter(project__isnull=False).count() == 1
    assert LabChatMessage.objects.for_lab(lab).filter(source=ChatSource.GOOGLE_CHAT).count() == 3
    assert GoogleCalendarSync.objects.for_lab(lab).count() == 4
    assert SyncedEvent.objects.for_lab(lab).exists()
    meetings = Meeting.objects.for_lab(lab)
    assert {m.video_provider for m in meetings} == {"zoom", "google_meet", ""}
    hooks = Webhook.objects.for_lab(lab)
    assert hooks.count() == 3 and hooks.filter(is_active=False).count() == 1
    assert all(h.host.endswith(".invalid") for h in hooks)


# ---------------------------------------------------------------- the daily link check


def assign_modes(remote, lab):
    """What the remote holds now, by a fixed rule from each link's state before the job: some
    up-to-date links changed or vanished, some changed ones were reverted, some gone came back."""
    seen = Counter()
    for link in ExternalLink.objects.for_lab(lab).order_by("title", "id"):
        i = seen[link.status]
        seen[link.status] += 1
        if link.status == "ok":
            mode = "changed" if i % 5 == 4 else "gone" if i % 7 == 6 else "ok"
        elif link.status == "changed":
            mode = "ok" if i % 2 == 0 else "changed"
        else:
            mode = "ok" if i % 2 == 0 else "gone"
        key = (link.provider, link.external_id)
        assert key not in remote.mode, key  # ids are unique, so a mode is one link's
        remote.mode[key] = mode


def test_the_daily_check_over_every_link_of_every_provider(full, remote):
    lab = full.lab
    assign_modes(remote, lab)
    remote.down = {"box": "503", "zotero": "timeout"}  # two services failing outright
    before = {link.pk: link for link in ExternalLink.objects.for_lab(lab)}
    was = {pk: (link.status, link.last_checked_at) for pk, link in before.items()}
    expect = {"checked": 0, "skipped": 0, "failed": 0}
    outcome = {}
    for link in before.values():
        provider = registry.PROVIDERS[link.provider]
        account_ = link.connected_account
        if provider.fetch_item is None or (provider.needs_account and account_ is None):
            outcome[link.pk] = None  # never selected (Overleaf)
        elif account_ and account_.status != AccountStatus.ACTIVE:
            expect["skipped"] += 1
            outcome[link.pk] = None  # the linker needs to reconnect: left as it was
        elif link.provider in remote.down:
            expect["failed"] += 1
            outcome[link.pk] = None
        else:
            expect["checked"] += 1
            mode = remote.mode[(link.provider, link.external_id)]
            outcome[link.pk] = {"ok": "ok", "changed": "changed", "gone": "unavailable"}[mode]

    with CaptureQueriesContext(connection) as queries:
        result = jobs.check_lab_links_task(str(lab.pk))
    selected = sum(expect.values())
    print(f"\nQUERIES check_lab_links: {len(queries)} for {selected} links, {len(before)} in lab")

    assert result == expect
    assert expect["failed"] >= 5 and expect["skipped"] >= 8 and expect["checked"] >= 30
    for pk, link in before.items():
        link.refresh_from_db()
        if outcome[pk] is None:
            # a failing service, an expired linker and a link-only provider change nothing
            assert (link.status, link.last_checked_at) == was[pk], (link.provider, link.title)
        else:
            assert link.status == outcome[pk], (link.provider, link.external_id)
            assert link.last_checked_at > timezone.now() - timedelta(minutes=5)
    # the failures of box and zotero did not stop anyone else
    done_providers = {
        link.provider for link in ExternalLink.objects.for_lab(lab) if outcome[link.pk] is not None
    }
    assert {"google_drive", "github", "gitlab", "zenodo", "redcap", "onedrive"} <= done_providers
    assert not done_providers & {"box", "zotero"}
    # one job, a sane number of queries per link
    assert len(queries) <= 20 * selected + 50


def test_the_scheduled_entry_point_queues_one_task_per_lab(full, remote, make_lab):
    make_lab("Another lab")
    assign_modes(remote, full.lab)
    assert jobs.check_links_by_lab() == 2  # eager celery: both ran inline
    assert ExternalLink.objects.for_lab(full.lab).filter(last_checked_at__gte=full.now).exists()


def test_one_lab_failing_does_not_stop_the_others(full, remote, make_lab, monkeypatch):
    other = make_lab("Other lab")
    real = services.check_lab_links

    def flaky(lab):
        if lab.pk == other.pk:
            raise RuntimeError("boom")
        return real(lab)

    monkeypatch.setattr(services, "check_lab_links", flaky)
    total = services.check_all_links()
    assert total["failed"] == 1 and total["checked"] >= 30


def test_an_account_the_provider_stops_accepting_is_marked_and_the_rest_carry_on(full, remote):
    lab = full.lab
    drive, github = account(full, "aisha", "google_drive"), account(full, "tomas", "github")
    remote.dead = {access_token(drive), access_token(github)}
    remote.on("POST", google_drive.PROVIDER.token_url, response(400, {"error": "invalid_grant"}))
    own_links = ExternalLink.objects.for_lab(lab).filter(connected_account__in=[drive, github])
    was = {link.pk: link.status for link in own_links}
    assert len(was) >= 3
    jobs.check_lab_links_task(str(lab.pk))

    for row in (drive, github):
        row.refresh_from_db()
        assert row.status == AccountStatus.EXPIRED and not (
            row.access_token_ct or row.refresh_token_ct
        )
        assert (
            Notification.objects.for_lab(lab)
            .filter(lab=lab, recipient=row.user, kind=NotificationKind.INTEGRATION_ISSUE)
            .count()
            == 1
        )
    assert AuditEvent.objects.filter(action=AuditAction.INTEGRATION_REFRESH_FAILED).count() == 2
    assert {
        link.pk: link.status for link in ExternalLink.objects.for_lab(lab).filter(pk__in=was)
    } == was
    # everyone else was still checked
    assert (
        ExternalLink.objects.for_lab(lab)
        .filter(provider="google_drive", linked_by=full.people["pi"], last_checked_at__gte=full.now)
        .exists()
    )


def test_a_refused_account_is_not_asked_again_for_its_other_links(full, remote):
    drive = account(full, "aisha", "google_drive")  # two Drive links
    remote.dead = {access_token(drive)}
    remote.on("POST", google_drive.PROVIDER.token_url, response(400, {"error": "invalid_grant"}))
    jobs.check_lab_links_task(str(full.lab.pk))
    assert len(remote.asked(access_token(drive))) == 1


def test_a_tokenless_seeded_lab_sends_nothing_to_providers_with_an_empty_credential(seeded, remote):
    services.check_lab_links(seeded.lab)
    empty = [
        c for c in remote.calls if (c[2].get("headers") or {}).get("Authorization") == "Bearer "
    ]
    assert not empty, f"{len(empty)} requests went out with an empty bearer token"


# ---------------------------------------------------------------- who sees what


def test_each_person_sees_their_own_accounts_only(full):
    everything = {
        str(pk) for pk in ConnectedAccount.objects.for_lab(full.lab).values_list("pk", flat=True)
    }
    url = lab_url(full, "integrations/accounts/")
    for key, user in full.people.items():
        mine = {
            str(pk)
            for pk in ConnectedAccount.objects.for_lab(full.lab)
            .filter(user=user)
            .values_list("pk", flat=True)
        }
        manager = full.roles[key] in ("pi", "lab_admin")
        plain = api(user).get(url)
        wide = api(user).get(url + "?all=true")
        for resp, expected in ((plain, mine), (wide, everything if manager else mine)):
            assert resp.status_code == 200, (key, resp.status_code)
            assert {a["id"] for a in resp.json()} == expected, key
        # the provider list carries only the requester's own account per provider
        for entry in api(user).get(lab_url(full, "integrations/providers/")).json():
            if entry["account"]:
                assert entry["account"]["id"] in mine, (key, entry["name"])
        for other in [k for k in full.people if k != key][:2]:
            assert not (mine & {a["id"] for a in api(full.people[other]).get(url).json()})


def link_body(external_id, **extra):
    return {"provider": "google_drive", "external_id": external_id, **extra}


def test_linking_needs_edit_access_and_your_own_connected_account(full, remote):
    sleep, ageing = full.projects["sleep"], full.projects["ageing"]
    url = lab_url(full, f"projects/{sleep.pk}/external-links/")
    # a project lead with Drive connected can link, with their own account
    made = api(full.people["priya"]).post(url, link_body("brand-new-file"), format="json")
    assert made.status_code == 201, made.content
    assert ExternalLink.objects.for_lab(full.lab).get(
        pk=made.json()["id"]
    ).connected_account == account(full, "priya", "google_drive")
    # viewers can't, even one with an active Drive account of their own
    viewer_url = lab_url(full, f"projects/{ageing.pk}/external-links/")
    for who in ("ingrid", "owen"):
        assert (
            api(full.people[who])
            .post(viewer_url, link_body("another-file"), format="json")
            .status_code
            == 403
        )
    owen = account(full, "owen", "google_drive")
    assert owen.status == AccountStatus.ACTIVE
    # a lab member who is not on that project can't
    assert api(full.people["noah"]).post(url, link_body("a-file"), format="json").status_code in (
        403,
        404,
    )
    # a revoked or expired account has to be reconnected first
    for who in ("ravi", "liam"):
        project = full.projects["fmri" if who == "ravi" else "mouse"]
        bad = api(full.people[who]).post(
            lab_url(full, f"projects/{project.pk}/external-links/"),
            link_body("x-file"),
            format="json",
        )
        assert bad.status_code == 400 and "Connect your Google Drive" in bad.content.decode(), who
    assert (
        ExternalLink.objects.for_lab(full.lab)
        .filter(external_id__in=["another-file", "a-file", "x-file"])
        .count()
        == 0
    )


def test_another_lab_sees_none_of_it(full, remote, make_lab, make_user, join):
    other = make_lab("Another lab")
    outsider = make_user()
    join(outsider, other, "pi")
    join(full.people["pi"], other, "pi")  # one person in both labs
    link = ExternalLink.objects.for_lab(full.lab).first()
    account_ = ConnectedAccount.objects.for_lab(full.lab).first()
    mine = f"/api/labs/{other.pk}/"
    ours = [
        lab_url(full, "integrations/providers/"),
        lab_url(full, "integrations/accounts/?all=true"),
        lab_url(full, f"projects/{link.project_id}/external-links/"),
        lab_url(full, f"external-links/{link.pk}/"),
        lab_url(full, "webhooks/"),
        lab_url(full, "chat/google/"),
        lab_url(full, "chat/messages/"),
    ]
    for url in ours:
        assert api(outsider).get(url).status_code in (403, 404), url
    # the check and delete endpoints of our lab are closed to them too
    assert api(outsider).post(lab_url(full, f"external-links/{link.pk}/check/")).status_code in (
        403,
        404,
    )
    assert api(outsider).delete(
        lab_url(full, f"integrations/accounts/{account_.pk}/")
    ).status_code in (403, 404)
    # asking our ids through their own lab's address finds nothing
    for tail in (f"external-links/{link.pk}/", f"integrations/accounts/{account_.pk}/"):
        assert api(outsider).get(mine + tail).status_code in (403, 404, 405)
    # their own lab shows no accounts, even to the person who has accounts in ours
    for user in (outsider, full.people["pi"]):
        assert api(user).get(mine + "integrations/accounts/?all=true").json() == []
        entries = api(user).get(mine + "integrations/providers/").json()
        assert all(e["account"] is None for e in entries)
    assert ConnectedAccount.objects.for_lab(other).count() == 0
    assert ExternalLink.objects.for_lab(other).count() == 0
    assert not Webhook.objects.for_lab(other).exists()


# ---------------------------------------------------------------- people leaving


def test_removing_a_member_revokes_their_connections_and_keeps_their_links(full, remote):
    lab, eli = full.lab, full.people["eli"]
    eli_accounts = ConnectedAccount.objects.for_lab(lab).filter(user=eli)
    assert eli_accounts.filter(status=AccountStatus.ACTIVE).count() >= 4
    eli_links = set(
        ExternalLink.objects.for_lab(lab).filter(linked_by=eli).values_list("pk", flat=True)
    )
    assert len(eli_links) >= 8
    others = {a.pk: a.status for a in ConnectedAccount.objects.for_lab(lab).exclude(user=eli)}
    tokens = {access_token(a) for a in eli_accounts if a.status == AccountStatus.ACTIVE}
    membership = LabMembership.objects.for_lab(lab).get(user=eli)

    # before: the handover report names every link he made, so someone can relink them
    report = handover.build_report(requester=full.people["pi"], lab=lab, membership=membership)
    section = next(s for s in report["sections"] if s["key"] == "external_links")
    assert {i["id"] for i in section["items"]} == eli_links
    assert {i["project"]["name"] for i in section["items"]} == {
        full.projects["crowding"].name,
        full.projects["pupil"].name,
    }

    remote.on("POST", google_drive.PROVIDER.revoke_url, response(200, {}))
    lab_services.remove_member(membership=membership, by=full.people["pi"])

    # every connection of his is revoked, wiped and forgotten; nobody else's changed
    for row in eli_accounts.all():
        assert row.status == AccountStatus.REVOKED
        assert not (
            row.access_token_ct or row.refresh_token_ct or row.external_email or row.granted_scopes
        )
        assert row.external_account_id.startswith("revoked:")
    assert {
        a.pk: a.status for a in ConnectedAccount.objects.for_lab(lab).exclude(user=eli)
    } == others
    events = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_REVOKED, lab=lab)
    assert events.count() == len(tokens)
    assert all(e.actor_id is None and e.actor_label == "lifecycle:member_removed" for e in events)
    # his Drive grant was revoked at Google once (by its refresh token), and nobody else's was used
    [sent] = remote.sent("POST", google_drive.PROVIDER.revoke_url)
    assert sent["data"]["token"] == f"CANARY-refresh-{account(full, 'eli', 'google_drive').pk}"

    # his links stay (they are the lab's record) but can no longer be refreshed with his account
    assert (
        set(ExternalLink.objects.for_lab(lab).filter(linked_by=eli).values_list("pk", flat=True))
        == eli_links
    )
    rows = (
        api(full.people["pi"])
        .get(lab_url(full, f"projects/{full.projects['crowding'].pk}/external-links/"))
        .json()
    )
    mine = [r for r in rows if r["linked_by"]["id"] == str(eli.pk)]
    assert mine and {r["check_blocked"] for r in mine} <= {"linker_inactive", ""}
    assert any(
        r["check_blocked"] == "linker_inactive" and r["linker_connection_status"] == "revoked"
        for r in mine
    )
    result = services.check_lab_links(lab)
    assert result["skipped"] >= len(tokens) - 1  # ones he linked with an account
    assert not [t for t in tokens if remote.asked(t)]  # none of his tokens was ever sent
    # a member who left no longer holds any project role
    assert not full.projects["crowding"].memberships.filter(user=eli).exists()


def test_the_handover_report_cannot_be_built_once_the_member_is_gone(full):
    """The report lists links by who made them, but only while the membership exists."""
    membership = LabMembership.objects.for_lab(full.lab).get(user=full.people["eli"])
    url = lab_url(full, f"members/{membership.pk}/handover/")
    assert api(full.people["pi"]).get(url).status_code == 200
    lab_services.remove_member(membership=membership, by=full.people["pi"])
    assert api(full.people["pi"]).get(url).status_code == 404


def test_removing_the_person_who_runs_the_chat_link_pauses_it(full, remote):
    lab, manager = full.lab, full.people["manager"]
    sync_row = GoogleCalendarSync.objects.for_lab(lab).get(user=manager)
    meeting = Meeting.objects.for_lab(lab).get(title="Grant writing session (FAKE)")
    assert sync_row.account.status == AccountStatus.ACTIVE and meeting.video_account.user == manager
    membership = LabMembership.objects.for_lab(lab).get(user=manager)
    remote.on("POST", google_drive.PROVIDER.revoke_url, response(200, {}))
    lab_services.remove_member(membership=membership, by=full.people["pi"])

    assert not GoogleCalendarSync.objects.for_lab(lab).filter(user=manager).exists()
    assert not SyncedEvent.objects.for_lab(lab).filter(sync=sync_row).exists()
    meeting.refresh_from_db()
    assert meeting.video_account.status == AccountStatus.REVOKED
    status = api(full.people["pi"]).get(lab_url(full, "chat/google/")).json()
    assert (
        status["bridge"] is None and status["needs_reconnect"] and not status["reconnect_is_mine"]
    )
    shown = api(full.people["priya"]).get(lab_url(full, "chat/messages/")).json()
    assert not [m for m in shown if m["source"] == "google_chat"]  # hidden while the link is off
    remote.calls.clear()
    remote.when("GET", f"{CHAT}/spaces/FAKEAGEING01/messages", response(200, {"messages": []}))
    remote.when("GET", f"{CHAT}/spaces/FAKEAGEING01/members", response(403, {}))
    assert chat_sync.poll_all() == 0
    assert not [c for c in remote.calls if LAB_SPACE in c[1]]  # nothing read or posted for it
    # a change to the meeting stays local: the call's owner is gone
    r = api(full.people["pi"]).patch(
        lab_url(full, f"calendar/meetings/{meeting.pk}/"), {"title": "Moved"}, format="json"
    )
    assert r.status_code == 200
    assert not [c for c in remote.calls if c[0] == "PATCH"]


# ---------------------------------------------------------------- writers: Zoom and Google


def meeting_url(ctx, meeting=None):
    return lab_url(ctx, "calendar/meetings/" + (f"{meeting.pk}/" if meeting else ""))


def test_zoom_and_meet_meetings_are_made_changed_and_removed_with_the_organisers_account(
    full, remote
):
    start = timezone.now() + timedelta(days=20)
    body = {
        "title": "Sync",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=45)).isoformat(),
        "notes": "PRIVATE NOTES",
    }
    pi, manager = api(full.people["pi"]), api(full.people["manager"])
    zoom_token, google_token = (
        access_token(account(full, "pi", "zoom")),
        access_token(account(full, "manager", "google_calendar")),
    )

    remote.on(
        "POST",
        ZOOM_MEETINGS,
        response(201, {"id": 8812, "join_url": "https://us05web.zoom.us/j/8812?pwd=x"}),
    )
    made = pi.post(
        meeting_url(full),
        {**body, "video": "zoom", "attendees": [str(full.people["priya"].pk)]},
        format="json",
    )
    assert made.status_code == 201, made.content
    assert made.json()["join_url"].startswith("https://us05web.zoom.us/j/8812")
    [call] = remote.sent("POST", ZOOM_MEETINGS)
    assert call["headers"][
        "Authorization"
    ] == f"Bearer {zoom_token}" and "PRIVATE NOTES" not in json.dumps(call["json"])

    remote.on(
        "POST",
        EVENTS,
        response(200, {"id": "ev1", "hangoutLink": "https://meet.google.com/abc-defg-hij"}),
    )
    meet = manager.post(
        meeting_url(full),
        {**body, "video": "google_meet", "attendees": [str(full.people["pi"].pk)]},
        format="json",
    )
    assert meet.status_code == 201, meet.content
    [call] = remote.sent("POST", EVENTS)
    assert call["headers"]["Authorization"] == f"Bearer {google_token}"
    assert {a["email"] for a in call["json"]["attendees"]} == {
        full.people["manager"].email,
        full.people["pi"].email,
    }

    # change and remove both calls
    remote.on("PATCH", f"{zoom.API}/meetings/8812", response(204))
    url = meeting_url(full, Meeting.objects.for_lab(full.lab).get(external_id="8812"))
    assert pi.patch(url, {"title": "Moved"}, format="json").status_code == 200
    assert remote.sent("PATCH", f"{zoom.API}/meetings/8812")[0]["json"]["topic"] == "Moved"
    remote.on("PATCH", f"{EVENTS}/ev1", response(200, {}))
    meet_url = meeting_url(full, Meeting.objects.for_lab(full.lab).get(external_id="ev1"))
    assert manager.patch(meet_url, {"title": "Moved too"}, format="json").status_code == 200
    # someone else on the meeting can't change a call that is on another person's account
    assert api(full.people["priya"]).patch(url, {"title": "Mine"}, format="json").status_code in (
        403,
        404,
    )
    remote.on("DELETE", f"{zoom.API}/meetings/8812", response(204))
    remote.on("DELETE", f"{EVENTS}/ev1", response(204))
    assert pi.delete(url).status_code == 204 and manager.delete(meet_url).status_code == 204
    assert not Meeting.objects.for_lab(full.lab).filter(external_id__in=["8812", "ev1"]).exists()


def test_a_seeded_zoom_meeting_is_changed_through_its_own_account_and_a_revoked_one_stays_local(
    full, remote
):
    seeded_call = Meeting.objects.for_lab(full.lab).get(title="Lab meeting (FAKE)")
    remote.on("PATCH", f"{zoom.API}/meetings/{seeded_call.external_id}", response(204))
    r = api(full.people["pi"]).patch(
        meeting_url(full, seeded_call), {"title": "Lab meeting, moved"}, format="json"
    )
    assert r.status_code == 200
    assert len(remote.sent("PATCH", f"{zoom.API}/meetings/{seeded_call.external_id}")) == 1

    # the coordinator's Zoom was disconnected: their meeting changes here only
    plain = Meeting.objects.for_lab(full.lab).get(title="Site visit prep (FAKE)")
    assert plain.video_account.status == AccountStatus.REVOKED
    r = api(full.people["coordinator"]).patch(
        meeting_url(full, plain), {"title": "Prep"}, format="json"
    )
    assert r.status_code == 200 and not remote.sent(
        "PATCH", f"{zoom.API}/meetings/{plain.external_id}"
    )
    # and they cannot start a new Zoom call
    new = api(full.people["coordinator"]).post(
        meeting_url(full),
        {
            "title": "x",
            "starts_at": timezone.now().isoformat(),
            "ends_at": (timezone.now() + timedelta(hours=1)).isoformat(),
            "video": "zoom",
        },
        format="json",
    )
    assert new.status_code == 400 and "Connect Zoom" in new.content.decode()


def test_the_calendar_push_clears_what_it_made_and_adds_the_lab_meetings(full, remote):
    sync_row = GoogleCalendarSync.objects.for_lab(full.lab).get(user=full.people["pi"])
    assert sync_row.pushes and sync_row.events.count() == 3
    cal = f"{google_calendar.API}/calendars/{quote(sync_row.app_calendar_id, safe='')}/events"
    remote.when("DELETE", cal, response(204))
    remote.when("POST", cal, lambda kw: response(200, {"id": "new-" + kw["json"]["summary"][:6]}))
    counts = video_calendar.push(sync_row)
    assert counts["removed"] == 3 and counts["added"] >= 3 and counts["changed"] == 0
    sync_row.refresh_from_db()
    assert sync_row.last_error == "" and sync_row.events.count() == counts["added"]
    assert {c[2]["headers"]["Authorization"] for c in remote.calls} == {
        f"Bearer {access_token(sync_row.account)}"
    }


def zoom_event(user_id, client_id="zm-client"):
    body = json.dumps(
        {
            "event": "app_deauthorized",
            "payload": {"user_id": user_id, "account_id": "a", "client_id": client_id},
        }
    )
    stamp = str(int(time.time()))
    sig = (
        "v0="
        + hmac.new(ZOOM_SECRET.encode(), f"v0:{stamp}:{body}".encode(), hashlib.sha256).hexdigest()
    )
    return APIClient(enforce_csrf_checks=True).post(
        "/api/integrations/zoom/events/", body, content_type="application/json",
        headers={"x-zm-request-timestamp": stamp, "x-zm-signature": sig},
    )  # fmt: skip


def test_zoom_deauthorizing_one_person_disconnects_only_them(full, remote):
    before = {a.pk: a.status for a in ConnectedAccount.objects.for_lab(full.lab)}
    pi_zoom = account(full, "pi", "zoom")
    assert zoom_event(pi_zoom.external_account_id).status_code == 200
    pi_zoom.refresh_from_db()
    assert pi_zoom.status == AccountStatus.REVOKED and not pi_zoom.access_token_ct
    after = {a.pk: a.status for a in ConnectedAccount.objects.for_lab(full.lab)}
    assert {pk for pk in after if after[pk] != before[pk]} == {pi_zoom.pk}
    assert account(full, "manager", "zoom").status == AccountStatus.ACTIVE
    assert account(full, "pi", "google_drive").status == AccountStatus.ACTIVE
    [event] = AuditEvent.objects.filter(action=AuditAction.INTEGRATION_REVOKED, lab=full.lab)
    assert event.actor_label == "zoom:app_deauthorized" and not remote.calls
    # someone else's Zoom app, or an unknown person, changes nothing
    assert (
        zoom_event(
            account(full, "manager", "zoom").external_account_id, client_id="other-app"
        ).status_code
        == 200
    )
    assert zoom_event("nobody").status_code == 200
    assert account(full, "manager", "zoom").status == AccountStatus.ACTIVE


# ---------------------------------------------------------------- Google Chat


def google_message(name, text, sender="users/9", at="2099-01-01T00:00:01.123456789Z"):
    return {
        "name": f"{LAB_SPACE}/messages/{name}",
        "text": text,
        "createTime": at,
        "sender": {"name": sender, "type": "HUMAN"},
    }


def test_the_lab_chat_bridge_sends_as_each_person_and_reads_new_messages(full, remote):
    lab = full.lab
    manager_token = access_token(account(full, "manager", "google_chat"))
    pi_chat = account(full, "pi", "google_chat")
    remote.on(
        "POST",
        CHAT_MESSAGES,
        lambda kw: response(200, {"name": f"{LAB_SPACE}/messages/{kw['params']['messageId']}"}),
    )

    # someone with no Google Chat account is relayed by the link's connection, with their name
    lab_services.post_lab_message(lab=lab, by=full.people["grace"], body="hello **all**")
    [call] = remote.sent("POST", CHAT_MESSAGES)
    assert call["headers"]["Authorization"] == f"Bearer {manager_token}"
    assert (
        call["json"]["text"]
        == f"*Grace Chen (FAKE) ({full.people['grace'].email})* via labbenchos: hello *all*"
    )
    # someone whose Google Chat has expired is relayed the same way
    lab_services.post_lab_message(lab=lab, by=full.people["priya"], body="from priya")
    assert (
        remote.sent("POST", CHAT_MESSAGES)[1]["headers"]["Authorization"]
        == f"Bearer {manager_token}"
    )
    # someone with their own active connection posts as themselves
    lab_services.post_lab_message(lab=lab, by=full.people["pi"], body="from the pi")
    last = remote.sent("POST", CHAT_MESSAGES)[2]
    assert last["headers"]["Authorization"] == f"Bearer {access_token(pi_chat)}" and last[
        "json"
    ] == {"text": "from the pi"}
    sent = LabChatMessage.objects.for_lab(lab).filter(source=ChatSource.APP)
    assert sent.count() == 3 and all(m.external_id.startswith(LAB_SPACE) for m in sent)

    # reading: a stranger, a member by their Google id, and one of our own echoed back
    remote.on(
        "GET",
        CHAT_MESSAGES,
        response(
            200,
            {
                "messages": [
                    google_message("g1", "from a visitor"),
                    google_message(
                        "g2", "from the pi in Google", sender=f"users/{pi_chat.external_account_id}"
                    ),
                ]
            },
        ),
    )
    remote.when("GET", f"{CHAT}/spaces/FAKEAGEING01/messages", response(200, {"messages": []}))
    remote.when("GET", f"{CHAT}/{LAB_SPACE}/members", response(403, {}))
    remote.when("GET", "https://people.googleapis.com", response(403, {}))
    assert chat_sync.poll_all() == 2
    got = {
        m.external_id.rsplit("/", 1)[1]: m
        for m in LabChatMessage.objects.for_lab(lab).filter(
            source=ChatSource.GOOGLE_CHAT, external_id__regex=r"messages/g\d$"
        )
    }
    assert got["g1"].author is None and got["g2"].author == full.people["pi"]
    assert all(m.via_account == account(full, "manager", "google_chat") for m in got.values())
    bridge = GoogleChatBridge.objects.for_lab(lab).get(project__isnull=True)
    assert bridge.cursor == "2099-01-01T00:00:01.123456Z" and bridge.last_error == ""
    assert chat_sync.poll_all() == 0  # the same answer adds nothing


def test_an_expired_bridge_connection_pauses_both_directions(full, remote):
    owner = account(full, "manager", "google_chat")
    ConnectedAccount.objects.for_lab(full.lab).filter(pk=owner.pk).update(
        status=AccountStatus.EXPIRED
    )
    remote.calls.clear()
    lab_services.post_lab_message(lab=full.lab, by=full.people["grace"], body="hello")
    assert chat_sync.poll_all() == 0
    assert not [c for c in remote.calls if LAB_SPACE in c[1]]
    bridge = GoogleChatBridge.objects.for_lab(full.lab).get(project__isnull=True)
    assert "no longer active" in bridge.last_error or "Reconnect" in bridge.last_error
    status = api(full.people["grace"]).get(lab_url(full, "chat/google/")).json()
    assert status["bridge"] is None and status["needs_reconnect"]
    # what came from Google is hidden until the owner reconnects
    shown = api(full.people["grace"]).get(lab_url(full, "chat/messages/")).json()
    assert not [m for m in shown if m["source"] == "google_chat"]


# ---------------------------------------------------------------- task import


def test_task_import_uses_the_members_own_account_and_never_copies_twice(full, remote):
    lab = full.lab
    ids = {"todoist": "p1", "trello": "0123456789abcdef01234567", "monday": "12345"}
    remote.on(
        "GET",
        f"{todoist.API}/tasks?project_id=p1&limit=200",
        response(
            200,
            {
                "results": [
                    {"content": "Book MRI", "due": {"date": "2030-02-03T10:00:00"}},
                    {"content": "Order caps"},
                ],
                "next_cursor": None,
            },
        ),
    )
    remote.on(
        "GET",
        f"{trello.API}/boards/{ids['trello']}/cards/open?fields=name,desc,due",
        response(200, [{"name": "Card A", "desc": "d", "due": "2030-01-02T00:00:00.000Z"}]),
    )
    remote.on(
        "POST",
        monday.API,
        response(
            200,
            {
                "data": {
                    "boards": [{"items_page": {"items": [{"name": "Item A", "column_values": []}]}}]
                }
            },
        ),
    )
    cases = [
        ("todoist", "zoe", "mouse", 2),
        ("trello", "noah", "eeg", 1),
        ("monday", "manager", "grant", 1),
    ]

    def run(provider, who, project):
        url = lab_url(
            full, f"projects/{full.projects[project].pk}/integrations/{provider}/import-tasks/"
        )
        return api(full.people[who]).post(url, {"source": ids[provider]}, format="json")

    for provider, who, project, count in cases:
        assert run(provider, who, project).json() == {"created": count, "skipped": 0}
        assert run(provider, who, project).json() == {"created": 0, "skipped": count}
        tasks = Task.objects.for_lab(lab).filter(project=full.projects[project])
        assert tasks.count() == count and all(
            t.created_by == full.people[who] and t.assignee is None for t in tasks
        )
    assert AuditEvent.objects.filter(action=AuditAction.TASKS_IMPORTED, lab=lab).count() == 6
    # someone with no connection there, or another person's, gets a plain 404 and no call
    calls = len(remote.calls)
    for provider, who, project in [
        ("todoist", "priya", "sleep"),
        ("trello", "pi", "grant"),
        ("monday", "priya", "sleep"),
        ("todoist", "ingrid", "sleep"),
    ]:
        assert run(provider, who, project).status_code in (403, 404)
    assert len(remote.calls) == calls
    # the provider list shows which services import
    names = {
        e["name"]
        for e in api(full.people["zoe"]).get(lab_url(full, "integrations/providers/")).json()
        if e["task_import"]
    }
    assert names == {"todoist", "trello", "monday"}


# ---------------------------------------------------------------- nothing secret leaves


FORBIDDEN_KEYS = {
    "access_token",
    "refresh_token",
    "token_expires_at",
    "api_key",
    "client_secret",
    "url_ct",
    "secret_ct",
    "authorization",
}


def keys_of(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from keys_of(v)
    elif isinstance(value, list):
        for v in value:
            yield from keys_of(v)


def test_no_response_for_any_role_carries_a_token_or_a_secret(full):
    lab, pi = full.lab, full.people["pi"]
    link = ExternalLink.objects.for_lab(lab).filter(connected_account__isnull=False).first()
    eli_membership = LabMembership.objects.for_lab(lab).get(user=full.people["eli"])
    urls = [
        "integrations/providers/",
        "integrations/accounts/",
        "integrations/accounts/?all=true",
        "webhooks/",
        "chat/google/",
        "chat/messages/",
        f"external-links/{link.pk}/",
        f"members/{eli_membership.pk}/handover/",
        *[f"projects/{p.pk}/external-links/" for p in full.projects.values()],
    ]
    secrets = [
        c
        for c in ConnectedAccount.objects.for_lab(lab).values_list("access_token_ct", flat=True)
        if c
    ]
    secrets += [
        "CANARY-",
        "fake-signing-secret",
        "fake-path-0001",
        "access_token_ct",
        "refresh_token_ct",
        "gd-secret",
        "zm-secret",
        "gc-secret",
    ]
    seen = 0
    for user in full.people.values():
        for path in urls:
            resp = api(user).get(lab_url(full, path))
            assert resp.status_code in (200, 403, 404), (user.email, path, resp.status_code)
            text = resp.content.decode()
            assert not [s for s in secrets if s in text], (user.email, path)
            if resp.status_code == 200:
                seen += 1
                assert not FORBIDDEN_KEYS & set(keys_of(resp.json())), (user.email, path)
    assert seen > 150
    # the hooks list shows where they go (the host) and nothing else of the address
    hooks = api(pi).get(lab_url(full, "webhooks/")).json()["webhooks"]
    assert {h["host"] for h in hooks} == {
        "hooks.slack.example.invalid",
        "hooks.example.invalid",
        "zapier.example.invalid",
    }
    # and the one place a token is meant to appear is still the Drive Picker's, to its owner only
    assert api(pi).get(lab_url(full, "integrations/google/picker-token/")).json()[
        "access_token"
    ] == access_token(account(full, "pi", "google_drive"))
