"""Token-leak test (ARCHITECTURE section 9). Distinctive canary tokens go through the whole account
lifecycle (connect, refresh, refused refresh, provider errors that echo the token, reconnect,
disconnect); then every surface below must be free of every canary.

To cover a new surface (an API response, a serializer, a job's output), add a function decorated
with `@surface` that returns the text to scan. `w` is the World built by the `world` fixture:
`w.client(user)` gives a logged-in test client, `w.users`, `w.lab`, `w.accounts`."""

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from django.core import serializers as django_serializers
from django.test import Client

from audit.models import AuditEvent
from core.models import Notification, User
from integrations import http, services
from integrations.models import ConnectedAccount, ExternalLink
from integrations.serializers import ConnectedAccountSerializer
from integrations.tests.conftest import CLIENT_SECRET, make_request, token_reply
from integrations.tests.fake import FAKE, response

pytestmark = pytest.mark.django_db

ACCESS = [f"CANARY-access-{i}-9f3c2a" for i in range(4)]
REFRESH = [f"CANARY-refresh-{i}-41d7e0" for i in range(4)]
CODE = "CANARY-authcode-5a8b"
FILE_URL = "https://api.fake.test/files/1"


@dataclass
class World:
    lab: object
    users: dict
    accounts: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    log_text: str = ""
    canaries: list = field(default_factory=list)

    def client(self, user):
        c = Client()
        c.force_login(user)
        return c


def _connect(transport, user, lab, i):
    request = make_request(user)
    state = parse_qs(urlsplit(services.start_connect(request, lab, "fake")).query)["state"][0]
    transport.on("POST", FAKE.token_url, token_reply(ACCESS[i], REFRESH[i]))
    transport.on("GET", FAKE.identity_url, response(200, {"id": "ext-1", "email": "a@fake.test"}))
    return services.complete_connect(request, state=state, code=CODE)


def _expect_error(w, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - every error is a surface
        w.errors.append(exc)
    else:
        raise AssertionError("expected an error")


@pytest.fixture
def world(lab_users, transport, caplog, make_project):
    caplog.set_level(logging.DEBUG)
    lab, users = lab_users
    w = World(lab=lab, users=users)
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
    project = make_project(lab)
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

    sent_verifiers = [
        kw["data"].get("code_verifier") for kw in transport.sent("POST", FAKE.token_url)
    ]
    w.canaries = [*ACCESS, *REFRESH, CODE, CLIENT_SECRET, *filter(None, sent_verifiers)]
    # the canaries really went over the wire, so a clean scan means something
    wire = repr(transport.calls)
    assert all(c in wire for c in (ACCESS[1], REFRESH[0], CODE, CLIENT_SECRET))
    w.log_text = "\n".join(
        f"{r.getMessage()} {r.args!r} {r.exc_text or ''}" for r in caplog.records
    )
    return w


SURFACES = {}


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


@surface
def logs(w):
    return w.log_text


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


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_no_token_leaks(world, name, settings):
    settings.ROOT_URLCONF = "integrations.tests.admin_urls"  # the app's URLs plus the admin
    text = SURFACES[name](world)
    assert text, f"surface {name} produced nothing to scan"
    leaked = [c for c in world.canaries if c in text]
    assert not leaked, f"{name} leaks {leaked}"


def test_errors_were_collected(world):
    assert len(world.errors) == 4
