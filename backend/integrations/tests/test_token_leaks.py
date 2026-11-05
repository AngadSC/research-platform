"""Token-leak test (ARCHITECTURE section 9). Distinctive canary tokens go through the whole account
lifecycle (connect, refresh, refused refresh, provider errors that echo the token, reconnect,
disconnect); then every surface below must be free of every canary.

To cover a new surface (an API response, a serializer, a job's output), add a function decorated
with `@surface` that returns the text to scan. `w` is the World built by the `world` fixture:
`w.client(user)` gives a logged-in test client, `w.users`, `w.lab`, `w.accounts`."""

import io
import json
import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from cryptography.fernet import Fernet
from django.core import serializers as django_serializers
from django.core.management import call_command
from django.test import Client
from django.test.utils import override_settings

from audit.models import AuditEvent
from core.models import Notification, User
from integrations import http, services
from integrations.jobs import revoke_orphans
from integrations.models import ConnectedAccount, ExternalLink
from integrations.serializers import ConnectedAccountSerializer
from integrations.tests.conftest import CLIENT_SECRET, make_request, token_reply
from integrations.tests.fake import FAKE, response

pytestmark = pytest.mark.django_db

ACCESS = [f"CANARY-access-{i}-9f3c2a" for i in range(4)]
REFRESH = [f"CANARY-refresh-{i}-41d7e0" for i in range(4)]
CODE = "CANARY-authcode-5a8b"
LIFE_ACCESS = [f"CANARY-life-access-{i}-77aa10" for i in range(3)]
LIFE_REFRESH = [f"CANARY-life-refresh-{i}-2c9d4e" for i in range(3)]
FILE_URL = "https://api.fake.test/files/1"


@dataclass
class World:
    lab: object
    users: dict
    accounts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    log_text: str = ""
    canaries: list = field(default_factory=list)
    transport: object = None
    project: object = None
    caplog: object = None
    ciphertexts: list = field(default_factory=list)

    def client(self, user):
        c = Client()
        c.force_login(user)
        return c


def _connect(transport, user, lab, i, *, access=None, refresh=None, ext_id="ext-1"):
    request = make_request(user)
    state = parse_qs(urlsplit(services.start_connect(request, lab, "fake")).query)["state"][0]
    transport.on("POST", FAKE.token_url, token_reply(access or ACCESS[i], refresh or REFRESH[i]))
    transport.on("GET", FAKE.identity_url, response(200, {"id": ext_id, "email": "a@fake.test"}))
    return services.complete_connect(request, state=state, code=CODE)


def _note_ciphertexts(w):
    """Every stored `*_ct` value seen so far: the ciphertext must not leak either."""
    for acc in ConnectedAccount.objects.for_lab(w.lab):
        w.ciphertexts += [c for c in (acc.access_token_ct, acc.refresh_token_ct) if c]


def _expect_error(w, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - every error is a surface
        w.errors.append(exc)
    else:
        raise AssertionError("expected an error")


@pytest.fixture
def world(lab_users, transport, caplog, make_project, make_user, join, capture_commits):
    caplog.set_level(logging.DEBUG)
    lab, users = lab_users
    w = World(lab=lab, users=users, transport=transport, caplog=caplog)
    member = users["member"]
    get = lambda acc: http.send("GET", FILE_URL, provider=FAKE, account=acc)  # noqa: E731

    acc = _connect(transport, member, lab, 0)
    # 401 -> refresh (rotating the refresh token) -> retry
    transport.on("GET", FILE_URL, response(401), response(200, {}))
    transport.on("POST", FAKE.token_url, token_reply(ACCESS[1], REFRESH[1]))
    get(acc)
    # refused refresh whose error body echoes the token
    transport.on("GET", FILE_URL, response(401))
    transport.on(
        "POST",
        FAKE.token_url,
        response(400, {"error": "invalid_grant", "error_description": f"bad {REFRESH[1]}"}),
    )
    _expect_error(w, lambda: get(acc))
    _expect_error(w, lambda: get(acc))  # AccountUnavailable on an expired account
    # reconnect; a network error whose message carries the token
    acc = _connect(transport, member, lab, 2)
    transport.on("GET", FILE_URL, requests.ConnectionError(f"Authorization: Bearer {ACCESS[2]}"))
    _expect_error(w, lambda: get(acc))
    # token endpoint error with an unsafe error code (the token itself)
    transport.on("GET", FILE_URL, response(401))
    transport.on("POST", FAKE.token_url, response(400, {"error": REFRESH[2]}))
    _expect_error(w, lambda: get(acc))
    # reconnect, then disconnect with a revoke endpoint that echoes the token
    acc = _connect(transport, member, lab, 3)
    transport.on("POST", FAKE.revoke_url, response(400, {"error": f"bad token {REFRESH[3]}"}))
    services.disconnect(acc, actor=member)
    # a second, still active account for list pages
    w.accounts = [acc, _connect(transport, users["viewer"], lab, 0)]
    _note_ciphertexts(w)
    project = w.project = make_project(lab)
    ExternalLink.objects.create(
        lab=lab,
        project=project,
        provider="fake",
        connected_account=w.accounts[1],
        external_id="f1",
        url="https://x.test/f1",
        title="Linked file",
        linked_by=users["viewer"],
    )

    _lifecycle(w, make_user, join, capture_commits)

    sent_verifiers = [
        kw["data"].get("code_verifier") for kw in transport.sent("POST", FAKE.token_url)
    ]
    w.canaries = [*ACCESS, *REFRESH, *LIFE_ACCESS, *LIFE_REFRESH, CODE, CLIENT_SECRET]
    w.canaries += list(filter(None, sent_verifiers))
    # the canaries really went over the wire, so a clean scan means something
    wire = repr(transport.calls)
    assert all(c in wire for c in (ACCESS[1], REFRESH[0], CODE, CLIENT_SECRET))
    assert w.ciphertexts and all(w.ciphertexts), "no ciphertext to look for"
    return w


@pytest.fixture
def capture_commits(django_capture_on_commit_callbacks):
    return django_capture_on_commit_callbacks


def _lifecycle(w, make_user, join, capture):
    """Member removal, deactivation and the orphan sweep, each with a provider whose revoke
    fails in a way that echoes the token (a wrapped requests error, an unexpected error, a
    400 body)."""
    from labs import services as lab_services
    from labs.models import LabMembership

    lab, transport = w.lab, w.transport
    people = [make_user() for _ in range(3)]
    for i, person in enumerate(people):
        join(person, lab, "member")
        _connect(
            transport,
            person,
            lab,
            0,
            access=LIFE_ACCESS[i],
            refresh=LIFE_REFRESH[i],
            ext_id=f"life-{i}",
        )
    _note_ciphertexts(w)
    cut = requests.exceptions.ChunkedEncodingError(f"cut {LIFE_REFRESH[0]} {LIFE_ACCESS[0]}")
    transport.on("POST", FAKE.revoke_url, cut)
    membership = LabMembership.objects.for_lab(lab).get(user=people[0])
    with capture(execute=True):
        lab_services.remove_member(membership=membership, by=w.users["pi"])
    transport.on("POST", FAKE.revoke_url, RuntimeError(f"x {LIFE_REFRESH[1]} {LIFE_ACCESS[1]}"))
    people[1].is_active = False
    with capture(execute=True):
        people[1].save()
    bad = response(400, {"error": f"bad {LIFE_REFRESH[2]} {LIFE_ACCESS[2]}"})
    transport.on("POST", FAKE.revoke_url, bad)
    LabMembership.objects.for_lab(lab).filter(user=people[2]).delete()
    with capture(execute=True):
        assert revoke_orphans() == 1
    for acc in ConnectedAccount.objects.for_lab(lab).filter(user__in=people):
        assert acc.status == "revoked" and not acc.access_token_ct


SURFACES = {}
API = "/api"


def surface(fn):
    SURFACES[fn.__name__] = fn
    return fn


def _accounts(w):
    return list(ConnectedAccount.objects.for_lab(w.lab))


@surface
def model_reprs(w):
    links = list(ExternalLink.objects.for_lab(w.lab))
    return "\n".join(f"{o!r} {o} {o.__dict__!r}" for o in [*_accounts(w), *links])


@surface
def admin_pages(w):
    admin = User.objects.create_superuser(email="root@example.com", password="pw")
    c = w.client(admin)
    pages = []
    for model in ("connectedaccount", "externallink"):
        base = f"/admin/integrations/{model}/"
        rows = _accounts(w) if model == "connectedaccount" else ExternalLink.objects.for_lab(w.lab)
        for url in [base, *(f"{base}{o.pk}/change/" for o in rows)]:
            resp = c.get(url)
            assert resp.status_code == 200, url
            pages.append(resp.content.decode())
    return "\n".join(pages)


def _log_records(w):
    return [*w.caplog.get_records("setup"), *w.caplog.records]


@surface
def logs(w):
    fmt = logging.Formatter("%(name)s %(levelname)s %(message)s")
    # format() appends the traceback (exc_info) and stack_info, so `log.exception` is scanned
    return "\n".join(f"{fmt.format(r)} {r.args!r}" for r in _log_records(w))


@surface
def audit_events(w):
    return json.dumps(list(AuditEvent.objects.filter(lab=w.lab).values()), default=str)


@surface
def notifications(w):
    return json.dumps(list(Notification.objects.for_lab(w.lab).values()), default=str)


@surface
def error_messages(w):
    out = []
    for exc in w.errors:
        while exc is not None:  # the whole chain, as a traceback would show it
            out.append(f"{exc!s} {exc!r} {exc.args!r}")
            exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return "\n".join(out)


@surface
def serializers(w):
    return json.dumps(ConnectedAccountSerializer(_accounts(w), many=True).data, default=str)


@surface
def dumpdata(w):
    return django_serializers.serialize("json", _accounts(w))


# ---- API responses (status line, headers and body of every new endpoint, errors included)


def _dump(resp):
    return f"{resp.status_code} {dict(resp.headers)!r} {resp.content.decode(errors='replace')}"


def _lab_url(w, path=""):
    return f"{API}/labs/{w.lab.pk}/{path}"


def _start(w, client):
    resp = client.post(_lab_url(w, "integrations/fake/connect/"), {}, "application/json")
    return resp, parse_qs(urlsplit(resp.json()["authorization_url"]).query)["state"][0]


def _callback(client, **query):
    return _dump(client.get(f"{API}/integrations/oauth/callback/", query))


@surface
def api_providers_and_accounts(w):
    out = []
    for user in w.users.values():
        c = w.client(user)
        for path in (
            "integrations/providers/",
            "integrations/accounts/",
            "integrations/accounts/?all=true",
        ):
            out.append(_dump(c.get(_lab_url(w, path))))
    return "\n".join(out)


@surface
def api_connect_and_callback(w):
    c = w.client(w.users["pi"])
    connect = _lab_url(w, "integrations/{}/connect/")
    start, state = _start(w, c)
    out = [_dump(start)]
    out.append(_dump(c.post(connect.format("nope"), {}, "application/json")))
    out.append(_dump(c.post(connect.format("fake"), {"scopes": ["x"]}, "application/json")))
    # the token endpoint refuses and echoes canaries everywhere it can
    w.transport.on(
        "POST", FAKE.token_url, response(400, {"error": REFRESH[1], "error_description": ACCESS[1]})
    )
    out.append(_callback(c, state=state, code=CODE))
    # success, then a replayed state, a bogus state and a provider error
    _, state = _start(w, c)
    w.transport.on("POST", FAKE.token_url, token_reply(ACCESS[1], REFRESH[1]))
    w.transport.on("GET", FAKE.identity_url, response(200, {"id": "ext-9", "email": "p@fake.test"}))
    out.append(_callback(c, state=state, code=CODE))
    out.append(_callback(c, state=state, code=CODE))
    out.append(_callback(c, state="bogus", code=CODE))
    _, state = _start(w, c)
    out.append(_callback(c, state=state, error="x"))
    out.append(_dump(c.get(_lab_url(w, "integrations/accounts/"))))
    # a second external account while one is active
    _, state = _start(w, c)
    w.transport.on(
        "GET", FAKE.identity_url, response(200, {"id": "ext-10", "email": "x@fake.test"})
    )
    out.append(_callback(c, state=state, code=CODE))
    return "\n".join(out)


@surface
def api_external_links(w):
    pi = w.users["pi"]
    c = w.client(pi)
    _connect(w.transport, pi, w.lab, 1)  # pi's own account; its tokens are canaries
    base = _lab_url(w, f"projects/{w.project.pk}/external-links/")
    file = "https://api.fake.test/files/f9"
    body = {"provider": "fake", "external_id": "f9"}
    item = {
        "name": "Raw.csv",
        "url": "https://fake.test/f9",
        "modifiedTime": "2030-01-01T10:00:00Z",
    }
    w.transport.on("GET", file, response(200, item))
    created = c.post(base, body, "application/json")
    out = [_dump(created)]
    w.transport.on("GET", file, response(500, {"error": ACCESS[1]}))  # provider failure
    out.append(_dump(c.post(base, body, "application/json")))
    w.transport.on("GET", file, response(404, {"error": ACCESS[1]}))  # no such item
    out.append(_dump(c.post(base, body, "application/json")))
    out.append(_dump(c.post(base, {"provider": "nope", "external_id": "f9"}, "application/json")))
    out.append(_dump(c.post(base, {}, "application/json")))
    out.append(_dump(w.client(w.users["viewer"]).post(base, body, "application/json")))
    out.append(_dump(c.get(base)))
    detail = _lab_url(w, f"external-links/{created.json()['id']}/")
    out += [_dump(c.get(detail)), _dump(c.delete(detail)), _dump(c.get(detail))]
    return "\n".join(out)


@surface
def api_disconnect_and_revoke(w):
    member, viewer, pi = w.users["member"], w.users["viewer"], w.users["pi"]
    mine = ConnectedAccount.objects.for_lab(w.lab).get(user=viewer, status="active")
    url = _lab_url(w, f"integrations/accounts/{mine.pk}/")
    out = [_dump(w.client(member).delete(url))]  # not theirs: 404
    echo = response(400, {"error": f"bad {REFRESH[0]} {ACCESS[0]}"})
    w.transport.on("POST", FAKE.revoke_url, echo)
    out.append(_dump(w.client(pi).delete(url)))  # admin revoke
    out.append(_dump(w.client(pi).delete(url)))  # again
    out.append(_dump(w.client(pi).get(_lab_url(w, "integrations/accounts/?all=true"))))
    return "\n".join(out)


@surface
def api_handover(w):
    from labs.models import LabMembership

    out = []
    for user in w.users.values():
        m = LabMembership.objects.for_lab(w.lab).get(user=user)
        out.append(_dump(w.client(w.users["pi"]).get(_lab_url(w, f"members/{m.pk}/handover/"))))
    return "\n".join(out)


@surface
def rotation_command(w):
    from django.conf import settings

    out, err = io.StringIO(), io.StringIO()
    keys = [Fernet.generate_key().decode(), *settings.INTEGRATION_ENCRYPTION_KEYS]
    with override_settings(INTEGRATION_ENCRYPTION_KEYS=keys):
        call_command("rotate_integration_keys", stdout=out, stderr=err)
    return f"{out.getvalue()}\n{err.getvalue()}"


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


@surface
def technical_500_pages(w):
    """DEBUG on, an unexpected error mid-request: Django's technical 500 page lists frame
    locals and settings. Once in the link view with an account in scope, once in the OAuth
    callback while the tokens are in memory."""
    import dataclasses

    from integrations import registry

    c = Client(raise_request_exception=False)
    c.force_login(w.users["pi"])
    _connect(w.transport, w.users["pi"], w.lab, 1)  # pi's own account, tokens are canaries
    pages = []
    base = _lab_url(w, f"projects/{w.project.pk}/external-links/")
    try:
        with override_settings(DEBUG=True):
            registry.PROVIDERS["fake"] = dataclasses.replace(FAKE, fetch_item=_boom)
            body = {"provider": "fake", "external_id": "f7"}
            pages.append(_dump(c.post(base, body, "application/json")))
            registry.PROVIDERS["fake"] = dataclasses.replace(FAKE, parse_identity=_boom)
            ConnectedAccount.objects.for_lab(w.lab).filter(user=w.users["pi"]).update(
                status="revoked"
            )
            _, state = _start(w, c)
            w.transport.on("POST", FAKE.token_url, token_reply(ACCESS[1], REFRESH[1]))
            w.transport.on("GET", FAKE.identity_url, response(200, {"id": "x"}))
            # the code in the URL is the request's own business, so it is not a canary here
            pages.append(_callback(c, state=state, code="plain-code"))
    finally:
        registry.PROVIDERS["fake"] = FAKE
    assert all(p.startswith("500") for p in pages), [p[:60] for p in pages]
    assert all("RuntimeError" in p for p in pages)  # the technical page really rendered
    return "\n".join(pages)


# Surfaces that legitimately hold the stored column: the ciphertext check skips them.
CT_EXEMPT = {"model_reprs", "dumpdata"}


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_no_token_leaks(world, name, settings):
    settings.ROOT_URLCONF = "integrations.tests.admin_urls"  # the app's URLs plus the admin
    text = SURFACES[name](world)
    assert text, f"surface {name} produced nothing to scan"
    leaked = [c for c in world.canaries if c in text]
    assert not leaked, f"{name} leaks {leaked}"
    if name not in CT_EXEMPT:
        stored = [c for c in world.ciphertexts if c in text]
        assert not stored, f"{name} leaks stored ciphertext"


def test_errors_were_collected(world):
    assert len(world.errors) == 4
