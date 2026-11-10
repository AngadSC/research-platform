"""The MCP server and its OAuth server, through the real HTTP endpoints (D161-D166)."""

import base64
import hashlib
import json
import secrets
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from rest_framework.test import APIClient

from assistant import services
from assistant.models import AIGrant, OAuthClient
from assistant.tests.reauth import sign_in
from audit.models import AuditAction, AuditEvent
from labs.models import LabMembership

pytestmark = pytest.mark.django_db
MCP = "/mcp"
CLAUDE_CB = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(autouse=True)
def _base(settings):
    settings.MCP_BASE_URL = "https://lab.example.org"
    settings.ALLOWED_HOSTS = ["testserver", "lab.example.org"]


def rpc(token, method, params=None, *, rid=1, headers=None, client=None):
    body = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        body["id"] = rid
    if params is not None:
        body["params"] = params
    extra = {"HTTP_ACCEPT": "application/json, text/event-stream"}
    if token:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    for k, v in (headers or {}).items():
        extra["HTTP_" + k.upper().replace("-", "_")] = v
    return (client or Client()).post(MCP, json.dumps(body), "application/json", **extra)


def pat(user, *labs, access="read"):
    _, token = services.create_pat(
        user, name="CLI", lab_ids=[lab.pk for lab in labs], access=access, days=30
    )
    return token


def legacy_session(token):
    """initialize, notifications/initialized, tools/list: the 2025-06-18 handshake."""
    init = rpc(
        token,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "claude-ai", "version": "1"},
        },
    )
    assert init.status_code == 200, init.content
    assert init.json()["result"]["protocolVersion"] == "2025-06-18"
    assert "Mcp-Session-Id" not in init
    h = {"MCP-Protocol-Version": "2025-06-18"}
    assert rpc(token, "notifications/initialized", rid=None, headers=h).status_code == 202
    listed = rpc(token, "tools/list", {}, rid=2, headers=h)
    assert listed.status_code == 200
    return listed.json()["result"]["tools"], h


# ---------------------------------------------------------------- protocol with a PAT


def test_legacy_initialize_list_call_with_a_pat(world):
    token = pat(world.u.contrib, world.lab_a)
    tools_, h = legacy_session(token)
    names = [t["name"] for t in tools_]
    assert names[:2] == ["list_labs", "list_projects"] and "create_task" in names
    assert {"list_papers", "read_paper", "cite_paper", "add_paper_note"} <= set(names)
    by = {t["name"]: t for t in tools_}
    assert by["read_paper"]["annotations"]["readOnlyHint"] is True
    assert by["add_paper_note"]["annotations"]["readOnlyHint"] is False
    assert by["list_tasks"]["annotations"]["readOnlyHint"] is True
    assert by["create_task"]["annotations"] == {
        "title": "Create a task",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    resp = rpc(token, "tools/call", {"name": "list_labs", "arguments": {}}, rid=3, headers=h)
    result = resp.json()["result"]
    assert result["isError"] is False and "resultType" not in result
    assert result["structuredContent"]["labs"] == [
        {"id": str(world.lab_a.pk), "name": "Lab A", "your_role": "member"}
    ]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert rpc(token, "ping", {}, rid=4, headers=h).json()["result"] == {}


def modern_headers(method, name=None):
    h = {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name:
        h["Mcp-Name"] = name
    return h


META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "ExampleClient", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


def test_modern_discover_list_call_with_a_pat(world):
    token = pat(world.u.contrib, world.lab_a)
    d = rpc(token, "server/discover", {"_meta": META}, headers=modern_headers("server/discover"))
    assert d.status_code == 200
    r = d.json()["result"]
    assert r["resultType"] == "complete" and "2026-07-28" in r["supportedVersions"]
    assert r["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "labbenchos"
    listed = rpc(token, "tools/list", {"_meta": META}, headers=modern_headers("tools/list"))
    assert listed.json()["result"]["resultType"] == "complete"
    call = rpc(
        token,
        "tools/call",
        {"name": "list_projects", "arguments": {"lab_id": str(world.lab_a.pk)}, "_meta": META},
        headers=modern_headers("tools/call", "list_projects"),
    )
    assert [p["name"] for p in call.json()["result"]["structuredContent"]["projects"]] == [
        "P1 open"
    ]
    encoded = "=?base64?" + base64.b64encode(b"list_labs").decode() + "?="
    ok = rpc(
        token,
        "tools/call",
        {"name": "list_labs", "arguments": {}, "_meta": META},
        headers=modern_headers("tools/call", encoded),
    )
    assert ok.status_code == 200


@pytest.mark.parametrize(
    ("headers", "meta", "code"),
    [
        (
            modern_headers("tools/list"),
            {**META, "io.modelcontextprotocol/protocolVersion": "1900-01-01"},
            -32022,
        ),
        ({"MCP-Protocol-Version": "2025-06-18", "Mcp-Method": "tools/list"}, META, -32020),
        (modern_headers("tools/call"), META, -32020),
        (
            modern_headers("tools/list"),
            {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
            -32602,
        ),
    ],
)
def test_modern_validation_errors_are_400(world, headers, meta, code):
    token = pat(world.u.contrib, world.lab_a)
    resp = rpc(token, "tools/list", {"_meta": meta}, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == code


def test_unknown_method_and_tool(world):
    token = pat(world.u.contrib, world.lab_a)
    assert rpc(token, "resources/list", {}).json()["error"]["code"] == -32601
    modern = rpc(token, "resources/list", {"_meta": META}, headers=modern_headers("resources/list"))
    assert modern.status_code == 404 and modern.json()["error"]["code"] == -32601
    assert rpc(token, "tools/call", {"name": "nope"}).json()["error"]["code"] == -32602


def test_tool_errors_are_results_not_protocol_errors(world):
    token = pat(world.u.contrib, world.lab_a)
    resp = rpc(
        token, "tools/call", {"name": "list_projects", "arguments": {"lab_id": str(world.lab_b.pk)}}
    )
    result = resp.json()["result"]
    assert resp.status_code == 200 and result["isError"] is True
    assert "No lab with that id" in result["content"][0]["text"]


def test_read_only_pat_gets_a_tool_error_for_writes(world):
    token = pat(world.u.contrib, world.lab_a)
    args = {"lab_id": str(world.lab_a.pk), "project_id": str(world.p1.pk), "title": "X"}
    resp = rpc(token, "tools/call", {"name": "create_task", "arguments": args})
    assert resp.status_code == 200 and resp.json()["result"]["isError"] is True


def test_transport_rules(world):
    token = pat(world.u.contrib, world.lab_a)
    auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    assert Client().get(MCP, **auth).status_code == 405
    assert Client().delete(MCP, **auth).status_code == 405
    bad_origin = rpc(token, "ping", {}, headers={"Origin": "https://evil.example"})
    assert bad_origin.status_code == 403
    same = rpc(token, "ping", {}, headers={"Origin": "https://lab.example.org"})
    assert same.status_code == 200
    batch = Client().post(MCP, "[]", "application/json", **auth)
    assert batch.status_code == 400 and batch.json()["error"]["code"] == -32600
    junk = Client().post(MCP, "{", "application/json", **auth)
    assert junk.json()["error"]["code"] == -32700


def test_missing_or_bad_token_is_401_with_metadata_pointer(world):
    for token in ("", "rwp_nope"):
        resp = rpc(token, "initialize", {"protocolVersion": "2025-06-18"})
        assert resp.status_code == 401
        challenge = resp["WWW-Authenticate"]
        assert challenge.startswith("Bearer ")
        assert (
            'resource_metadata="https://lab.example.org/.well-known/oauth-protected-resource/mcp"'
            in challenge
        )
        assert 'scope="mcp:read"' in challenge
    session = Client()
    session.force_login(world.u.contrib)  # a browser session is never accepted here
    assert rpc(None, "ping", {}, client=session).status_code == 401


def test_deactivation_removal_and_revocation_take_effect_at_once(world):
    token = pat(world.u.contrib, world.lab_a)
    args = {"name": "list_projects", "arguments": {"lab_id": str(world.lab_a.pk)}}
    assert rpc(token, "tools/call", args).json()["result"]["isError"] is False
    LabMembership.objects.for_lab(world.lab_a).filter(user=world.u.contrib).delete()
    assert rpc(token, "tools/call", args).json()["result"]["isError"] is True
    world.u.contrib.is_active = False
    world.u.contrib.save()
    assert rpc(token, "ping", {}).status_code == 401
    other = pat(world.u.pi, world.lab_a)
    services.revoke(AIGrant.objects.get(user=world.u.pi), by=world.u.pi)
    assert rpc(other, "ping", {}).status_code == 401


def test_rate_limit_per_grant(world, monkeypatch):
    from assistant import mcp

    monkeypatch.setattr(mcp, "RATE", 2)
    token = pat(world.u.contrib, world.lab_a)
    codes = [rpc(token, "ping", {}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---------------------------------------------------------------- OAuth


def test_metadata_documents():
    prm = Client().get("/.well-known/oauth-protected-resource/mcp").json()
    assert prm["resource"] == "https://lab.example.org/mcp"
    assert prm["authorization_servers"] == ["https://lab.example.org"]
    assert Client().get("/.well-known/oauth-protected-resource").json() == prm
    asm = Client().get("/.well-known/oauth-authorization-server").json()
    assert asm["issuer"] == "https://lab.example.org"
    assert asm["authorization_endpoint"] == "https://lab.example.org/oauth/authorize"
    assert asm["code_challenge_methods_supported"] == ["S256"]
    assert asm["token_endpoint_auth_methods_supported"] == ["none"]
    assert asm["client_id_metadata_document_supported"] is True


def pkce():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def register(redirect=CLAUDE_CB, name="Claude"):
    resp = Client().post(
        "/api/oauth/register/",
        json.dumps(
            {
                "client_name": name,
                "redirect_uris": [redirect],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        ),
        "application/json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()["client_id"]


def authorize(
    user,
    client_id,
    challenge,
    *,
    labs,
    access="write",
    scope="mcp:read mcp:write",
    redirect=CLAUDE_CB,
):
    api = sign_in(APIClient(), user)
    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "st4te",
        "scope": scope,
        "resource": "https://lab.example.org/mcp",
    }
    check = api.post("/api/oauth/authorize/", {**query, "decision": "check"}, format="json")
    assert check.status_code == 200, check.content
    approve = api.post(
        "/api/oauth/authorize/",
        {**query, "decision": "approve", "labs": [str(lab.pk) for lab in labs], "access": access},
        format="json",
    )
    assert approve.status_code == 200, approve.content
    return check.json(), approve.json()["redirect"]


def token_request(**form):
    return Client().post("/api/oauth/token/", form)


def full_flow(user, labs, **kw):
    client_id = register()
    verifier, challenge = pkce()
    _, redirect = authorize(user, client_id, challenge, labs=labs, **kw)
    q = parse_qs(urlsplit(redirect).query)
    assert redirect.startswith(CLAUDE_CB + "?")
    assert q["state"] == ["st4te"] and q["iss"] == ["https://lab.example.org"]
    resp = token_request(
        grant_type="authorization_code",
        code=q["code"][0],
        client_id=client_id,
        redirect_uri=CLAUDE_CB,
        code_verifier=verifier,
        resource="https://lab.example.org/mcp",
    )
    assert resp.status_code == 200, resp.content
    assert resp["Cache-Control"] == "no-store"
    return client_id, q["code"][0], verifier, resp.json()


def test_oauth_flow_then_mcp_with_the_access_token(world):
    _, _, _, tok = full_flow(world.u.contrib, [world.lab_a])
    assert tok["token_type"] == "Bearer" and tok["scope"] == "mcp:read mcp:write"
    assert tok["access_token"].startswith("rwa_") and tok["refresh_token"].startswith("rwr_")
    tools_, h = legacy_session(tok["access_token"])
    args = {"lab_id": str(world.lab_a.pk), "project_id": str(world.p1.pk), "title": "From Claude"}
    resp = rpc(
        tok["access_token"], "tools/call", {"name": "create_task", "arguments": args}, headers=h
    )
    assert resp.json()["result"]["isError"] is False, resp.content
    event = AuditEvent.objects.get(action=AuditAction.AI_TOOL_WRITE)
    assert event.metadata["via"] == "mcp" and event.metadata["client"].startswith("Claude")
    granted = AuditEvent.objects.get(action=AuditAction.AI_ACCESS_GRANTED)
    assert granted.lab == world.lab_a and granted.actor == world.u.contrib


def test_consent_check_describes_the_request(world):
    client_id = register(name="Totally Claude")
    _, challenge = pkce()
    check, _ = authorize(world.u.contrib, client_id, challenge, labs=[world.lab_a])
    assert check["client"] == {
        "name": "Totally Claude",
        "verified_host": None,  # DCR names are self-reported
        "redirect_host": "claude.ai",
        "loopback": False,
    }
    assert [lab["name"] for lab in check["labs"]] == ["Lab A"]


def test_read_scope_by_default_and_write_needs_step_up(world):
    _, _, _, tok = full_flow(world.u.contrib, [world.lab_a], access="read", scope="mcp:read")
    assert tok["scope"] == "mcp:read"
    args = {"lab_id": str(world.lab_a.pk), "project_id": str(world.p1.pk), "title": "X"}
    resp = rpc(tok["access_token"], "tools/call", {"name": "create_task", "arguments": args})
    assert resp.status_code == 403
    assert 'error="insufficient_scope"' in resp["WWW-Authenticate"]
    assert 'scope="mcp:read mcp:write"' in resp["WWW-Authenticate"]


def test_person_can_downgrade_a_write_request_to_read(world):
    _, _, _, tok = full_flow(world.u.contrib, [world.lab_a], access="read")
    assert tok["scope"] == "mcp:read"


def test_person_can_choose_write_when_the_app_asked_only_for_read(world):
    _, _, _, tok = full_flow(world.u.contrib, [world.lab_a], access="write", scope="mcp:read")
    assert tok["scope"] == "mcp:read mcp:write"


@pytest.mark.parametrize(
    ("declared", "accepted"),
    [
        (  # ChatGPT's real document
            {
                "token_endpoint_auth_method": "private_key_jwt",
                "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
            },
            True,
        ),
        ({"token_endpoint_auth_method": "none"}, True),
        ({}, True),
        ({"token_endpoint_auth_method": "private_key_jwt"}, False),
        ({"token_endpoint_auth_methods_supported": ["client_secret_post"]}, False),
    ],
)
def test_cimd_client_must_be_able_to_work_without_a_secret(monkeypatch, declared, accepted):
    url = "https://chatgpt.com/oauth/client.json"
    body = json.dumps({"client_id": url, **declared}).encode()
    reply = SimpleNamespace(status_code=200, content=body)
    monkeypatch.setattr("integrations.http.send", lambda *a, **k: reply)
    if accepted:
        assert services._fetch_cimd(url)["client_id"] == url
    else:
        with pytest.raises(services.OAuthError):
            services._fetch_cimd(url)


def test_refresh_rotates_and_replay_ends_the_grant(world):
    client_id, code, verifier, tok = full_flow(world.u.contrib, [world.lab_a])
    first = token_request(
        grant_type="refresh_token", refresh_token=tok["refresh_token"], client_id=client_id
    )
    assert first.status_code == 200
    new = first.json()
    assert new["refresh_token"] != tok["refresh_token"]
    assert rpc(new["access_token"], "ping", {}).status_code == 200
    replay = token_request(
        grant_type="refresh_token", refresh_token=tok["refresh_token"], client_id=client_id
    )
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"
    assert rpc(new["access_token"], "ping", {}).status_code == 401  # whole grant revoked
    revoked = AuditEvent.objects.get(action=AuditAction.AI_ACCESS_REVOKED)
    assert revoked.actor is None and revoked.actor_label == "assistant:token_replay"


def test_code_is_single_use_and_bound_to_pkce_client_and_redirect(world):
    client_id = register()
    verifier, challenge = pkce()
    _, redirect = authorize(world.u.contrib, client_id, challenge, labs=[world.lab_a])
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    base = {"grant_type": "authorization_code", "code": code, "redirect_uri": CLAUDE_CB}
    other = register()
    assert (
        token_request(**base, client_id=other, code_verifier=verifier).json()["error"]
        == "invalid_grant"
    )
    # the failed attempt above did not spend it (wrong client is checked first)
    bad = token_request(**base, client_id=client_id, code_verifier="wrong" * 10)
    assert bad.json()["error"] == "invalid_grant"
    again = token_request(**base, client_id=client_id, code_verifier=verifier)
    assert again.json()["error"] == "invalid_grant"  # a failed PKCE check burns the code


def test_registration_and_authorization_refusals(world):
    bad = Client().post(
        "/api/oauth/register/",
        json.dumps({"redirect_uris": ["https://evil.example/cb"]}),
        "application/json",
    )
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_redirect_uri"
    loop = register(redirect="http://localhost/callback", name="Claude Code")
    verifier, challenge = pkce()
    check, redirect = authorize(
        world.u.contrib,
        loop,
        challenge,
        labs=[world.lab_a],
        redirect="http://localhost:53682/callback",
    )
    assert check["client"]["loopback"] is True and redirect.startswith(
        "http://localhost:53682/callback?"
    )
    api = sign_in(APIClient(), world.u.contrib)
    base = {
        "response_type": "code",
        "client_id": loop,
        "redirect_uri": "http://localhost/callback",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "decision": "check",
    }
    unknown = api.post("/api/oauth/authorize/", {**base, "client_id": "nope"}, format="json")
    assert unknown.status_code == 400 and "redirect" not in unknown.json()
    wrong_uri = api.post(
        "/api/oauth/authorize/", {**base, "redirect_uri": CLAUDE_CB}, format="json"
    )
    assert wrong_uri.status_code == 400 and "redirect" not in wrong_uri.json()
    plain = api.post(
        "/api/oauth/authorize/", {**base, "code_challenge_method": "plain"}, format="json"
    )
    assert plain.status_code == 400 and "error=invalid_request" in plain.json()["redirect"]
    outsider_lab = api.post(
        "/api/oauth/authorize/",
        {**base, "decision": "approve", "labs": [str(world.lab_b.pk)]},
        format="json",
    )
    assert outsider_lab.status_code == 400
    deny = api.post("/api/oauth/authorize/", {**base, "decision": "deny"}, format="json")
    assert "error=access_denied" in deny.json()["redirect"]
    anon = APIClient().post("/api/oauth/authorize/", base, format="json")
    assert anon.status_code in (401, 403)


def test_cimd_client_is_fetched_from_an_allowed_host(world, monkeypatch):
    url = "https://claude.ai/oauth/claude-client-metadata"
    fetched = []

    def fake_fetch(client_id):
        fetched.append(client_id)
        return {"client_id": client_id, "client_name": "Claude", "redirect_uris": [CLAUDE_CB]}

    monkeypatch.setattr(services, "_fetch_cimd", fake_fetch)
    verifier, challenge = pkce()
    check, redirect = authorize(world.u.contrib, url, challenge, labs=[world.lab_a])
    assert check["client"]["verified_host"] == "claude.ai"
    assert fetched == [url]  # cached for the approve step
    code = parse_qs(urlsplit(redirect).query)["code"][0]
    resp = token_request(
        grant_type="authorization_code",
        code=code,
        client_id=url,
        redirect_uri=CLAUDE_CB,
        code_verifier=verifier,
    )
    assert resp.status_code == 200
    with pytest.raises(services.OAuthError):
        services.resolve_client("https://evil.example/metadata.json")
    assert OAuthClient.objects.filter(client_id__contains="evil").count() == 0


def test_reconsent_replaces_the_previous_grant_for_that_client(world):
    client_id = register()
    for _ in range(2):
        _, challenge = pkce()
        authorize(world.u.contrib, client_id, challenge, labs=[world.lab_a])
    assert services.active_grants(world.u.contrib).count() == 1


# ---------------------------------------------------------------- grant management API


def test_pat_create_list_revoke(world):
    api = sign_in(APIClient(), world.u.contrib)
    resp = api.post(
        "/api/ai/grants/",
        {
            "name": "Claude Code",
            "labs": [str(world.lab_a.pk)],
            "access": "read",
            "expires_in_days": 30,
        },
        format="json",
    )
    assert resp.status_code == 201
    token = resp.json()["token"]
    assert token.startswith("rwp_")
    listed = api.get("/api/ai/grants/").json()
    assert [g["name"] for g in listed] == ["Claude Code"] and "token" not in listed[0]
    assert rpc(token, "ping", {}).status_code == 200
    assert api.delete(f"/api/ai/grants/{listed[0]['id']}/").status_code == 204
    assert rpc(token, "ping", {}).status_code == 401
    assert api.get("/api/ai/grants/").json() == []
    lab_b = api.post(
        "/api/ai/grants/",
        {"name": "x", "labs": [str(world.lab_b.pk)], "access": "read", "expires_in_days": 30},
        format="json",
    )
    assert lab_b.status_code == 400


def test_lab_manager_removes_their_lab_from_a_members_grant(world, make_lab, join):
    from labs.models import LabRole

    lab_c = make_lab("Lab C")
    join(world.u.contrib, lab_c, LabRole.MEMBER)
    token = pat(world.u.contrib, world.lab_a, lab_c)
    pi = APIClient()
    pi.force_login(world.u.pi)
    listed = pi.get(f"/api/labs/{world.lab_a.pk}/ai-grants/").json()
    assert [(g["user"]["display_name"], g["kind"]) for g in listed] == [("Contrib", "pat")]
    member = APIClient()
    member.force_login(world.u.contrib)
    assert member.get(f"/api/labs/{world.lab_a.pk}/ai-grants/").status_code == 403
    assert pi.delete(f"/api/labs/{world.lab_a.pk}/ai-grants/{listed[0]['id']}/").status_code == 204
    labs = rpc(token, "tools/call", {"name": "list_labs", "arguments": {}}).json()["result"]
    assert [lab["name"] for lab in labs["structuredContent"]["labs"]] == ["Lab C"]
    assert pi.get(f"/api/labs/{world.lab_a.pk}/ai-grants/").json() == []
