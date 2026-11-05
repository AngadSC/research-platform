from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from integrations import http, registry, services
from integrations.tests.fake import FAKE, FakeTransport, response

CLIENT_SECRET = "CANARY-client-secret-7b1e"


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch, settings):
    monkeypatch.setitem(registry.PROVIDERS, FAKE.name, FAKE)
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        FAKE.name: {"client_id": "fake-client", "client_secret": CLIENT_SECRET},
    }
    return FAKE


@pytest.fixture
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(http, "_session", fake)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    return fake


@pytest.fixture
def lab_users(make_lab, make_user, join):
    lab = make_lab()
    users = {role: make_user() for role in ("pi", "lab_admin", "member", "viewer")}
    for role, user in users.items():
        join(user, lab, role)
    return lab, users


def make_request(user, session=None):
    request = RequestFactory().get("/")
    request.user = user
    request.session = session if session is not None else SessionStore()
    return request


def token_reply(access, refresh=None, scope="files.read files.meta", expires_in=3600):
    body = {"access_token": access, "expires_in": expires_in, "token_type": "Bearer"}
    if refresh:
        body["refresh_token"] = refresh
    if scope:
        body["scope"] = scope
    return response(200, body)


@pytest.fixture
def connect(transport):
    """Run the whole OAuth flow for `user` in `lab`; returns the ConnectedAccount."""

    def run(user, lab, *, access="at-1", refresh="rt-1", ext_id="ext-1", email="a@fake.test"):
        request = make_request(user)
        url = services.start_connect(request, lab, FAKE.name)
        state = parse_qs(urlsplit(url).query)["state"][0]
        transport.on("POST", FAKE.token_url, token_reply(access, refresh))
        transport.on("GET", FAKE.identity_url, response(200, {"id": ext_id, "email": email}))
        return services.complete_connect(request, state=state, code="the-code")

    return run
