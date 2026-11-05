"""Token-leak test for AI access (D162). Real tokens (a PAT, an authorization code, access and
refresh tokens, a PKCE verifier) go through creation, use, refresh, replay, revocation and errors;
after creation none of them may appear in any API response, log line, audit event, model repr,
dumpdata output, MCP or OAuth error body, or the DEBUG 500 page.

The one allowed exposure is the response that creates the token (the PAT create response, the
consent redirect carrying the code, the token endpoint's success body)."""

import io
import json
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.management import call_command
from django.test import Client
from django.test.utils import override_settings

from assistant import services
from assistant.models import AIGrant, AIToken, OAuthClient
from assistant.tests.reauth import sign_in
from assistant.tests.test_mcp import CLAUDE_CB, authorize, pkce, register, rpc, token_request
from audit.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _base(settings):
    settings.MCP_BASE_URL = "https://lab.example.org"
    settings.ALLOWED_HOSTS = ["testserver", "lab.example.org"]


def _boom(*args, **kwargs):
    raise RuntimeError("boom")


def test_no_token_appears_after_creation(world, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    seen = []  # text from every surface after creation
    canaries = []

    def dump(resp):
        return f"{resp.status_code} {dict(resp.headers)} {resp.content.decode(errors='replace')}"

    # --- a personal access token
    api = sign_in(Client(), world.u.contrib)
    created = api.post(
        "/api/ai/grants/",
        {"name": "CLI", "labs": [str(world.lab_a.pk)], "access": "write", "expires_in_days": 7},
        "application/json",
    )
    pat = created.json()["token"]
    canaries.append(pat)
    seen += [dump(api.get("/api/ai/grants/"))]
    pi = Client()
    pi.force_login(world.u.pi)
    seen += [dump(pi.get(f"/api/labs/{world.lab_a.pk}/ai-grants/"))]
    seen += [dump(rpc(pat, "tools/call", {"name": "list_labs", "arguments": {}}))]
    seen += [dump(rpc(pat, "tools/call", {"name": "nope"}))]
    seen += [dump(rpc(pat, "tools/call", {"name": "list_projects", "arguments": {"lab_id": "x"}}))]

    # --- the OAuth flow: code, verifier, access and refresh tokens
    client_id = register()
    verifier, challenge = pkce()
    canaries.append(verifier)
    check, redirect = authorize(world.u.contrib, client_id, challenge, labs=[world.lab_a])
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    canaries.append(code)
    tok = token_request(
        grant_type="authorization_code",
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_CB,
        code_verifier=verifier,
    ).json()
    canaries += [tok["access_token"], tok["refresh_token"]]
    seen += [dump(rpc(tok["access_token"], "tools/list", {}))]
    replay_code = token_request(
        grant_type="authorization_code",
        code=code,
        client_id=client_id,
        redirect_uri=CLAUDE_CB,
        code_verifier=verifier,
    )
    seen += [dump(replay_code)]  # the code came back: the grant ends
    seen += [dump(rpc(tok["access_token"], "ping", {}))]  # revoked now: 401
    seen += [
        dump(
            token_request(
                grant_type="refresh_token", refresh_token=tok["refresh_token"], client_id=client_id
            )
        )
    ]

    # a second flow, refreshed and then replayed
    verifier2, challenge2 = pkce()
    _, redirect2 = authorize(world.u.contrib, client_id, challenge2, labs=[world.lab_a])
    code2 = parse_qs(urlsplit(redirect2).query)["code"][0]
    tok2 = token_request(
        grant_type="authorization_code",
        code=code2,
        client_id=client_id,
        redirect_uri=CLAUDE_CB,
        code_verifier=verifier2,
    ).json()
    fresh = token_request(
        grant_type="refresh_token", refresh_token=tok2["refresh_token"], client_id=client_id
    ).json()
    canaries += [verifier2, code2, tok2["access_token"], tok2["refresh_token"]]
    canaries += [fresh["access_token"], fresh["refresh_token"]]
    seen += [
        dump(
            token_request(
                grant_type="refresh_token", refresh_token=tok2["refresh_token"], client_id=client_id
            )
        )
    ]
    seen += [
        dump(api.get("/api/ai/grants/")),
        dump(pi.get(f"/api/labs/{world.lab_a.pk}/ai-grants/")),
    ]

    # --- revocation of the PAT, then its use
    grant = AIGrant.objects.get(kind="pat")
    seen += [dump(api.delete(f"/api/ai/grants/{grant.pk}/")), dump(rpc(pat, "ping", {}))]

    # --- the DEBUG 500 page with tokens in memory (MCP call and token exchange)
    verifier3, challenge3 = pkce()
    _, redirect3 = authorize(world.u.contrib, client_id, challenge3, labs=[world.lab_a])
    code3 = parse_qs(urlsplit(redirect3).query)["code"][0]
    canaries += [verifier3, code3]
    _, pat2 = services.create_pat(
        world.u.pi, name="x", lab_ids=[world.lab_a.pk], access="read", days=1
    )
    canaries.append(pat2)
    raw = Client(raise_request_exception=False)
    with override_settings(DEBUG=True):
        monkeypatch.setattr(services, "_token_pair", _boom)
        page = raw.post(
            "/api/oauth/token/",
            {
                "grant_type": "authorization_code",
                "code": code3,
                "client_id": client_id,
                "redirect_uri": CLAUDE_CB,
                "code_verifier": verifier3,
            },
        )
        from assistant import tools

        monkeypatch.setattr(tools, "call", _boom)
        page2 = raw.post(
            "/mcp",
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_labs"}}
            ),
            "application/json",
            HTTP_AUTHORIZATION=f"Bearer {pat2}",
        )
    assert page.status_code == page2.status_code == 500
    assert b"RuntimeError" in page.content and b"RuntimeError" in page2.content
    seen += [dump(page), dump(page2)]

    # --- stored state
    seen.append(caplog.text)
    seen += [json.dumps(list(AuditEvent.objects.values()), default=str)]
    for model in (AIGrant, AIToken, OAuthClient):
        for obj in model.objects.all():
            seen += [str(obj), repr(obj), str(obj.__dict__)]
    out = io.StringIO()
    call_command("dumpdata", "assistant", "audit", stdout=out)
    seen.append(out.getvalue())
    seen.append(json.dumps(check))

    text = "\n".join(seen)
    assert len(canaries) == 14
    leaked = [c[:8] + "..." for c in canaries if c in text]
    assert not leaked, leaked
