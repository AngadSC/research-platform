"""Integration services (ARCHITECTURE section 9): the generic OAuth2 connect flow, token refresh,
disconnect and revoke. Views (next phase) call these and serialize the result."""

import base64
import hashlib
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from audit import services as audit
from audit.models import AuditAction
from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, get_lab_or_404, labs_for, require
from integrations import crypto, http, registry
from integrations.http import AccountUnavailable, IntegrationError
from integrations.models import AccountStatus, ConnectedAccount
from labs.models import Lab

SESSION_KEY = "integrations.oauth"
STATE_TTL = 600  # seconds a started connect flow stays valid
MAX_PENDING = 5  # pending flows kept per session
_CODE_RE = re.compile(r"^[a-z_]{1,40}$")


class OAuthError(IntegrationError):
    """`code` is a fixed, safe identifier the API can return as-is."""

    def __init__(self, code):
        super().__init__(f"Connecting the account failed: {code}")
        self.code = code


class TokenError(IntegrationError):
    def __init__(self, code, status):
        super().__init__(f"The provider rejected the token request: {code} (HTTP {status})")
        self.code, self.status = code, status


def _oauth_provider(name) -> registry.Provider:
    provider = registry.PROVIDERS.get(name)
    if provider is None or provider.auth_type != registry.AuthType.OAUTH2:
        raise OAuthError("unknown_provider")
    if not provider.configured:
        raise OAuthError("provider_not_configured")
    return provider


def _expiry(tokens):
    seconds = tokens.get("expires_in")
    return timezone.now() + timedelta(seconds=int(seconds)) if seconds else None


@sensitive_variables("data", "body")
def _token_request(provider, data) -> dict:
    client_id, client_secret = provider.client()
    resp = http.send(
        "POST",
        provider.token_url,
        provider=provider,
        data={**data, "client_id": client_id, "client_secret": client_secret},
        headers={"Accept": "application/json"},
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200 or not isinstance(body, dict) or not body.get("access_token"):
        code = body.get("error") if isinstance(body, dict) else None
        raise TokenError(code if _CODE_RE.match(str(code)) else "unknown", resp.status_code)
    return body


# ---- connect


@sensitive_variables("verifier", "pending")
def start_connect(request, lab, provider_name, scopes=None) -> str:
    """Begin connecting `request.user`'s account in `lab`; returns the URL to send the browser to.
    The state is bound to this session, user, lab and provider, is single-use and lasts
    STATE_TTL. PKCE (S256) protects the code. Only registry scopes can be requested."""
    user = request.user
    require(user, Perm.MANAGE_INTEGRATIONS, lab)
    provider = _oauth_provider(provider_name)
    scopes = sorted(set(scopes or provider.scopes))
    if not set(scopes) <= set(provider.scopes):
        raise OAuthError("invalid_scope")

    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    now = time.time()
    pending = {
        k: v for k, v in request.session.get(SESSION_KEY, {}).items() if v["at"] > now - STATE_TTL
    }
    keep = sorted(pending, key=lambda k: pending[k]["at"])[-(MAX_PENDING - 1) :]
    pending = {k: pending[k] for k in keep}
    pending[state] = {
        "user": str(user.pk),
        "lab": str(lab.pk),
        "provider": provider.name,
        "scopes": scopes,
        "verifier": verifier,
        "at": now,
    }
    request.session[SESSION_KEY] = pending

    params = {
        "response_type": "code",
        "client_id": provider.client()[0],
        "redirect_uri": settings.INTEGRATION_OAUTH_REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge.decode().rstrip("="),
        "code_challenge_method": "S256",
        **provider.authorize_params,
    }
    current = (
        ConnectedAccount.objects.for_lab(lab)
        .filter(user=user, provider=provider.name, status=AccountStatus.ACTIVE)
        .first()
    )
    if current is not None and current.external_email:
        params["login_hint"] = current.external_email  # incremental auth: same account
    return f"{provider.authorize_url}?{urlencode(params)}"


@sensitive_variables("entry", "tokens", "access", "pending")
def complete_connect(request, *, state, code="", error="") -> ConnectedAccount:
    """The OAuth callback. Consumes the state (even on failure), re-checks the user and their
    permission, exchanges the code with the PKCE verifier and stores the account."""
    pending = request.session.get(SESSION_KEY, {})
    entry = pending.pop(state, None) if state else None
    request.session[SESSION_KEY] = pending
    user = request.user
    if (
        entry is None
        or entry["at"] < time.time() - STATE_TTL
        or not user.is_authenticated
        or str(user.pk) != entry["user"]
    ):
        raise OAuthError("invalid_state")
    lab = get_lab_or_404(user, entry["lab"])
    require(user, Perm.MANAGE_INTEGRATIONS, lab)
    if error:
        raise OAuthError("access_denied" if error == "access_denied" else "provider_error")
    if not code:
        raise OAuthError("invalid_request")
    provider = _oauth_provider(entry["provider"])

    tokens = _token_request(
        provider,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.INTEGRATION_OAUTH_REDIRECT_URI,
            "code_verifier": entry["verifier"],
        },
    )
    access = tokens["access_token"]
    granted = sorted(set(str(tokens.get("scope", "")).split()) or entry["scopes"])
    if not set(entry["scopes"]) <= set(granted):
        raise OAuthError("scope_not_granted")  # the user unticked a scope on the consent screen
    resp = http.send(
        "GET",
        provider.identity_url,
        provider=provider,
        headers={"Authorization": f"Bearer {access}"},
    )
    try:
        if resp.status_code != 200:
            raise ValueError
        external_id, email = provider.parse_identity(resp.json())
    except (ValueError, KeyError, TypeError):
        raise OAuthError("identity_failed") from None
    if not external_id:
        raise OAuthError("identity_failed")

    # A discarded token (any failure above or below) is never stored. It is not revoked at the
    # provider either: the same grant may back this person's account in another lab (D68).
    with transaction.atomic():
        rows = list(
            ConnectedAccount.objects.for_lab(lab)
            .select_for_update()
            .filter(user=user, provider=provider.name)
        )
        if any(
            r.status == AccountStatus.ACTIVE and r.external_account_id != external_id for r in rows
        ):
            raise OAuthError("other_account_connected")  # disconnect the current one first
        account = next((r for r in rows if r.external_account_id == external_id), None)
        if account is None:
            account = ConnectedAccount(
                lab=lab, user=user, provider=provider.name, external_account_id=external_id
            )
        account.external_email = email
        account.granted_scopes = granted
        account.status = AccountStatus.ACTIVE
        account.connected_at = account.last_used_at = timezone.now()
        account.set_tokens(
            access=access, refresh=tokens.get("refresh_token") or None, expires_at=_expiry(tokens)
        )
        account.save()
        audit.record(
            AuditAction.INTEGRATION_CONNECTED,
            actor=user,
            lab=lab,
            target=account,
            request=request,
            metadata={"provider": provider.name, "scopes": granted},
        )
    return account


# ---- refresh


def _notify_reconnect(account):
    label = getattr(registry.PROVIDERS.get(account.provider), "label", account.provider)
    notify(
        lab=account.lab,
        recipient=account.user,
        kind=NotificationKind.INTEGRATION_ISSUE,
        title=f"Your {label} connection needs reconnecting",
        body="The provider stopped accepting this connection. Reconnect it to keep linked items "
        "up to date.",
        target=account,
        dedupe_key=f"integration:{account.pk}:{account.connected_at.isoformat()}",
    )


@sensitive_variables("tokens")
def _refresh_locked(row) -> bool:
    """Refresh a locked, active row. Returns True when it failed for good (row marked, audited).
    A transient failure (network, 429, 5xx) raises and changes nothing."""
    provider = registry.PROVIDERS.get(row.provider)
    if provider is None or not provider.configured:
        status, reason = AccountStatus.ERROR, "provider_not_configured"
    elif not row.refresh_token_ct:
        status, reason = AccountStatus.EXPIRED, "no_refresh_token"
    else:
        try:
            tokens = _token_request(
                provider, {"grant_type": "refresh_token", "refresh_token": row.refresh_token()}
            )
        except TokenError as exc:
            if exc.status == 429 or exc.status >= 500:
                raise
            # invalid_grant: revoked at the provider, or aged out. Anything else: our config.
            status = AccountStatus.EXPIRED if exc.code == "invalid_grant" else AccountStatus.ERROR
            reason = exc.code
        else:
            row.set_tokens(
                access=tokens["access_token"],
                refresh=tokens.get("refresh_token") or None,  # some providers rotate it
                expires_at=_expiry(tokens),
            )
            if tokens.get("scope"):
                row.granted_scopes = sorted(set(str(tokens["scope"]).split()))
            row.save()
            return False
    row.status = status
    row.clear_tokens()
    row.save()
    audit.record(
        AuditAction.INTEGRATION_REFRESH_FAILED,
        actor=None,
        actor_label="integrations:refresh",
        lab=row.lab,
        target=row,
        metadata={"provider": row.provider, "reason": reason, "status": status},
    )
    return True


def refresh_access_token(account) -> None:
    """Refresh `account` in place, under a row lock so concurrent callers refresh once.
    Raises AccountUnavailable when the account is (or becomes) unusable, IntegrationError on a
    transient failure."""
    seen = account.access_token_ct
    with transaction.atomic():
        row = (
            ConnectedAccount.objects.for_lab(account.lab_id).select_for_update().get(pk=account.pk)
        )
        # someone else refreshed meanwhile when the stored token changed: just reload
        failed = (
            row.status == AccountStatus.ACTIVE
            and row.access_token_ct == seen
            and _refresh_locked(row)
        )
        if failed:
            _notify_reconnect(row)
    account.refresh_from_db()
    if account.status != AccountStatus.ACTIVE:
        raise AccountUnavailable(f"{account.provider} connection needs reconnecting")


# ---- disconnect / revoke


def _grant_used_elsewhere(row) -> bool:
    """D68: the same external account is active for this user in another lab. Revoking at the
    provider would revoke the whole grant and break that connection too."""
    for lab in labs_for(row.user):
        if lab.pk != row.lab_id and (
            ConnectedAccount.objects.for_lab(lab)
            .filter(
                user=row.user_id,
                provider=row.provider,
                external_account_id=row.external_account_id,
                status=AccountStatus.ACTIVE,
            )
            .exists()
        ):
            return True
    return False


@sensitive_variables("token")
def _revoke_at_provider(row) -> bool:
    provider = registry.PROVIDERS.get(row.provider)
    token = row.refresh_token() or row.access_token()
    if provider is None or not provider.revoke_url or not token or _grant_used_elsewhere(row):
        return False
    try:
        resp = http.send("POST", provider.revoke_url, provider=provider, data={"token": token})
    except IntegrationError:
        return False
    return resp.status_code == 200


def disconnect(account, *, actor, request=None, actor_label="") -> None:
    """Wipe the tokens, mark the account revoked and revoke the grant at the provider (best
    effort: a provider failure never keeps the tokens). The owner needs manage_integrations
    (audited `integration.disconnected`); anyone else needs manage_lab_integrations
    (`integration.revoked`). `actor=None` is a system revoke (lifecycle), with `actor_label`."""
    own = actor is not None and account.user_id == actor.pk
    if actor is not None:
        perm = Perm.MANAGE_INTEGRATIONS if own else Perm.MANAGE_LAB_INTEGRATIONS
        require(actor, perm, account)
    with transaction.atomic():
        row = (
            ConnectedAccount.objects.for_lab(account.lab_id).select_for_update().get(pk=account.pk)
        )
        if row.status == AccountStatus.REVOKED:
            return
        revoked_at_provider = _revoke_at_provider(row)
        row.status = AccountStatus.REVOKED
        row.clear_tokens()
        row.save()
        audit.record(
            AuditAction.INTEGRATION_DISCONNECTED if own else AuditAction.INTEGRATION_REVOKED,
            actor=actor,
            actor_label=actor_label,
            lab=row.lab,
            target=row,
            request=request,
            metadata={"provider": row.provider, "provider_revoked": revoked_at_provider},
        )
    account.refresh_from_db()


def revoke_member_accounts(lab, user, *, reason) -> int:
    """Lifecycle hook (member removed from `lab`, or deactivated): revoke every connected account
    `user` holds in `lab`. `reason` becomes the audit actor label. Returns the number revoked."""
    accounts = list(
        ConnectedAccount.objects.for_lab(lab)
        .filter(user=user)
        .exclude(status=AccountStatus.REVOKED)
    )
    for account in accounts:
        disconnect(account, actor=None, actor_label=f"lifecycle:{reason}")
    return len(accounts)


# ---- key rotation


def rotate_token_encryption() -> int:
    """Re-encrypt every stored token under the newest key (D63). Run after adding a key, before
    removing an old one. Returns the number of accounts rewritten."""
    count = 0
    for lab in Lab.objects.all():
        for row in ConnectedAccount.objects.for_lab(lab).exclude(
            access_token_ct="", refresh_token_ct=""
        ):
            row.access_token_ct = crypto.rotate(row.access_token_ct)
            row.refresh_token_ct = crypto.rotate(row.refresh_token_ct)
            row.save(update_fields=["access_token_ct", "refresh_token_ct"])
            count += 1
    return count
