"""Remote MCP server: Streamable HTTP, stateless, JSON responses (D161).

Dual-era (MCP 2026-07-28, "Versioning and Compatibility"): a request whose params carry
`_meta["io.modelcontextprotocol/protocolVersion"]` is served as a modern, per-request-metadata
request (headers validated, `resultType` in results, `server/discover`); an `initialize` request
and anything after it without that `_meta` is served as a legacy (2025-03-26 to 2025-11-25)
client. We never mint `Mcp-Session-Id` (optional in the legacy revisions, removed in the modern
one), never open SSE streams, and answer GET and DELETE with 405.

Every request needs `Authorization: Bearer <access token or PAT>` (D162); the token, its grant,
the user and their lab roles are re-checked on every call (D163)."""

import base64
import binascii
import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables

from assistant import services, tools
from assistant.models import GrantKind

MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26")
PV = "io.modelcontextprotocol/protocolVersion"
CAPS = "io.modelcontextprotocol/clientCapabilities"
CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
SERVER_INFO = {"name": "labbenchos", "title": settings.PRODUCT_NAME, "version": "1.0.0"}
INSTRUCTIONS = (
    f"Tools for {settings.PRODUCT_NAME}, a research lab workspace. Call list_labs first; every "
    "other tool takes a lab_id. You only ever see what the signed-in person can see in the app. "
    "Write tools (create_task, add_task_update, create_decision_draft, add_paper, add_paper_note) "
    "change the lab's records: confirm with the person before calling them."
)
MAX_BODY = 1024 * 1024
RATE = 120  # requests per minute per grant (D166)
WRITE_RATE = 30
POLICY_OFF = -31001  # D188: the lab turned AI assistants off (HTTP 403)
RATE_LIMITED = -31000  # application code, outside the JSON-RPC and MCP reserved ranges


def _rpc_error(rid, code, message, status, data=None, headers=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    body = {"jsonrpc": "2.0", "error": err}
    if rid is not None:
        body["id"] = rid
    resp = JsonResponse(body, status=status)
    for k, v in (headers or {}).items():
        resp[k] = v
    return resp


def _challenge(error=None, scope="mcp:read", description=""):
    parts = []
    if error:
        parts.append(f'error="{error}"')
    if description:
        parts.append(f'error_description="{description}"')
    parts += [f'resource_metadata="{services.prm_url()}"', f'scope="{scope}"']
    return "Bearer " + ", ".join(parts)


def _unauthorized(presented):
    desc = "The access token is missing, expired or revoked." if presented else ""
    resp = JsonResponse(
        {"error": "invalid_token", "error_description": desc or "Sign in required."}, status=401
    )
    resp["WWW-Authenticate"] = _challenge("invalid_token" if presented else None, description=desc)
    return resp


def _origin_ok(request) -> bool:
    """D166: a browser page on another origin must not drive this endpoint (DNS rebinding). No
    Origin header (server-to-server clients such as claude.ai and ChatGPT) is fine; ALLOWED_HOSTS
    already pins the Host header."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    allowed = {settings.MCP_BASE_URL.lower(), *(o.lower() for o in settings.MCP_ALLOWED_ORIGINS)}
    return origin.rstrip("/").lower() in allowed


def _header_value(raw):
    """Decode the `=?base64?...?=` sentinel (Streamable HTTP, Value Encoding)."""
    if raw and raw.startswith("=?base64?") and raw.endswith("?="):
        try:
            return base64.b64decode(raw[9:-2], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return None
    return raw


@sensitive_variables("auth", "raw")
def _bearer(request):
    auth = request.headers.get("Authorization", "")
    scheme, _, raw = auth.partition(" ")
    return raw.strip() if scheme.lower() == "bearer" else ""


@csrf_exempt
@sensitive_variables("raw")
def mcp_endpoint(request):
    if request.method != "POST":
        resp = HttpResponse(status=405)
        resp["Allow"] = "POST"
        return resp
    if not _origin_ok(request):
        return _rpc_error(None, -32600, "Origin not allowed", 403)
    raw = _bearer(request)
    found = services.authenticate(raw)
    if found is None:
        return _unauthorized(bool(raw))
    grant, _token = found
    if services.over_limit(f"mcp:{grant.pk}", RATE):
        return _rpc_error(
            None, RATE_LIMITED, "Rate limit exceeded", 429, headers={"Retry-After": "60"}
        )
    if len(request.body) > MAX_BODY:
        return _rpc_error(None, -32600, "Request too large", 413)
    try:
        msg = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _rpc_error(None, -32700, "Parse error", 400)
    if (
        not isinstance(msg, dict)
        or msg.get("jsonrpc") != "2.0"
        or not isinstance(msg.get("method"), str)
    ):
        return _rpc_error(None, -32600, "Invalid request (batches are not supported)", 400)
    rid, method = msg.get("id"), msg["method"]
    params = msg.get("params") or {}
    if not isinstance(params, dict):
        return _rpc_error(rid, -32602, "params must be an object", 400)
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    modern = PV in meta

    if modern:
        bad = _check_modern(request, rid, method, params, meta)
        if bad is not None:
            return bad
        client_name = (
            (meta.get(CLIENT_INFO) or {}).get("name", "")
            if isinstance(meta.get(CLIENT_INFO), dict)
            else ""
        )
    else:
        header = request.headers.get("MCP-Protocol-Version")
        if header in MODERN:
            return _rpc_error(rid, -32602, f"Missing _meta[{PV}]", 400)
        if method != "initialize" and header and header not in LEGACY:
            return _rpc_error(
                rid,
                -32600,
                "Unsupported protocol version",
                400,
                {"supported": [*MODERN, *LEGACY], "requested": header},
            )
        client_name = ""
    if "id" not in msg:  # a notification (notifications/initialized and the like)
        return HttpResponse(status=202)

    if services.policy_blocked(grant):  # D188: the lab(s) turned AI assistants off
        return _rpc_error(
            rid,
            POLICY_OFF,
            "AI assistants are turned off for this lab by its administrators.",
            403,
        )
    ctx = tools.Context(
        user=grant.user,
        lab_ids=services.granted_lab_ids(grant),
        can_write=grant.access == "write",
        via="mcp",
        client=_client_label(grant, client_name),
        grant_id=str(grant.pk),
        request=request,
    )
    return _dispatch(request, rid, method, params, modern, grant, ctx)


def _client_label(grant, reported):
    """The OAuth client's registered name, else the PAT's label; `reported` (clientInfo) is
    self-asserted, so it is only appended for context (spec: not for security decisions)."""
    base = grant.client.name if grant.client_id else f"access token: {grant.name}"
    reported = str(reported)[:60]
    return f"{base} ({reported})" if reported and reported != base else base


def _check_modern(request, rid, method, params, meta):
    version = meta[PV]
    if not isinstance(meta.get(CAPS), dict):
        return _rpc_error(rid, -32602, f"Missing _meta[{CAPS}]", 400)
    if version not in MODERN:
        return _rpc_error(
            rid,
            -32022,
            "Unsupported protocol version",
            400,
            {"supported": [*MODERN, *LEGACY], "requested": version},
        )
    if request.headers.get("MCP-Protocol-Version") != version:
        return _rpc_error(rid, -32020, "Header mismatch: MCP-Protocol-Version", 400)
    if request.headers.get("Mcp-Method") != method:
        return _rpc_error(rid, -32020, "Header mismatch: Mcp-Method", 400)
    if method == "tools/call" and _header_value(request.headers.get("Mcp-Name")) != params.get(
        "name"
    ):
        return _rpc_error(rid, -32020, "Header mismatch: Mcp-Name", 400)
    return None


def _result(rid, result, modern):
    if modern:
        result = {
            "resultType": "complete",
            **result,
            "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO},
        }
    return JsonResponse({"jsonrpc": "2.0", "id": rid, "result": result})


def _tool_list():
    return [
        {
            "name": d["name"],
            "title": d["title"],
            "description": d["description"],
            "inputSchema": d["input_schema"],
            "annotations": {
                "title": d["title"],
                "readOnlyHint": not d["write"],
                "destructiveHint": False,  # writes only add records; nothing is changed or deleted
                "idempotentHint": not d["write"],
                "openWorldHint": False,
            },
        }
        for d in tools.definitions()
    ]


CAPABILITIES = {"tools": {"listChanged": False}}


def _dispatch(request, rid, method, params, modern, grant, ctx):
    if method == "initialize" and not modern:
        asked = params.get("protocolVersion")
        return _result(
            rid,
            {
                "protocolVersion": asked if asked in LEGACY else LEGACY[0],
                "capabilities": CAPABILITIES,
                "serverInfo": SERVER_INFO,
                "instructions": INSTRUCTIONS,
            },
            modern,
        )
    if method == "ping":
        return _result(rid, {}, modern)
    if method == "server/discover":
        return _result(
            rid,
            {
                "supportedVersions": [*MODERN, *LEGACY],
                "capabilities": CAPABILITIES,
                "instructions": INSTRUCTIONS,
            },
            modern,
        )
    if method == "tools/list":
        return _result(rid, {"tools": _tool_list()}, modern)
    if method == "tools/call":
        return _call_tool(rid, params, modern, grant, ctx)
    return _rpc_error(rid, -32601, f"Method not found: {method}"[:100], 404 if modern else 200)


def _call_tool(rid, params, modern, grant, ctx):
    name = params.get("name")
    if not isinstance(name, str) or name not in tools.TOOLS:
        return _rpc_error(rid, -32602, "Unknown tool", 400 if modern else 200)
    t = tools.TOOLS[name]
    if t.write and not ctx.can_write and grant.kind == GrantKind.OAUTH:
        # Step-up (MCP authorization, "Scope Challenge Handling"): Claude re-runs consent
        resp = JsonResponse(
            {"error": "insufficient_scope", "error_description": "Write access is needed."},
            status=403,
        )
        resp["WWW-Authenticate"] = _challenge(
            "insufficient_scope", "mcp:read mcp:write", "Write access is needed."
        )
        return resp
    if t.write and services.over_limit(f"mcp-write:{grant.pk}", WRITE_RATE):
        return _rpc_error(
            rid, RATE_LIMITED, "Rate limit exceeded", 429, headers={"Retry-After": "60"}
        )
    try:
        result = tools.call(ctx, name, params.get("arguments"))
    except tools.ToolError as exc:
        return _result(
            rid, {"content": [{"type": "text", "text": str(exc)}], "isError": True}, modern
        )
    # D245: the JSON once, as text. No `structuredContent` copy (we declare no outputSchema): a
    # second copy doubled every result the model reads and could push a big one past the 150,000
    # character limit clients put on a tool result.
    text = json.dumps(result, ensure_ascii=False)
    return _result(rid, {"content": [{"type": "text", "text": text}], "isError": False}, modern)
