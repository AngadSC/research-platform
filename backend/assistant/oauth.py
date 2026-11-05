"""OAuth 2.1 authorization server endpoints for the MCP server (D161, D165). Plain Django views:
they are protocol endpoints for MCP clients, not the SPA's API (the consent API is in views.py).

- `/.well-known/oauth-protected-resource[/mcp]`: RFC 9728 protected resource metadata
- `/.well-known/oauth-authorization-server`: RFC 8414 authorization server metadata
- `/api/oauth/register/`: RFC 7591 dynamic client registration (public clients only)
- `/api/oauth/token/`: authorization_code (PKCE S256) and refresh_token (rotating) grants
The authorization endpoint is the SPA page `/oauth/authorize` (sign-in, MFA, then consent)."""

import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST

from assistant import services
from assistant.models import OAuthClient
from assistant.services import OAuthError

REGISTER_RATE = 20  # per client IP per hour
TOKEN_RATE = 60  # per client IP per minute


def _ip(request):
    from audit.services import _client_ip

    return _client_ip(request) or "unknown"


def _public(data, status=200):
    resp = JsonResponse(data, status=status)
    resp["Access-Control-Allow-Origin"] = "*"  # public metadata; helps browser-based MCP clients
    resp["Cache-Control"] = "public, max-age=300"
    return resp


def _no_store(data, status=200):
    resp = JsonResponse(data, status=status)
    resp["Cache-Control"] = "no-store"
    resp["Pragma"] = "no-cache"
    return resp


def _error(exc: OAuthError):
    body = {"error": exc.code}
    if exc.description:
        body["error_description"] = exc.description
    return _no_store(body, exc.status)


@require_GET
def protected_resource(request):
    return _public(
        {
            "resource": services.mcp_url(),
            "authorization_servers": [settings.MCP_BASE_URL],
            "scopes_supported": ["mcp:read", "mcp:write"],
            "bearer_methods_supported": ["header"],
            "resource_name": settings.PRODUCT_NAME,
        }
    )


@require_GET
def authorization_server(request):
    base = settings.MCP_BASE_URL
    return _public(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/oauth/authorize",
            "token_endpoint": f"{base}/api/oauth/token/",
            "registration_endpoint": f"{base}/api/oauth/register/",
            "scopes_supported": ["mcp:read", "mcp:write", "offline_access"],
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "client_id_metadata_document_supported": True,
            "authorization_response_iss_parameter_supported": True,
        }
    )


@csrf_exempt
@require_POST
def register(request):
    if services.over_limit(f"oauth-register:{_ip(request)}", REGISTER_RATE, 3600):
        return _no_store({"error": "slow_down"}, 429)
    try:
        meta = json.loads(request.body or b"{}")
        if not isinstance(meta, dict):
            raise ValueError
    except ValueError:
        return _error(OAuthError("invalid_client_metadata", "Send a JSON object."))
    try:
        client = services.register_client(meta)
    except OAuthError as exc:
        return _error(exc)
    return _no_store(
        {
            "client_id": client.client_id,
            "client_id_issued_at": int(client.created_at.timestamp()),
            "client_name": client.name,
            "redirect_uris": client.redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        201,
    )


@csrf_exempt
@require_POST
@sensitive_post_parameters("code", "code_verifier", "refresh_token")
def token(request):
    if services.over_limit(f"oauth-token:{_ip(request)}", TOKEN_RATE):
        return _no_store({"error": "slow_down"}, 429)
    p = request.POST  # application/x-www-form-urlencoded (RFC 6749 section 4.1.3)
    try:
        client_id = p.get("client_id", "")
        if not OAuthClient.objects.filter(client_id=client_id).exists():
            # unknown (CIMD clients are stored at authorization): Claude re-registers on this
            raise OAuthError("invalid_client", "Unknown app.", 401)
        grant_type = p.get("grant_type")
        if grant_type == "authorization_code":
            body = services.exchange_code(
                code=p.get("code", ""),
                client_id=client_id,
                redirect_uri=p.get("redirect_uri", ""),
                verifier=p.get("code_verifier", ""),
                resource=p.get("resource", ""),
            )
        elif grant_type == "refresh_token":
            body = services.refresh(
                refresh_token=p.get("refresh_token", ""),
                client_id=client_id,
                resource=p.get("resource", ""),
            )
        else:
            raise OAuthError("unsupported_grant_type")
    except OAuthError as exc:
        if exc.code == "invalid_client":
            exc.status = 401
        return _error(exc)
    return _no_store(body)
