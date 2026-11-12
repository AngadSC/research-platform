"""The AI features as the real clients drive them, with no network and no real account (D245).

- MCP: the tool list every client reads, and the result size limit.
- OAuth: Claude and ChatGPT connecting with their real client metadata documents (as fetched
  from claude.ai and chatgpt.com on 2026-11-10; the fetch itself is faked).
- The in-app assistant: one whole conversation per provider through the real views."""

import dataclasses
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import anthropic
import httpx2 as httpx
import openai
import pytest
from django.test import Client
from jsonschema import Draft202012Validator

from assistant import services, tools
from assistant.models import AIProviderKey
from assistant.tests.fakes import (
    CANARY_KEY,
    OPENAI_CANARY,
    claude_message,
    o_call,
    o_message,
    openai_response,
    patch_claude,
    patch_openai,
    text,
    tool_use,
)
from assistant.tests.test_assistant import api, events, kinds, new_conv, send, url
from assistant.tests.test_mcp import authorize, data, legacy_session, pkce, rpc, token_request
from audit.models import AuditAction, AuditEvent
from projects.models import Task

pytestmark = pytest.mark.django_db
RESOURCE = "https://lab.example.org/mcp"


@pytest.fixture(autouse=True)
def _base(settings):
    settings.MCP_BASE_URL = "https://lab.example.org"
    settings.ALLOWED_HOSTS = ["testserver", "lab.example.org"]


# ---------------------------------------------------------------- MCP tool list


def test_every_tool_is_one_any_client_accepts(world):
    token = services.create_pat(
        world.u.contrib, name="x", lab_ids=[world.lab_a.pk], access="read", days=1
    )[1]
    listed, _ = legacy_session(token)
    assert len(listed) == len(tools.definitions())  # in-app-only tools are not offered
    for t in listed:
        name = t["name"]
        assert len(name) <= 64 and name.replace("_", "").isalnum(), name  # Claude and OpenAI
        assert t["title"] and t["description"], name
        assert t["annotations"]["readOnlyHint"] is not tools.TOOLS[name].write, name
        assert "destructiveHint" in t["annotations"], name
        Draft202012Validator.check_schema(t["inputSchema"])  # MCP's default dialect
        assert t["inputSchema"]["type"] == "object", name


def test_the_biggest_allowed_result_stays_under_the_client_limit(world, monkeypatch):
    """Claude and ChatGPT refuse a tool result past 150,000 characters. The tool layer caps a
    result at MAX_RESULT_CHARS, and the MCP result carries it once (D245)."""
    row = 'say "hi" ' * 10  # quotes, so escaping cannot hide a doubled size
    big = {"rows": [row] * ((tools.MAX_RESULT_CHARS - 100) // len(json.dumps(row) + ", "))}
    assert tools.MAX_RESULT_CHARS - 200 < len(json.dumps(big)) < tools.MAX_RESULT_CHARS
    fake = dataclasses.replace(tools.TOOLS["list_labs"], handler=lambda ctx: big)
    monkeypatch.setitem(tools.TOOLS, "list_labs", fake)
    token = services.create_pat(
        world.u.contrib, name="x", lab_ids=[world.lab_a.pk], access="read", days=1
    )[1]
    result = rpc(token, "tools/call", {"name": "list_labs", "arguments": {}}).json()["result"]
    assert result["isError"] is False
    assert sum(len(c["text"]) for c in result["content"]) < 120_000
    assert set(result) == {"content", "isError"}


# ---------------------------------------------------------------- OAuth as Claude and ChatGPT

CLAUDE_DOC = {
    "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
    "client_name": "Claude",
    "client_uri": "https://claude.ai",
    "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
    "grant_types": [
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:jwt-bearer",
    ],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none",
}
CHATGPT_DOC = {
    "client_id": "https://chatgpt.com/oauth/client.json",
    "client_uri": "https://chatgpt.com/",
    "redirect_uris": ["https://chatgpt.com/connector_platform_oauth_redirect"],
    "token_endpoint_auth_method": "private_key_jwt",
    "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
    "grant_types": [
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:jwt-bearer",
    ],
    "response_types": ["code"],
    "client_name": "ChatGPT",
    "token_endpoint_auth_signing_alg": "RS256",
    "jwks_uri": "https://chatgpt.com/oauth/jwks.json",
}


@pytest.mark.parametrize("doc", [CLAUDE_DOC, CHATGPT_DOC], ids=["claude", "chatgpt"])
def test_a_real_client_connects_end_to_end(world, monkeypatch, doc):
    cid, callback = doc["client_id"], doc["redirect_uris"][0]
    fetched = []

    def fake_send(method, address, **kw):
        fetched.append(address)
        return SimpleNamespace(status_code=200, content=json.dumps(doc).encode())

    monkeypatch.setattr("integrations.http.send", fake_send)

    # 1. the first call has no token: 401 pointing at the protected resource metadata
    first = rpc("", "initialize", {"protocolVersion": "2025-06-18"})
    assert first.status_code == 401
    challenge = first["WWW-Authenticate"]
    prm_url = "https://lab.example.org/.well-known/oauth-protected-resource/mcp"
    assert f'resource_metadata="{prm_url}"' in challenge

    # 2. both well-known documents
    prm = Client().get(urlsplit(prm_url).path).json()
    assert prm["resource"] == RESOURCE and prm["authorization_servers"] == [
        "https://lab.example.org"
    ]
    asm = Client().get("/.well-known/oauth-authorization-server").json()
    assert asm["client_id_metadata_document_supported"] is True
    assert asm["token_endpoint_auth_methods_supported"] == ["none"]
    assert asm["code_challenge_methods_supported"] == ["S256"]
    assert asm["authorization_response_iss_parameter_supported"] is True

    # 3. consent: the metadata document is fetched once and names the app by its host
    verifier, code_challenge = pkce()
    check, redirect = authorize(
        world.u.contrib,
        cid,
        code_challenge,
        labs=[world.lab_a],
        access="read",
        scope="mcp:read",
        redirect=callback,
    )
    assert check["client"]["name"] == doc["client_name"]
    assert check["client"]["verified_host"] == urlsplit(cid).hostname
    assert fetched == [cid]
    assert redirect.startswith(callback + "?")
    q = parse_qs(urlsplit(redirect).query)
    assert q["iss"] == ["https://lab.example.org"] and q["state"] == ["st4te"]

    # 4. token exchange with the resource parameter. ChatGPT may also send its client
    # assertion; it is a public client to us (only "none" is advertised), PKCE binds the code.
    extra = (
        {
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": "a.b.c",
        }
        if doc is CHATGPT_DOC
        else {}
    )
    resp = token_request(
        grant_type="authorization_code",
        code=q["code"][0],
        client_id=cid,
        redirect_uri=callback,
        code_verifier=verifier,
        resource=RESOURCE,
        **extra,
    )
    assert resp.status_code == 200, resp.content
    tok = resp.json()
    assert tok["scope"] == "mcp:read" and tok["token_type"] == "Bearer"

    # 5. the MCP handshake and a read with the access token; a write asks for more scope
    listed, h = legacy_session(tok["access_token"])
    assert {"list_labs", "create_task"} <= {t["name"] for t in listed}
    labs = data(rpc(tok["access_token"], "tools/call", {"name": "list_labs"}, headers=h))
    assert [lab["name"] for lab in labs["labs"]] == ["Lab A"]
    args = {"lab_id": str(world.lab_a.pk), "project_id": str(world.p1.pk), "title": "X"}
    step_up = rpc(tok["access_token"], "tools/call", {"name": "create_task", "arguments": args})
    assert step_up.status_code == 403
    assert 'error="insufficient_scope"' in step_up["WWW-Authenticate"]

    # 6. refresh rotates; the old refresh token coming back ends the grant
    new = token_request(
        grant_type="refresh_token",
        refresh_token=tok["refresh_token"],
        client_id=cid,
        resource=RESOURCE,
        **extra,
    ).json()
    assert new["refresh_token"] != tok["refresh_token"]
    assert rpc(new["access_token"], "ping", {}).status_code == 200
    assert fetched == [cid]  # cached for an hour, not fetched on every call


def test_a_second_allow_keeps_the_grant_the_app_already_has(world, monkeypatch):
    """What happened live with Claude: Allow was clicked twice for one sign-in. The app had
    already swapped the first code for tokens, and the second Allow revoked them."""
    monkeypatch.setattr(
        "integrations.http.send",
        lambda *a, **k: SimpleNamespace(status_code=200, content=json.dumps(CLAUDE_DOC).encode()),
    )
    cid, callback = CLAUDE_DOC["client_id"], CLAUDE_DOC["redirect_uris"][0]
    verifier, challenge = pkce()
    kw = {"labs": [world.lab_a], "access": "read", "redirect": callback}
    _, redirect = authorize(world.u.contrib, cid, challenge, **kw)
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    tok = token_request(
        grant_type="authorization_code",
        code=code,
        client_id=cid,
        redirect_uri=callback,
        code_verifier=verifier,
    ).json()
    authorize(world.u.contrib, cid, challenge, **{**kw, "access": "write"})  # the second click
    assert rpc(tok["access_token"], "ping", {}).status_code == 200
    grants = services.active_grants(world.u.contrib)
    assert [g.access for g in grants] == ["write"]  # one grant, with the latest choice
    # a new sign-in (a new PKCE challenge) still replaces the grant
    authorize(world.u.contrib, cid, pkce()[1], **kw)
    assert rpc(tok["access_token"], "ping", {}).status_code == 401
    assert services.active_grants(world.u.contrib).count() == 1


# ---------------------------------------------------------------- in-app assistant, both providers


def _status_error(cls, code, host, headers=None):
    resp = httpx.Response(
        code, request=httpx.Request("POST", f"https://{host}/v1"), headers=headers or {}, json={}
    )
    return cls(f"echo {CANARY_KEY} {OPENAI_CANARY}", response=resp, body=None)


def _claude(lab, project):
    task = {"lab_id": str(lab.pk), "project_id": str(project.pk), "title": "Order primers"}
    return {
        "patch": patch_claude,
        "turns": [
            claude_message(
                [text("Checking."), tool_use("r1", "list_projects", {"lab_id": str(lab.pk)})],
                stop="tool_use",
            ),
            claude_message([tool_use("w1", "create_task", task)], stop="tool_use"),
            claude_message([text("Added the task.")]),
            claude_message(
                [],
                stop="refusal",
                stop_details={"type": "refusal", "category": "cyber", "explanation": None},
            ),
            _status_error(
                anthropic.RateLimitError,
                429,
                "api.anthropic.com",
                {"retry-after": "7"},
            ),
            _status_error(anthropic.AuthenticationError, 401, "api.anthropic.com"),
        ],
        "write_id": "w1",
        "label": "Anthropic",
    }


def _openai(lab, project):
    task = {"lab_id": str(lab.pk), "project_id": str(project.pk), "title": "Order primers"}
    refusal = {
        "id": "msg_r",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "refusal", "refusal": "I can't help with that."}],
    }
    return {
        "patch": patch_openai,
        "turns": [
            openai_response(
                [
                    o_message("Checking."),
                    o_call("r1", "list_projects", json.dumps({"lab_id": str(lab.pk)})),
                ]
            ),
            openai_response([o_call("w1", "create_task", json.dumps(task))]),
            openai_response([o_message("Added the task.")]),
            openai_response([refusal]),
            _status_error(openai.RateLimitError, 429, "api.openai.com", {"retry-after": "7"}),
            _status_error(openai.AuthenticationError, 401, "api.openai.com"),
        ],
        "write_id": "w1",
        "label": "OpenAI",
    }


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_a_whole_conversation(world, monkeypatch, provider):
    w, lab = world, world.lab_a
    row = AIProviderKey(user=w.u.contrib, provider=provider)
    row.set_key(CANARY_KEY if provider == "anthropic" else OPENAI_CANARY)
    row.save()
    script = (_claude if provider == "anthropic" else _openai)(lab, w.p1)
    fake = script["patch"](monkeypatch, *script["turns"])
    c = api(w.u.contrib)
    conv = new_conv(c, lab, provider=provider)
    before = Task.objects.for_lab(lab).count()

    # a read runs at once; the write that follows waits for the person
    evs = events(send(c, lab, conv, "What projects do we have? Add a task to order primers."))
    assert kinds(evs) == [
        "start",
        "text",
        "tool_start",
        "assistant",
        "tool",
        "tool_start",
        "assistant",
        "approval_required",
        "done",
    ]
    assert [(d["name"], d["status"]) for k, d in evs if k == "tool"] == [("list_projects", "done")]
    waiting = next(d for k, d in evs if k == "approval_required")["calls"]
    assert [(x["id"], x["name"]) for x in waiting] == [(script["write_id"], "create_task")]
    assert Task.objects.for_lab(lab).count() == before

    # approve: the write runs, is audited as the person, and the model is told
    evs = events(
        c.post(
            url(lab, "conversations", conv, "approvals"),
            {"decisions": {script["write_id"]: True}},
            "application/json",
        )
    )
    assert kinds(evs) == ["start", "tool", "text", "assistant", "done"]
    assert Task.objects.for_lab(lab).count() == before + 1
    audit = AuditEvent.objects.get(action=AuditAction.AI_TOOL_WRITE)
    assert audit.actor == w.u.contrib and audit.metadata["via"] == "in_app"
    assert script["write_id"] in json.dumps(fake.calls[2])  # the result went back

    # a refusal is a notice, not an error
    evs = events(send(c, lab, conv, "Something the model will not do"))
    assert kinds(evs) == ["start", "assistant", "notice", "done"]
    assert next(d for k, d in evs if k == "notice")["code"] == "refusal"

    # a rate limit and a bad key are plain messages, never the provider's own text
    label = script["label"]
    evs = events(send(c, lab, conv, "again"))
    err = next(d for k, d in evs if k == "error")
    assert err == {
        "type": "error",
        "code": "rate_limited",
        "message": f"{label} is rate limiting your key. Try again in 7 seconds.",
        "retryable": True,
    }
    evs = events(send(c, lab, conv, "again"))
    err = next(d for k, d in evs if k == "error")
    assert err["message"] == (
        f"{label} rejected your API key. Check it in Settings, under Assistant API keys."
    )
    assert CANARY_KEY not in json.dumps(evs) and OPENAI_CANARY not in json.dumps(evs)

    # the saved conversation shows the same story after a reload
    items = c.get(url(lab, "conversations", conv)).json()["items"]
    assert [i["status"] for i in items if i["kind"] == "tool"] == ["done", "done"]
    assert any(i.get("refusal") for i in items if i["kind"] == "assistant")
