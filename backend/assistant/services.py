"""AI access services (D160-D169): grants, hashed tokens, the OAuth 2.1 code flow and CIMD.

Tokens are random 256-bit strings; only their sha256 is stored (D162), so a database leak does not
yield a usable token. Plaintext exists only in the return value of the issuing function. Functions
that hold one are `sensitive_variables`, and nothing here logs or audits a token."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from assistant.models import Access, AIGrant, AIToken, ClientKind, GrantKind, OAuthClient, TokenKind
from audit.models import AuditAction
from audit.services import record
from core.permissions import lab_role, labs_for
from labs.models import AiPolicy, Lab

MCP_POLICIES = (AiPolicy.MCP, AiPolicy.FULL)  # D188: what the lab allows over MCP
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
CODE_TTL = timedelta(minutes=5)
PAT_MAX_DAYS = 365
CIMD_TTL = timedelta(hours=1)
PREFIX = {TokenKind.ACCESS: "rwa_", TokenKind.REFRESH: "rwr_", TokenKind.PAT: "rwp_"}
SCOPES = {Access.READ: "mcp:read", Access.WRITE: "mcp:read mcp:write"}


class OAuthError(Exception):
    """`code` is an RFC 6749 error code, safe to return."""

    def __init__(self, code, description="", status=400):
        super().__init__(description or code)
        self.code, self.description, self.status = code, description, status


def mcp_url() -> str:
    return settings.MCP_BASE_URL + "/mcp"


def prm_url() -> str:
    return settings.MCP_BASE_URL + "/.well-known/oauth-protected-resource/mcp"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@sensitive_variables("raw")
def _issue(grant, kind, ttl, data=None) -> str:
    raw = PREFIX.get(kind, "") + secrets.token_urlsafe(32)
    AIToken.objects.create(
        grant=grant,
        kind=kind,
        token_hash=_hash(raw),
        expires_at=timezone.now() + ttl,
        data=data or {},
    )
    return raw


def over_limit(key: str, limit: int, seconds: int = 60) -> bool:
    """Fixed-window counter in the shared cache. ponytail: fixed window allows a 2x burst at a
    window edge; switch to a sliding window if that ever matters."""
    bucket = f"rl:{key}:{int(time.time() // seconds)}"
    if cache.add(bucket, 1, seconds + 1):
        return limit < 1
    try:
        return cache.incr(bucket) > limit
    except ValueError:  # expired between add and incr
        cache.add(bucket, 1, seconds + 1)
        return False


# ---------------------------------------------------------------- grants


def _audit_grant(action, grant, *, actor, labs, request=None, metadata=None, label=""):
    """One event per lab, so each lab's audit log shows its own grants (lab is required)."""
    for lab in labs:
        record(
            action,
            actor=actor,
            lab=lab,
            target=grant,
            request=request,
            actor_label=label,
            metadata={
                "kind": grant.kind,
                "access": grant.access,
                "client": grant.client.name if grant.client_id else "",
                "grant_id": str(grant.pk),
                **(metadata or {}),
            },
        )


def _member_labs(user, lab_ids):
    """The user's own labs among `lab_ids`; anything else (unknown, someone else's) refuses."""
    wanted = {str(i) for i in lab_ids}
    labs = [lab for lab in labs_for(user) if str(lab.pk) in wanted]
    if not wanted or len(labs) != len(wanted):
        raise OAuthError("invalid_request", "Choose at least one of your labs.")
    return labs


@transaction.atomic
@sensitive_variables("raw")
def create_pat(user, *, name, lab_ids, access, days, request=None):
    """A personal access token (D164). Returns (grant, token); the token is shown once."""
    labs = _member_labs(user, lab_ids)
    grant = AIGrant.objects.create(
        user=user,
        kind=GrantKind.PAT,
        name=name,
        access=access,
        expires_at=timezone.now() + timedelta(days=days),
    )
    grant.labs.set(labs)
    raw = _issue(grant, TokenKind.PAT, timedelta(days=days))
    _audit_grant(AuditAction.AI_ACCESS_GRANTED, grant, actor=user, labs=labs, request=request)
    return grant, raw


@transaction.atomic
def revoke(grant, *, by, lab=None, request=None, label="", reason="") -> None:
    """The owner revokes the whole grant. A lab manager (`lab` given) removes only their lab;
    the grant ends when no lab is left. `by=None` is a system revoke (`label` names it)."""
    grant = AIGrant.objects.select_for_update().get(pk=grant.pk)
    if grant.revoked_at is not None:
        return
    labs = [lab] if lab is not None else list(grant.labs.all())
    if lab is not None:
        grant.labs.remove(lab)
    if lab is None or not grant.labs.exists():
        grant.revoked_at, grant.revoked_by, grant.revoked_reason = timezone.now(), by, reason
        grant.save(update_fields=["revoked_at", "revoked_by", "revoked_reason"])
        AIToken.objects.filter(grant=grant).delete()
    scope = "lab" if lab is not None else "all"
    _audit_grant(
        AuditAction.AI_ACCESS_REVOKED,
        grant,
        actor=by,
        labs=labs,
        request=request,
        label=label,
        metadata={"scope": scope},
    )


def revoke_all(user, *, reason, request=None) -> int:
    """D195: end every live grant of `user` after a security event (password change or reset,
    TOTP removed, account deactivated). Audited per lab with actor null and the label
    `assistant:<reason>`; the reason is kept on the grant so Settings can explain it."""
    count = 0
    for grant in list(active_grants(user)):
        revoke(grant, by=None, request=request, label=f"assistant:{reason}", reason=reason)
        count += 1
    from labs.admin_services import revoke_calendar_feeds  # avoids an import cycle

    revoke_calendar_feeds(user, reason=reason, request=request)  # D231
    return count


def ended_by_security(user):
    """Grants the system ended in the last 30 days, for the Settings notice (D195)."""
    return (
        AIGrant.objects.filter(user=user, revoked_at__gte=timezone.now() - timedelta(days=30))
        .exclude(revoked_reason="")
        .select_related("client")
        .prefetch_related("labs")
        .order_by("-revoked_at")
    )


def active_grants(user):
    now = timezone.now()
    return (
        AIGrant.objects.filter(user=user, revoked_at__isnull=True)
        .exclude(expires_at__lte=now)
        .select_related("client")
        .prefetch_related("labs")
        .order_by("-created_at")
    )


def lab_grants(lab):
    now = timezone.now()
    return (
        AIGrant.objects.filter(labs=lab, revoked_at__isnull=True)
        .exclude(expires_at__lte=now)
        .select_related("client", "user")
        .prefetch_related("labs")
        .order_by("-created_at")
    )


# ---------------------------------------------------------------- bearer authentication


@sensitive_variables("raw")
def authenticate(raw: str):
    """(grant, token) for a live access token or PAT, re-checked on every call (D163): the token
    is unexpired, the grant unrevoked and unexpired, the user active, and an access token is for
    this server (RFC 8707 audience). None otherwise."""
    if not raw or len(raw) > 200:
        return None
    token = (
        AIToken.objects.select_related("grant__user", "grant__client")
        .filter(token_hash=_hash(raw), kind__in=(TokenKind.ACCESS, TokenKind.PAT))
        .first()
    )
    if token is None or token.expires_at <= timezone.now():
        return None
    grant = token.grant
    if not grant.active or not grant.user.is_active:
        return None
    if token.kind == TokenKind.ACCESS and token.data.get("resource") != mcp_url():
        return None
    if grant.last_used_at is None or grant.last_used_at < timezone.now() - timedelta(minutes=1):
        grant.last_used_at = timezone.now()
        AIGrant.objects.filter(pk=grant.pk).update(last_used_at=grant.last_used_at)
    return grant, token


def _member_lab_ids(grant) -> list[str]:
    return [
        str(lab_id)
        for lab_id in grant.labs.values_list("id", flat=True)
        if lab_role(grant.user, lab_id) is not None
    ]


def granted_lab_ids(grant) -> frozenset[str]:
    """Labs the grant names where the user is still a member right now (D163) and whose AI
    policy still allows MCP (D188: `mcp` or `full`; `off` hides the lab from every tool)."""
    member = _member_lab_ids(grant)
    allowed = Lab.objects.filter(pk__in=member, ai_policy__in=MCP_POLICIES).values_list(
        "pk", flat=True
    )
    return frozenset(str(pk) for pk in allowed)


def policy_blocked(grant) -> bool:
    """True when the user is still in at least one granted lab but every one of them has turned
    AI assistants off: the MCP endpoint answers 403 then, not an empty lab list (D188)."""
    return bool(_member_lab_ids(grant)) and not granted_lab_ids(grant)


# ---------------------------------------------------------------- OAuth clients (D165)

LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _listed(uri: str) -> bool:
    """D193: an exact entry of MCP_ALLOWED_REDIRECT_URIS. `*` in an entry matches one id-like
    path segment and nothing else (no query, no fragment, no slash)."""
    for entry in settings.MCP_ALLOWED_REDIRECT_URIS:
        if "*" not in entry:
            if uri == entry:
                return True
        elif re.fullmatch(re.escape(entry).replace(r"\*", "[A-Za-z0-9_-]{1,100}"), uri):
            return True
    return False


def redirect_allowed(uri: str) -> bool:
    """Deployment policy (D193): an exact allowlisted https URI, or http loopback (any port)."""
    try:
        parts = urlsplit(uri)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018  (raises on a malformed port)
    except ValueError:
        return False
    if parts.fragment or parts.username or parts.password or not host:
        return False
    if parts.scheme == "http":
        return host in LOOPBACK
    return parts.scheme == "https" and _listed(uri)


def redirect_matches(uri: str, registered) -> bool:
    """Exact match, except loopback ports are ignored (RFC 8252 section 7.3; Claude Code)."""
    if uri in registered:
        return True
    try:
        parts = urlsplit(uri)
        if parts.scheme != "http" or (parts.hostname or "") not in LOOPBACK:
            return False
        for r in registered:
            rp = urlsplit(r)
            if (rp.scheme, rp.hostname, rp.path, rp.query) == (
                "http",
                parts.hostname,
                parts.path,
                parts.query,
            ):
                return True
    except ValueError:
        return False
    return False


def _clean_uris(uris) -> list[str]:
    if not isinstance(uris, list) or not uris or len(uris) > 10:
        raise OAuthError("invalid_redirect_uri", "Give between 1 and 10 redirect URIs.")
    for uri in uris:
        if not isinstance(uri, str) or len(uri) > 500 or not redirect_allowed(uri):
            raise OAuthError("invalid_redirect_uri", "That redirect URI is not allowed here.")
    return uris


def register_client(meta: dict) -> OAuthClient:
    """RFC 7591 registration. Public clients only: we never issue a client secret."""
    uris = _clean_uris(meta.get("redirect_uris"))
    name = meta.get("client_name") or "Unnamed app"
    if not isinstance(name, str):
        raise OAuthError("invalid_client_metadata", "client_name must be text.")
    for field, allowed in (
        ("grant_types", {"authorization_code", "refresh_token"}),
        ("response_types", {"code"}),
    ):
        value = meta.get(field, [])
        if not isinstance(value, list) or not set(value) <= allowed:
            raise OAuthError("invalid_client_metadata", f"Unsupported {field}.")
    return OAuthClient.objects.create(
        client_id=secrets.token_urlsafe(24),
        kind=ClientKind.DCR,
        name=name.strip()[:100] or "Unnamed app",
        redirect_uris=uris,
    )


def _is_cimd(client_id: str) -> bool:
    parts = urlsplit(client_id)
    return parts.scheme == "https" and parts.path not in ("", "/")


def _fetch_cimd(client_id: str) -> dict:
    """GET the metadata document through the SSRF-pinned client (D67, D82): https, port 443,
    only MCP_CIMD_HOSTS, public addresses, size and time capped, no redirects to other hosts."""
    from integrations import http

    provider = SimpleNamespace(label="Client metadata", api_hosts=set(settings.MCP_CIMD_HOSTS))
    try:
        with http.budget(8):
            resp = http.send("GET", client_id, provider=provider)
        doc = json.loads(resp.content)
    except (http.IntegrationError, ValueError):
        raise OAuthError("invalid_client", "The app's client metadata could not be read.") from None
    if resp.status_code != 200 or not isinstance(doc, dict) or doc.get("client_id") != client_id:
        raise OAuthError("invalid_client", "The app's client metadata is not valid.")
    # ChatGPT's singular field prefers private_key_jwt, but its list also offers "none", and it
    # picks from what we advertise (only "none"). A client has to be able to work without a secret.
    methods = doc.get("token_endpoint_auth_methods_supported") or [
        doc.get("token_endpoint_auth_method", "none")
    ]
    if not isinstance(methods, list) or "none" not in methods:
        raise OAuthError("invalid_client", "Only public clients (PKCE, no secret) are supported.")
    return doc


def resolve_client(client_id) -> OAuthClient:
    """A registered client, or a CIMD client on an allowed host (fetched, cached an hour)."""
    if not isinstance(client_id, str) or not client_id or len(client_id) > 255:
        raise OAuthError("invalid_client", "Unknown app.")
    client = OAuthClient.objects.filter(client_id=client_id).first()
    if not _is_cimd(client_id):
        if client is None or client.kind != ClientKind.DCR:
            raise OAuthError("invalid_client", "Unknown app.")
        return client
    if (urlsplit(client_id).hostname or "").lower() not in settings.MCP_CIMD_HOSTS:
        raise OAuthError("invalid_client", "Apps from that host are not allowed here.")
    if client is not None and client.refreshed_at > timezone.now() - CIMD_TTL:
        return client
    doc = _fetch_cimd(client_id)
    uris = _clean_uris(doc.get("redirect_uris"))
    name = str(doc.get("client_name") or urlsplit(client_id).hostname)[:100]
    client, _ = OAuthClient.objects.update_or_create(
        client_id=client_id,
        defaults={
            "kind": ClientKind.CIMD,
            "name": name,
            "redirect_uris": uris,
            "refreshed_at": timezone.now(),
        },
    )
    return client


# ---------------------------------------------------------------- authorization code flow


def canonical(uri: str) -> str:
    """RFC 8707 resource comparison: lower-case scheme and host, no trailing slash."""
    parts = urlsplit(uri or "")
    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}"


@transaction.atomic
@sensitive_variables("code")
def approve(user, client, *, lab_ids, access, redirect_uri, challenge, request=None) -> str:
    """The user consented (D161): replace their earlier grant for this client, record the new
    one, and return a single-use authorization code."""
    labs = _member_labs(user, lab_ids)
    for old in AIGrant.objects.filter(user=user, client=client, revoked_at__isnull=True):
        revoke(old, by=user, request=request)
    grant = AIGrant.objects.create(
        user=user, kind=GrantKind.OAUTH, client=client, name=client.name, access=access
    )
    grant.labs.set(labs)
    code = _issue(
        grant,
        TokenKind.CODE,
        CODE_TTL,
        {"challenge": challenge, "redirect_uri": redirect_uri, "resource": mcp_url()},
    )
    _audit_grant(AuditAction.AI_ACCESS_GRANTED, grant, actor=user, labs=labs, request=request)
    return code


@sensitive_variables("access", "refresh")
def _token_pair(grant) -> dict:
    access = _issue(grant, TokenKind.ACCESS, ACCESS_TTL, {"resource": mcp_url()})
    refresh = _issue(grant, TokenKind.REFRESH, REFRESH_TTL)
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TTL.total_seconds()),
        "refresh_token": refresh,
        "scope": SCOPES[grant.access],
    }


class _Replay(Exception):
    def __init__(self, grant):
        self.grant = grant


@sensitive_variables("raw")
def _spend(raw, kind, client_id):
    """Look up a code or refresh token, check its client, and mark it used (committed before
    anything else is checked, so a failed exchange still burns it). A used one coming back means
    someone holds a copy: the whole grant ends (OAuth 2.1 section 4.3.1, rotation)."""
    try:
        with transaction.atomic():
            token = (
                AIToken.objects.select_for_update(of=("self",))
                .select_related("grant__client", "grant__user")
                .filter(token_hash=_hash(raw or ""), kind=kind)
                .first()
            )
            if token is None:
                raise OAuthError("invalid_grant", "The code or token is not valid.")
            grant = token.grant
            if grant.client is None or grant.client.client_id != client_id:
                raise OAuthError("invalid_grant", "The code or token was issued to another app.")
            if token.used_at is not None:
                raise _Replay(grant)
            if token.expires_at <= timezone.now() or not grant.active or not grant.user.is_active:
                raise OAuthError("invalid_grant", "The code or token has expired.")
            token.used_at = timezone.now()
            token.save(update_fields=["used_at"])
    except _Replay as replay:
        revoke(replay.grant, by=None, label="assistant:token_replay")
        raise OAuthError("invalid_grant", "The code or token was already used.") from None
    return token, grant


@sensitive_variables("code", "verifier")
def exchange_code(*, code, client_id, redirect_uri, verifier, resource) -> dict:
    token, grant = _spend(code, TokenKind.CODE, client_id)
    if redirect_uri != token.data.get("redirect_uri"):
        raise OAuthError("invalid_grant", "redirect_uri does not match the authorization.")
    if resource and canonical(resource) != canonical(mcp_url()):
        raise OAuthError("invalid_target", "Unknown resource.")
    digest = hashlib.sha256((verifier or "").encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    if not verifier or not hmac.compare_digest(expected, token.data.get("challenge", "")):
        raise OAuthError("invalid_grant", "PKCE verification failed.")
    return _token_pair(grant)


@sensitive_variables("refresh_token")
def refresh(*, refresh_token, client_id, resource) -> dict:
    _, grant = _spend(refresh_token, TokenKind.REFRESH, client_id)
    if resource and canonical(resource) != canonical(mcp_url()):
        raise OAuthError("invalid_target", "Unknown resource.")
    return _token_pair(grant)
