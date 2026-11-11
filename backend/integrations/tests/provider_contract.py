"""The provider contract (D88): one mock-based harness every provider's tests reuse.

A provider test is a subclass with a few fixtures and the provider's mocked HTTP replies:

    from integrations.providers import zenodo
    from integrations.tests.provider_contract import ProviderContract

    class TestZenodo(ProviderContract):
        provider = zenodo.PROVIDER
        item_id = "123"
        item_url = "https://zenodo.org/records/123"  # a pasted address (paste_url only)
        title = "Survey data"  # what fetch_item must return as the title
        replies = {  # stage -> [(method, url, status, json body)]
            "item": [("GET", "https://zenodo.org/api/records/123", 200, {...})],
            "item_changed": [("GET", "https://zenodo.org/api/records/123", 200, {...})],
            "item_gone": [("GET", "https://zenodo.org/api/records/123", 404, {})],
            "search": [("GET", "https://zenodo.org/api/records?q=survey", 200, {...})],
        }

Stages: `identity` (oauth2: the identity_url reply; api_key: the call that validates the key),
`item`, `item_changed` (a newer version of the item), `item_gone`, `search` (for the "search"
link method, queried with `search_query` and `target`), `revoke` (oauth2 with a revoke_url;
default 200). The oauth2 token endpoint is answered by the harness. For api_key the harness
supplies the key and secret (canaries) and `instance_url` when the provider needs one; the
"bad key" case reuses the `identity` URLs with a 401.

Every test runs the real endpoints with the provider registered, so permissions, audit, the
link rules (D83, D85), freshness and the leak scan are the framework's, not the provider's.
`provider_problems()` and `content_paths()` are also used by `test_registry.py` on every
enabled provider.
"""

import ast
import inspect
import json
import logging
import re
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client

from audit.models import AuditEvent
from core.models import Notification
from integrations import http, registry, services
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink
from integrations.registry import (
    CONNECT_FIELDS,
    LINK_METHODS,
    TARGETS,
    WRITERS,
    AuthType,
    Category,
)
from integrations.serializers import ConnectedAccountSerializer
from integrations.tests.fake import FakeTransport, response

# ---- static checks (also run on every enabled provider by test_registry.py)

# D84: what a content download looks like in a provider's code. A match in any string literal
# (docstrings excluded) or host fails the provider. Extend when a new API has its own spelling.
CONTENT_PATHS = [
    r"alt=media",
    r"\bexport\b",
    r"download",
    r"/contents?(?:$|[/?{])",
    r"(?:^|[/.])content\.",
    r"/raw(?:$|[/?{])",
    r"raw\.githubusercontent",
    r"codeload\.",
    r"/archive",
    r"zipball|tarball",
    r"/blobs?(?:$|[/?{])",
    r"files\.osf\.io",
    r"waterbutler|ndownloader|files-archive",  # OSF, Figshare, Zenodo downloads (D115 to D119)
    r"responses",
    r"/file(?:$|[/?{])",
    r"content=(?:record|file|report|log|metadata|instrument|participantlist|user|event|arm)",
    r"distributions?(?:$|[/?{])",
    r"/(?:steps|materials|comments)(?:$|[/?{])",
    r"/api/access/|/api/files?/|datafile",  # Dataverse file endpoints (D183)
]
_HOOKS = (
    "fetch_item",
    "search_items",
    "identify",
    "parse_identity",
    "sign",
    "apply_to_target",
    "task_sources",
    "fetch_tasks",
)


def _strings(module) -> list[str]:
    """Every string literal in `module`, docstrings excluded."""
    tree = ast.parse(inspect.getsource(module))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    ]


def content_paths(provider) -> list[str]:
    """Content-download paths in the provider's code and hosts (D84): must be empty."""
    modules = {inspect.getmodule(h) for h in (getattr(provider, n) for n in _HOOKS) if h}
    modules.discard(None)
    modules.discard(inspect.getmodule(registry.Provider))  # the framework's default `sign`
    web = provider.link_hosts - provider.api_hosts  # pages people open; never requested (D78)
    texts = [
        s
        for m in modules
        for s in _strings(m)
        if not any(s.startswith(f"https://{h}/") for h in web)
    ]
    texts += [*provider.api_hosts, *provider.link_hosts, provider.identity_url]
    return sorted(
        {t for t in texts for p in CONTENT_PATHS if t and re.search(p, t.lower())},
    )


def provider_problems(p) -> list[str]:  # noqa: C901 - a checklist, one line per rule
    """What is wrong with a provider's registry entry; [] when it is sound."""
    out = []

    def need(ok, msg):
        if not ok:
            out.append(msg)

    def https(url):
        return url.startswith("https://") and (urlsplit(url).hostname or "") in p.api_hosts

    need(re.fullmatch(r"[a-z][a-z0-9_]{1,39}", p.name), "name: lower-case slug, 40 chars max")
    need(p.label and p.icon and re.fullmatch(r"[a-z0-9-]+", p.icon), "label and icon key")
    need(p.auth_type in set(AuthType) and p.category in set(Category), "auth_type, category")
    if p.name in WRITERS:  # D253: a writer declares exactly its allowed writes and links nothing
        need(p.metadata_only is False and p.writes == WRITERS[p.name], "writes must match WRITERS")
        need(p.category == Category.MEETINGS and not p.link_targets, "writers: meetings, no links")
    else:
        need(p.metadata_only is True and not p.writes, "metadata_only must be True (D84)")
        need(p.link_targets and set(p.link_targets) <= set(TARGETS), "link_targets")
    need(p.token_auth in ("body", "basic"), "token_auth: body or basic")
    for other_name in p.bundle:  # D262: a shared grant is shared both ways, from one OAuth app
        other = registry.PROVIDERS.get(other_name)
        need(other is not None and p.name in other.bundle, f"bundle {other_name}: both ways")
        if other is not None:
            same = (p.authorize_url, p.token_url, p.token_auth, p.authorize_params) == (
                other.authorize_url,
                other.token_url,
                other.token_auth,
                other.authorize_params,
            )
            need(same, f"bundle {other_name}: same sign-in and token endpoints")
            need(
                (p.client_from or p.name) == (other.client_from or other.name)
                or p.client_from == other.name
                or other.client_from == p.name,
                f"bundle {other_name}: one OAuth app",
            )
    need(not p.bundle or p.bundle_label, "bundle needs a bundle_label")
    need(set(p.link_methods) <= set(LINK_METHODS), "link_methods")
    need("search" not in p.link_methods or p.search_items, "search needs search_items")
    if "paste_url" in p.link_methods:
        pattern_ok = False
        try:
            pattern_ok = "id" in re.compile(p.url_pattern).groupindex
        except re.error:
            pass
        need(pattern_ok, "paste_url needs url_pattern with an `id` group")
        need(p.link_hosts or p.needs_instance_url, "paste_url needs link_hosts")
    for host in [*p.api_hosts, *p.link_hosts]:
        need(http.dns_name_ok(host), f"host {host!r}: a DNS name, no scheme or port")
    names = [f.name for f in p.connect_fields]
    need(len(set(names)) == len(names) and set(names) <= set(CONNECT_FIELDS), "connect_fields")
    need(not p.needs_instance_url or p.auth_type == AuthType.API_KEY, "instance URL: api_key")
    need(("instance_url" in names) == p.needs_instance_url, "instance_url field iff needed")
    need(
        not (p.needs_account or p.auth_type == AuthType.PUBLIC)
        or p.fetch_item
        or p.fetch_tasks
        or p.writes,
        "fetch_item is required unless link_only or task import",
    )
    if p.instance_host_pattern:
        try:
            re.compile(p.instance_host_pattern)
        except re.error:
            out.append("instance_host_pattern does not compile")
    if p.auth_type == AuthType.OAUTH2:
        need(p.scopes and p.parse_identity, "oauth2: scopes and parse_identity")
        for url in (p.authorize_url, p.token_url, p.identity_url):
            need(url.startswith("https://"), f"oauth2 url {url!r}: https")
        for url in (p.token_url, p.identity_url, *([p.revoke_url] if p.revoke_url else [])):
            need(https(url), f"oauth2 url {url!r}: on api_hosts")
        need(not names, "oauth2: no connect_fields")
    elif p.auth_type == AuthType.API_KEY:
        need("api_key" in names, "api_key: an api_key connect field")
        need(p.identify or (p.identity_url and p.parse_identity), "api_key: a way to identify")
        need(p.api_hosts or p.needs_instance_url, "api_key: api_hosts or an instance URL")
        need(not (p.scopes or p.authorize_url or p.token_url), "api_key: no OAuth settings")
    else:
        need(not (names or p.scopes or p.token_url), "no credentials without an account")
        need(p.auth_type != AuthType.PUBLIC or p.api_hosts, "public: api_hosts")
        need(
            p.auth_type != AuthType.LINK_ONLY or "paste_url" in p.link_methods,
            "link_only: paste_url",
        )
    return out


# ---- the harness

KEY = "CANARY-api-key-3f9a71"
SECRET = "CANARY-api-secret-c20e44"
ACCESS = "CANARY-access-b81d02"
REFRESH = "CANARY-refresh-5e7c19"
CLIENT_SECRET = "CANARY-contract-client-secret"
PUBLIC_IP = "93.184.216.34"


class World:
    def __init__(self, lab, users, project, transport, caplog):
        self.lab, self.users, self.project = lab, users, project
        self.transport, self.caplog = transport, caplog
        self.pi = users["pi"]
        self.client = Client()
        self.client.force_login(self.pi)
        self.seen = []  # every response body, for the leak scan

    def url(self, path):
        return f"/api/labs/{self.lab.pk}/{path}"

    def call(self, method, path, body=None, **query):
        c = self.client
        if method == "GET":
            resp = c.get(self.url(path), query)
        else:
            resp = getattr(c, method.lower())(self.url(path), body or {}, "application/json")
        self.seen.append(f"{resp.status_code} {dict(resp.headers)!r} {resp.content.decode()}")
        return resp


class ProviderContract:
    """Subclass as `class Test<Provider>(ProviderContract)`; see the module docstring."""

    provider = None
    item_id = ""
    item_url = ""  # a pasted address that parses to item_id (when paste_url is offered)
    title = ""  # the title fetch_item returns for the item
    instance_url = ""  # api_key with needs_instance_url
    search_query = "data"
    target = "project"  # what the link hangs off (must be in link_targets)
    link_title = "My title"  # link_only: the title the person gives
    replies: dict = {}

    # -- fixtures

    @pytest.fixture
    def w(self, lab_users, make_project, monkeypatch, settings, caplog):
        caplog.set_level(logging.DEBUG)
        p = self.provider
        monkeypatch.setitem(registry.PROVIDERS, p.name, p)
        settings.INTEGRATION_CLIENTS = {
            **settings.INTEGRATION_CLIENTS,
            p.name: {"client_id": "contract-client", "client_secret": CLIENT_SECRET},
        }
        transport = FakeTransport()
        monkeypatch.setattr(http, "_session", transport)
        monkeypatch.setattr(http.time, "sleep", lambda s: None)
        monkeypatch.setattr(http, "_resolve", lambda host: [PUBLIC_IP])
        lab, users = lab_users
        return World(lab, users, make_project(lab), transport, caplog)

    def reply(self, w, stage, status=None):
        for method, url, code, body in self.replies.get(stage, []):
            w.transport.on(method, url, response(status or code, body))

    def needs(self, *what):
        p = self.provider
        checks = {
            "account": p.needs_account,
            "no_account": not p.needs_account,
            "api_key": p.auth_type == AuthType.API_KEY,
            "oauth2": p.auth_type == AuthType.OAUTH2,
            "search": "search" in p.link_methods,
            "paste": "paste_url" in p.link_methods and bool(self.item_url),
            "fetch": p.fetch_item is not None,
        }
        missing = [x for x in what if not checks[x]]
        if missing:
            pytest.skip(f"{p.name}: not applicable ({', '.join(missing)})")

    def connect(self, w, *, key=KEY):
        """Connect the PI's account through the API; returns the response."""
        p = self.provider
        if p.auth_type == AuthType.API_KEY:
            self.reply(w, "identity")
            body = {"api_key": key, "secret": SECRET}
            if p.needs_instance_url:
                body["instance_url"] = self.instance_url
            return w.call("POST", f"integrations/{p.name}/connect/", body)
        start = w.call("POST", f"integrations/{p.name}/connect/")
        if p.auth_type != AuthType.OAUTH2:
            return start  # link_only and public have no account to connect
        assert start.status_code == 200, start.content
        state = parse_qs(urlsplit(start.json()["authorization_url"]).query)["state"][0]
        tokens = {
            "access_token": ACCESS,
            "refresh_token": REFRESH,
            "expires_in": 3600,
            "scope": " ".join(p.scopes),
        }
        w.transport.on("POST", p.token_url, response(200, tokens))
        self.reply(w, "identity")
        return w.client.get("/api/integrations/oauth/callback/", {"state": state, "code": "c"})

    def account(self, w):
        return ConnectedAccount.objects.for_lab(w.lab).get(user=w.pi, provider=self.provider.name)

    def link_body(self, **over):
        p = self.provider
        body = {"provider": p.name}
        if p.auth_type == AuthType.LINK_ONLY:
            body.update(url=self.item_url, title=self.link_title)
        else:
            body["external_id"] = self.item_id
        if self.target != "project":
            body[self.target] = str(self.make_target(**over))
        return body

    def make_target(self, **over):
        from provenance.models import Analysis, DatasetRecord, Decision, ManuscriptLink, Result

        w, user = self._w, self._w.pi
        lab, project = w.lab, w.project
        common = {"lab": lab, "project": project}
        if self.target == "dataset":
            obj = DatasetRecord.objects.create(
                **common, name="Data", version_label="v1", created_by=user
            )
        elif self.target in ("analysis", "result"):
            from django.utils import timezone

            from documents.models import Attachment

            att = Attachment.objects.create(
                **common,
                storage_key=f"contract/{uuid.uuid4()}",
                original_filename="code.py",
                content_type="text/x-python",
                size_bytes=1,
                sha256="0" * 64,
                uploaded_by=user,
                notice_acknowledged_at=timezone.now(),
            )
            obj = Analysis.objects.create(
                **common, title="A", code_attachment=att, ran_by=user, ran_at=timezone.now()
            )
            if self.target == "result":
                obj = Result.objects.create(**common, title="R", analysis=obj, created_by=user)
        elif self.target == "manuscript":
            obj = ManuscriptLink.objects.create(
                **common, title="M", url="https://example.org/m", created_by=user
            )
        elif self.target == "decision":
            obj = Decision.objects.create(
                **common, title="D", decided_on="2030-01-01", decided_by=user
            )
        else:
            from documents.models import Document

            obj = Document.objects.create(**common, title="Doc", created_by=user, updated_by=user)
        return obj.pk

    def create_link(self, w, **body):
        self._w = w
        if self.provider.needs_account:
            assert self.connect(w).status_code in (200, 302)
        self.reply(w, "item")
        body = {k: v for k, v in {**self.link_body(), **body}.items() if v is not None}
        resp = w.call("POST", f"projects/{w.project.pk}/external-links/", body)
        assert resp.status_code == 201, resp.content
        return resp.json()

    def check(self, w, link):
        ExternalLink.objects.for_lab(w.lab).update(last_checked_at=None)  # not a 429 (D78)
        resp = w.call("POST", f"external-links/{link['id']}/check/")
        assert resp.status_code == 200, resp.content
        return resp.json()

    # -- the contract

    def test_registry_entry_is_sound(self):
        assert provider_problems(self.provider) == []
        assert content_paths(self.provider) == [], "metadata only (D84)"
        assert self.target in self.provider.link_targets

    def test_providers_endpoint_describes_it_without_secrets(self, w):
        entry = next(
            e
            for e in w.call("GET", "integrations/providers/").json()
            if e["name"] == self.provider.name
        )
        assert entry["auth_type"] == self.provider.auth_type and entry["metadata_only"] is True
        assert entry["link_methods"] == list(self.provider.link_methods)
        assert CLIENT_SECRET not in json.dumps(entry)

    def test_connect(self, w):
        p = self.provider
        resp = self.connect(w)
        if not p.needs_account:
            assert resp.status_code == 400 and resp.json()["code"] == "unknown_provider"
            assert not ConnectedAccount.objects.for_lab(w.lab).filter(provider=p.name).exists()
            return
        assert resp.status_code in (200, 302), resp.content
        account = self.account(w)
        assert account.status == AccountStatus.ACTIVE and account.access_token_ct
        assert AuditEvent.objects.filter(action="integration.connected", lab=w.lab).exists()
        if p.auth_type == AuthType.API_KEY:
            assert account.access_token() == KEY and account.refresh_token() == SECRET
            assert KEY not in resp.content.decode()
            assert any(KEY in repr(kw) for _, _, kw in w.transport.calls), "key never sent"
            assert account.instance_url == self.instance_url.rstrip("/")

    def test_bad_key_is_refused_and_nothing_stored(self, w):
        self.needs("api_key")
        self.reply(w, "identity", status=401)
        body = {"api_key": KEY, "secret": SECRET}
        if self.provider.needs_instance_url:
            body["instance_url"] = self.instance_url
        resp = w.call("POST", f"integrations/{self.provider.name}/connect/", body)
        assert resp.status_code == 400 and resp.json()["code"] == "invalid_key"
        assert not ConnectedAccount.objects.for_lab(w.lab).exists()

    def test_search(self, w):
        self.needs("search")
        self._w = w
        if self.provider.needs_account:
            self.connect(w)
        self.reply(w, "search")
        resp = w.call(
            "GET",
            f"projects/{w.project.pk}/integrations/{self.provider.name}/search/",
            q=self.search_query,
            target=self.target,
        )
        assert resp.status_code == 200, resp.content
        assert resp["Cache-Control"] == "no-store"
        results = resp.json()
        assert results and all(
            set(r) == {"id", "title", "subtitle", "modified", "url"} for r in results
        )
        assert self.item_id in [r["id"] for r in results]
        assert AuditEvent.objects.filter(action="integration.searched", lab=w.lab).exists()

    def test_fetch_and_link(self, w):
        link = self.create_link(w)
        assert link["external_id"] == self.item_id and link["status"] == "ok"
        assert link["title"] == (
            self.link_title if self.provider.auth_type == AuthType.LINK_ONLY else self.title
        )
        assert link["url"], "the link's address was refused by the provider's own host rules"
        assert AuditEvent.objects.filter(action="external_link.created", lab=w.lab).exists()

    def test_link_from_pasted_url(self, w):
        self.needs("paste")
        link = self.create_link(w, url=self.item_url, external_id=None)  # by address only
        assert link["external_id"] == self.item_id

    def test_client_metadata_is_never_trusted(self, w):
        self.needs("fetch")
        if self.provider.auth_type == AuthType.LINK_ONLY:
            pytest.skip("link_only stores the person's own title by design")
        link = self.create_link(w, title="Forged", url="https://evil.example/x")
        assert link["title"] == self.title and "evil" not in link["url"]

    def test_check_changed_then_gone(self, w):
        self.needs("fetch")
        link = self.create_link(w)
        self.reply(w, "item_changed")
        changed = self.check(w, link)
        assert changed["status"] == "changed" and changed["changed_since_linked"], changed
        self.reply(w, "item_gone")
        gone = self.check(w, link)
        assert gone["status"] == "unavailable" and gone["unavailable_since"]

    def test_revoke(self, w):
        self.needs("account")
        assert self.connect(w).status_code in (200, 302)
        account = self.account(w)
        if self.provider.revoke_url:
            w.transport.on("POST", self.provider.revoke_url, response(200, {}))
            self.reply(w, "revoke")
        resp = w.call("DELETE", f"integrations/accounts/{account.pk}/")
        assert resp.status_code == 200 and resp.json()["status"] == "revoked"
        account.refresh_from_db()
        assert account.access_token_ct == "" and account.refresh_token_ct == ""
        assert AuditEvent.objects.filter(action="integration.disconnected", lab=w.lab).exists()

    def test_rejected_credentials_mark_the_account(self, w):
        """A 401 on an item read: OAuth refreshes once; an API key is revoked there (D81)."""
        self.needs("account", "fetch")
        assert self.connect(w).status_code in (200, 302)
        self.reply(w, "item", status=401)
        if self.provider.auth_type == AuthType.OAUTH2:
            w.transport.on(
                "POST", self.provider.token_url, response(400, {"error": "invalid_grant"})
            )
        with pytest.raises(http.AccountUnavailable):
            self.provider.fetch_item(self.account(w), self.item_id)
        account = self.account(w)
        assert account.status == AccountStatus.EXPIRED and not account.access_token_ct
        assert Notification.objects.for_lab(w.lab).filter(recipient=w.pi).exists()

    def test_no_secrets_leak(self, w):
        """The whole lifecycle, then every surface is scanned for every credential."""
        p = self.provider
        if p.needs_account:
            self.connect(w)
            self.connect(w, key=KEY)  # reconnect reuses the row
        if "search" in p.link_methods:
            self.reply(w, "search")
            w.call("GET", f"projects/{w.project.pk}/integrations/{p.name}/search/", q="x")
        self._w = w
        self.reply(w, "item")
        w.call("POST", f"projects/{w.project.pk}/external-links/", self.link_body())
        for stage in ("item_changed", "item_gone"):
            if p.fetch_item:
                self.reply(w, stage)
                ExternalLink.objects.for_lab(w.lab).update(last_checked_at=None)
                for link in ExternalLink.objects.for_lab(w.lab):
                    w.call("POST", f"external-links/{link.pk}/check/")
        w.call("GET", "integrations/providers/")
        w.call("GET", "integrations/accounts/?all=true")
        errors = []
        if p.needs_account and p.fetch_item:
            self.reply(w, "item", status=401)
            if p.auth_type == AuthType.OAUTH2:
                w.transport.on("POST", p.token_url, response(400, {"error": REFRESH}))
            try:
                p.fetch_item(self.account(w), self.item_id)
            except Exception as exc:  # noqa: BLE001 - the error is a surface
                errors.append(f"{exc!s} {exc!r} {exc.__cause__!r} {exc.__context__!r}")
        if p.needs_account:
            self.connect(w)
            if p.revoke_url:
                w.transport.on("POST", p.revoke_url, response(400, {"error": f"bad {REFRESH}"}))
            services.disconnect(self.account(w), actor=w.pi)
        accounts = list(ConnectedAccount.objects.for_lab(w.lab))
        ciphertexts = [c for a in accounts for c in (a.access_token_ct, a.refresh_token_ct) if c]
        surfaces = {
            "responses": "\n".join(w.seen),
            "logs": "\n".join(f"{r.getMessage()} {r.args!r}" for r in w.caplog.records),
            "audit": json.dumps(list(AuditEvent.objects.filter(lab=w.lab).values()), default=str),
            "notifications": json.dumps(
                list(Notification.objects.for_lab(w.lab).values()), default=str
            ),
            "serializer": json.dumps(
                ConnectedAccountSerializer(accounts, many=True).data, default=str
            ),
            "reprs": "\n".join(f"{a!r} {a}" for a in accounts),
            "errors": "\n".join(errors),
        }
        canaries = [KEY, SECRET, ACCESS, REFRESH, CLIENT_SECRET, *ciphertexts]
        leaks = {name: [c for c in canaries if c in text] for name, text in surfaces.items()}
        assert not any(leaks.values()), leaks
        if p.needs_account:  # the credentials really were used, so a clean scan means something
            wire = repr(w.transport.calls)
            assert (KEY if p.auth_type == AuthType.API_KEY else ACCESS) in wire
        else:  # nothing secret is ever attached for an account-less provider
            assert all(
                "Authorization" not in kw.get("headers", {}) for _, _, kw in w.transport.calls
            )
