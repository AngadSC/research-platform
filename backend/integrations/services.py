"""Integration services (ARCHITECTURE section 9): connecting accounts (OAuth2, API key), token
refresh, disconnect and revoke, external links, item search and freshness. Views call these and
serialize the result."""

import base64
import hashlib
import logging
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from audit import services as audit
from audit.models import AuditAction
from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, can, get_lab_or_404, require
from integrations import crypto, http, registry
from integrations.http import AccountUnavailable, InstanceURLError, IntegrationError
from integrations.models import TARGET_FIELDS, AccountStatus, ConnectedAccount, ExternalLink
from labs.models import Lab
from provenance.models import validate_web_url

AuthType = registry.AuthType

log = logging.getLogger("integrations.services")
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
    if provider.token_auth == "basic":  # Zoom: the app's credentials as HTTP Basic auth
        pair = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        creds, headers = {}, {"Accept": "application/json", "Authorization": f"Basic {pair}"}
    else:
        creds = {"client_id": client_id, "client_secret": client_secret}
        headers = {"Accept": "application/json"}
    resp = http.send(
        "POST",
        provider.token_url,
        provider=provider,
        data={**data, **creds},
        headers=headers,
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


@http.interactive
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
    if not set(granted) <= set(provider.scopes):
        raise OAuthError("unexpected_scope")  # D78: a merged grant; discarded, not stored
    resp = http.send(
        provider.identity_method,
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
    return _store_account(
        request,
        lab,
        provider,
        external_id=external_id,
        email=email,
        scopes=granted,
        access=access,
        refresh=tokens.get("refresh_token") or None,
        expires_at=_expiry(tokens),
    )


@sensitive_variables("access", "refresh")
def _store_account(
    request, lab, provider, *, external_id, email, scopes, access, refresh, expires_at, instance=""
) -> ConnectedAccount:
    """Save a verified connection. Under a row lock: another active external account of this
    provider refuses (`other_account_connected`: disconnect first, D69); the same external
    account reuses its row, so its links keep pointing at it."""
    user = request.user
    with transaction.atomic():
        rows = list(
            ConnectedAccount.objects.for_lab(lab)
            .select_for_update()
            .filter(user=user, provider=provider.name)
        )
        if any(
            r.status == AccountStatus.ACTIVE and r.external_account_id != external_id for r in rows
        ):
            raise OAuthError("other_account_connected")
        account = next((r for r in rows if r.external_account_id == external_id), None)
        if account is None:
            account = ConnectedAccount(
                lab=lab, user=user, provider=provider.name, external_account_id=external_id
            )
        account.external_email = (email or "")[:254]
        account.granted_scopes = scopes
        account.instance_url = instance
        account.status = AccountStatus.ACTIVE
        account.connected_at = account.last_used_at = timezone.now()
        account.set_tokens(access=access, refresh=refresh, expires_at=expires_at)
        account.save()
        audit.record(
            AuditAction.INTEGRATION_CONNECTED,
            actor=user,
            lab=lab,
            target=account,
            request=request,
            metadata={
                "provider": provider.name,
                "scopes": scopes,
                **({"instance_host": account.instance_host} if instance else {}),
            },
        )
    return account


@http.interactive
@sensitive_variables()
def connect_with_key(request, lab, provider_name, *, api_key, secret="", instance_url=""):
    """API-key connect (D81): validate the key with one cheap provider call before anything is
    stored, then store it encrypted like an OAuth token (the key in the access-token column, the
    optional secret in the refresh-token column). Self-hosted providers check the instance URL
    first (D82). Raises OAuthError with a safe code; nothing is stored on failure."""
    user = request.user
    require(user, Perm.MANAGE_INTEGRATIONS, lab)
    provider = registry.PROVIDERS.get(provider_name)
    if provider is None or provider.auth_type != AuthType.API_KEY or not provider.configured:
        raise OAuthError("unknown_provider")
    given = {"api_key": api_key, "secret": secret, "instance_url": instance_url}
    if not api_key or any(f.required and not given[f.name] for f in provider.connect_fields):
        raise OAuthError("invalid_request")
    instance = ""
    if provider.needs_instance_url:
        try:
            instance = http.validate_instance_url(instance_url, provider)
        except InstanceURLError as exc:
            raise OAuthError(exc.code) from None
    probe = ConnectedAccount(
        lab=lab,
        user=user,
        provider=provider.name,
        instance_url=instance,
        status=AccountStatus.ACTIVE,
        connected_at=timezone.now(),
    )
    probe.set_tokens(access=api_key, refresh=secret or "", expires_at=None)
    try:
        external_id, email = provider.identify_account(probe)
    except AccountUnavailable:
        raise OAuthError("invalid_key") from None  # the provider answered 401
    except IntegrationError:
        raise OAuthError("provider_error") from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise OAuthError("identity_failed") from None
    external_id = str(external_id or "")
    if not external_id:
        raise OAuthError("identity_failed")
    if instance:  # the same user id on two servers is two accounts (D68 compares these)
        external_id = f"{probe.instance_host}:{external_id}"
    return _store_account(
        request,
        lab,
        provider,
        external_id=external_id[:255],
        email=str(email or ""),
        scopes=[],
        access=api_key,
        refresh=secret or "",
        expires_at=None,
        instance=instance,
    )


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
    if provider is None or not provider.configured or provider.auth_type != AuthType.OAUTH2:
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
            granted = sorted(set(str(tokens.get("scope", "")).split()))
            if set(granted) <= set(provider.scopes):
                row.set_tokens(
                    access=tokens["access_token"],
                    refresh=tokens.get("refresh_token") or None,  # some providers rotate it
                    expires_at=_expiry(tokens),
                )
                if granted:
                    row.granted_scopes = granted
                row.save()
                return False
            status, reason = AccountStatus.ERROR, "unexpected_scope"  # D78: wipe and reconnect
    _mark_failed(row, status, reason)
    return True


def _mark_failed(row, status, reason) -> None:
    """A locked row the provider stopped accepting: wipe its credentials, set `status` and
    audit `integration.refresh_failed` (actor null)."""
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


def key_rejected(account) -> None:
    """The provider answered 401 to an API key (D81): revoked or expired there. Marked
    `expired`, wiped, audited and the owner notified, like a refused refresh. An unsaved
    account (a key being validated on connect) is left alone."""
    if account._state.adding:
        return
    with transaction.atomic():
        row = (
            ConnectedAccount.objects.for_lab(account.lab_id).select_for_update().get(pk=account.pk)
        )
        if row.status == AccountStatus.ACTIVE:
            _mark_failed(row, AccountStatus.EXPIRED, "key_rejected")
            _notify_reconnect(row)
    account.refresh_from_db()


# ---- disconnect / revoke


def _grant_used_elsewhere(row) -> bool:
    """D68: another active row (any user, any lab) holds the same external account. Revoking at
    the provider would revoke the whole grant and break that connection too."""
    return any(
        ConnectedAccount.objects.for_lab(lab)
        .filter(
            provider=row.provider,
            external_account_id=row.external_account_id,
            status=AccountStatus.ACTIVE,
        )
        .exclude(pk=row.pk)
        .exists()
        for lab in Lab.objects.all()
    )


@sensitive_variables("token")
def _stored_token(row) -> str:
    """The token to revoke at the provider; "" when there is none or it can't be decrypted. A
    decrypt failure must never stop the local revoke."""
    try:
        return row.refresh_token() or row.access_token()
    except Exception:  # noqa: BLE001 - the local wipe goes ahead whatever this raises
        return ""


@http.interactive
@sensitive_variables("token")
def _revoke_at_provider(row, token) -> bool:
    """Best effort: any failure means "not revoked" and never propagates."""
    provider = registry.PROVIDERS.get(row.provider)
    try:
        if (
            provider is None
            or provider.auth_type != AuthType.OAUTH2  # an API key is deleted at the provider
            or not provider.revoke_url
            or not token
            or _grant_used_elsewhere(row)
        ):
            return False
        if provider.revoke is not None:
            return bool(provider.revoke(token))
        resp = http.send("POST", provider.revoke_url, provider=provider, data={"token": token})
        return resp.status_code == 200
    except Exception as exc:  # noqa: BLE001 - messages may echo the token; log the type only
        log.warning("integration provider revoke failed: %s", type(exc).__name__)
        return False


def disconnect(account, *, actor, request=None) -> None:
    """Wipe the tokens, mark the account revoked and revoke the grant at the provider (best
    effort: a provider failure never keeps the tokens). The owner needs manage_integrations
    (audited `integration.disconnected`); anyone else needs manage_lab_integrations
    (`integration.revoked`). System revokes go through `revoke_member_accounts`."""
    own = account.user_id == actor.pk
    require(actor, Perm.MANAGE_INTEGRATIONS if own else Perm.MANAGE_LAB_INTEGRATIONS, account)
    with transaction.atomic():
        row = (
            ConnectedAccount.objects.for_lab(account.lab_id).select_for_update().get(pk=account.pk)
        )
        if row.status == AccountStatus.REVOKED:
            return
        token = _stored_token(row)
        row.status = AccountStatus.REVOKED
        row.clear_tokens()
        row.save()
        revoked_at_provider = _revoke_at_provider(row, token)
        audit.record(
            AuditAction.INTEGRATION_DISCONNECTED if own else AuditAction.INTEGRATION_REVOKED,
            actor=actor,
            lab=row.lab,
            target=row,
            request=request,
            metadata={"provider": row.provider, "provider_revoked": revoked_at_provider},
        )
    account.refresh_from_db()


def revoke_member_accounts(lab, user, *, reason) -> int:
    """Lifecycle hook (member removed from `lab`, or deactivated; `user` may be a pk): revoke
    every connected account they hold in `lab`. Call it inside the transaction that changes the
    membership, so the local revoke (status, tokens, audit with actor null and label
    `lifecycle:<reason>`) commits with it. The provider calls run after the commit, best
    effort, and can't undo the revoke. Returns the number revoked."""
    pending = []
    with transaction.atomic():
        rows = (
            ConnectedAccount.objects.for_lab(lab)
            .select_for_update()
            .filter(user=user)
            .exclude(status=AccountStatus.REVOKED)
        )
        for row in rows:
            pending.append((row, _stored_token(row)))
            row.status = AccountStatus.REVOKED
            row.clear_tokens()
            row.save()
            audit.record(
                AuditAction.INTEGRATION_REVOKED,
                actor=None,
                actor_label=f"lifecycle:{reason}",
                lab=row.lab,
                target=row,
                metadata={"provider": row.provider, "provider_revoked": False},
            )
        if pending:
            transaction.on_commit(lambda: [_revoke_at_provider(r, t) for r, t in pending])
    return len(pending)


def revoke_orphaned_accounts() -> int:
    """Daily safety net for the lifecycle hooks: revoke every account whose owner is no longer
    an active member of its lab. Returns the number revoked."""
    from labs.models import LabMembership

    count = 0
    for lab in Lab.objects.all():
        active = LabMembership.objects.for_lab(lab).filter(user__is_active=True)
        owners = (
            ConnectedAccount.objects.for_lab(lab)
            .exclude(status=AccountStatus.REVOKED)
            .exclude(user__in=active.values("user"))
            .values_list("user", flat=True)
            .distinct()
        )
        for owner in list(owners):
            count += revoke_member_accounts(lab, owner, reason="orphan_sweep")
    return count


# ---- external links


def _target(project, field, pk):
    """The optional item a link hangs off, from the same project (D20, D31)."""
    model = ExternalLink._meta.get_field(field).related_model
    qs = model.objects.for_lab(project.lab_id).filter(project=project, pk=pk)
    if field == "document":
        qs = qs.filter(deleted_at__isnull=True)
    obj = qs.first()
    if obj is None:
        raise ValidationError({field: "This item does not exist in this project."})
    return obj


def _own_account(project, user, provider):
    """The requester's own active account at `provider` in this lab, or a readable 400."""
    account = (
        ConnectedAccount.objects.for_lab(project.lab_id)
        .filter(user=user, provider=provider.name, status=AccountStatus.ACTIVE)
        .first()
    )
    if account is None:
        raise ValidationError({"provider": f"Connect your {provider.label} account first."})
    return account


@http.interactive
@transaction.atomic
def create_link(*, project, user, data, request=None) -> ExternalLink:
    """Link an outside item to `project` (the caller already holds edit_content).

    The item is named by `external_id`, or by a pasted `url` the provider parses (D83). Its
    metadata always comes from the provider, read server-side with the linker's own active
    account (none for public providers), never from the client (D85). A link_only provider has
    no API: the pasted URL (checked against the provider's pattern and hosts) and the person's
    own title are stored."""
    provider = registry.PROVIDERS.get(data["provider"])
    if provider is None:
        raise ValidationError({"provider": "This service is not available."})
    account = _own_account(project, user, provider) if provider.needs_account else None
    instance_host = account.instance_host if account else ""
    url = data.get("url") or ""
    external_id = data.get("external_id") or ""
    if url and (provider.auth_type == AuthType.LINK_ONLY or not external_id):
        external_id = provider.parse_url(url, instance_host) or ""
        if not external_id:
            raise ValidationError({"url": f"This is not a {provider.label} address we can link."})
    if not provider.valid_external_id(external_id):
        raise ValidationError({"external_id": "This is not a valid item id."})
    targets = {f: _target(project, f, data[f]) for f in TARGET_FIELDS if data.get(f) is not None}
    kind, target = next(iter(targets.items()), ("project", None))
    if kind not in provider.link_targets:
        raise ValidationError({kind: f"{provider.label} items can't be linked here."})

    if provider.auth_type == AuthType.LINK_ONLY:
        if not (url and data.get("title")):
            raise ValidationError({"url": "Give the link's address and title."})
        meta = {"url": url.strip(), "title": data["title"]}
    else:
        if provider.fetch_item is None:
            raise ValidationError({"provider": f"Linking {provider.label} items is not ready yet."})
        try:
            meta = provider.fetch_item(account, external_id)
        except AccountUnavailable:
            raise ValidationError(
                {"provider": f"Reconnect your {provider.label} account first."}
            ) from None
        except IntegrationError:
            raise ValidationError(
                {"external_id": f"{provider.label} could not be reached. Try again shortly."}
            ) from None
        if meta is None:
            raise ValidationError(
                {"external_id": f"Not found in {provider.label}, or you can't open it."}
            )
    if not provider.link_url_ok(meta["url"], instance_host):
        raise ValidationError({"url": f"{provider.label} gave an unexpected link address."})
    try:
        validate_web_url(meta["url"])
    except DjangoValidationError:
        raise ValidationError({"url": "Enter a web address starting with http or https."}) from None
    fetched = provider.auth_type != AuthType.LINK_ONLY
    link = ExternalLink.objects.create(
        lab=project.lab,
        project=project,
        provider=provider.name,
        connected_account=account,
        external_id=external_id,
        url=meta["url"],
        title=(meta["title"] or external_id)[:500],
        mime_type=(meta.get("mime_type") or "")[:255],
        linked_by=user,
        linked_modified_at=meta.get("modified_at"),
        linked_version=(meta.get("version") or "")[:100],
        linked_checksum=(meta.get("checksum") or "")[:140],
        remote_modified_at=meta.get("modified_at"),
        remote_version=(meta.get("version") or "")[:100],
        remote_checksum=(meta.get("checksum") or "")[:140],
        last_checked_at=timezone.now() if fetched else None,
        **targets,
    )
    link.version_note = _apply_to_target(provider, link, kind, target, meta, user, request)
    audit.record(
        AuditAction.EXTERNAL_LINK_CREATED,
        actor=user,
        lab=project.lab,
        target=link,
        request=request,
        metadata={
            "provider": provider.name,
            "external_id": link.external_id,
            **({"version_copy": link.version_note} if link.version_note else {}),
        },
    )
    return link


APPLY_KINDS = ("dataset", "analysis", "result", "manuscript", "decision")
# D115: list fields a provider may append one entry to (never fill-if-empty): (kind, field).
APPEND_FIELDS = {("decision", "references")}
# D121: fields that only make sense together. A commit belongs to one repository, so both are
# written in one step and only while both are empty, never filled one by one from two links.
PAIRED_FIELDS = {"analysis": ("code_repo_url", "code_commit")}


def _append_reference(target, name, entry):
    """Append one `{title, url, doi}` entry to the record's list, if it passes the D95 rules and
    is not there yet (same DOI, else same URL, else same title) and the list has room. Returns
    "copied", "same", "kept" (full) or None (the entry is refused)."""
    from provenance.serializers import MAX_REFERENCES, ReferenceSerializer  # late: heavy import

    ser = ReferenceSerializer(data=entry)
    current = getattr(target, name)
    if not (isinstance(entry, dict) and ser.is_valid() and isinstance(current, list)):
        return None
    new = {k: ser.validated_data.get(k, "") for k in ("doi", "url", "title")}
    key = next(k for k in ("doi", "url", "title") if new[k])
    if any(
        isinstance(o, dict) and str(o.get(key, "")).casefold() == new[key].casefold()
        for o in current
    ):
        return "same"
    if len(current) >= MAX_REFERENCES:
        return "kept"
    setattr(target, name, [*current, {"title": new["title"], "url": new["url"], "doi": new["doi"]}])
    return "copied"


def _pair_values(provider, link, target, pair, proposed):
    """D121: `(outcome, proposed)`. A non-empty outcome ends the apply ("kept" or "same": the
    record already has a code reference). Otherwise `proposed` holds the pair only if every
    value is acceptable (the repository address on the provider's pinned hosts, and each value
    valid for its field), else the pair is dropped whole."""
    if any(getattr(target, name) for name in pair):
        same = all(getattr(target, n) == proposed.get(n, "") for n in pair if proposed.get(n))
        return ("same" if same else "kept"), proposed
    rest = {k: v for k, v in proposed.items() if k not in pair}
    values = {n: proposed.get(n) or "" for n in pair}
    account = link.connected_account
    host = account.instance_host if account else ""
    try:
        for name, value in values.items():
            if value:
                target._meta.get_field(name).clean(value, target)
    except DjangoValidationError:
        return "", rest
    if values.get(pair[0]) and not provider.link_url_ok(values[pair[0]], host):
        return "", rest  # a server-supplied address off its own host is never stored
    return "", {**rest, **values}


def _apply_to_target(provider, link, kind, target, meta, user, request) -> str:
    """D76, D86: the provider proposes values for the linked record (`apply_to_target`). Each
    is written only while that field is empty and only if the field's validators accept it.
    Returns "copied" (something was written), "kept" (the record already holds a different
    value: left alone, a new version is a new row, D20), "same", "none" (nothing to offer) or
    "" (the provider proposes nothing for this kind of target)."""
    if target is None or kind not in APPLY_KINDS or provider.apply_to_target is None:
        return ""
    proposed = provider.apply_to_target(kind, meta) or {}
    if not proposed:
        return ""
    if any((kind, name) in APPEND_FIELDS for name in proposed):
        # D122: lock the row and re-read it, so two people appending at once keep both entries
        # instead of the later save overwriting the earlier one with a stale list.
        list(type(target).objects.for_lab(link.lab_id).select_for_update().filter(pk=target.pk))
        target.refresh_from_db()
    copied, seen = [], set()
    pair = PAIRED_FIELDS.get(kind, ())
    if any(name in proposed for name in pair):
        outcome, proposed = _pair_values(provider, link, target, pair, proposed)
        if outcome:
            return outcome
    for name, value in proposed.items():
        if not value:
            continue
        if (kind, name) in APPEND_FIELDS:
            outcome = _append_reference(target, name, value)
            if outcome == "copied":
                copied.append(name)
            elif outcome:
                seen.add(outcome)
            continue
        try:
            value = target._meta.get_field(name).clean(value, target)
        except DjangoValidationError:
            continue  # never store a value the record itself would refuse
        current = getattr(target, name)
        if current == value:
            seen.add("same")
        elif current:
            seen.add("kept")
        else:
            setattr(target, name, value)
            copied.append(name)
    if not copied:
        return "kept" if "kept" in seen else "same" if seen else "none"
    target.save(update_fields=[*copied, "updated_at"])
    audit.record(
        AuditAction(f"{kind}.updated"),
        actor=user,
        lab=link.lab,
        target=target,
        request=request,
        metadata={"source": "external_link", "fields": copied},
    )
    return "copied"


# ---- item search (D85)

SEARCH_LIMIT = 20


def _search_result(provider, item, instance_host) -> dict | None:
    """One candidate, checked like everything else from outside: a valid id, plain text, a
    link only when it is on the provider's hosts. Anything malformed is dropped."""
    try:
        external_id, title = item["id"], item["title"]
        modified = item.get("modified")
        url = item.get("url") or ""
    except (KeyError, TypeError, AttributeError):
        return None
    if not provider.valid_external_id(external_id) or not isinstance(title, str):
        return None
    try:
        validate_web_url(url)
        url = url if provider.link_url_ok(url, instance_host) else ""
    except DjangoValidationError:
        url = ""
    return {
        "id": external_id,
        "title": title[:500],
        "subtitle": str(item.get("subtitle") or "")[:300],
        "modified": modified if hasattr(modified, "isoformat") else None,
        "url": url,
    }


@http.interactive
def search_items(*, project, user, provider_name, query, target, request=None) -> list[dict]:
    """Candidates to link, from the provider, read with the requester's own account (none for a
    public provider). Nothing is stored or cached; linking one re-fetches it (create_link).
    Audited as `integration.searched` (provider, target and count; never the query)."""
    provider = registry.PROVIDERS.get(provider_name)
    if provider is None or provider.search_items is None:
        raise ValidationError({"provider": "This service can't be searched."})
    if target not in provider.link_targets:
        raise ValidationError({"target": f"{provider.label} items can't be linked here."})
    account = _own_account(project, user, provider) if provider.needs_account else None
    try:
        found = provider.search_items(account, query, target) or []
    except AccountUnavailable:
        raise ValidationError(
            {"provider": f"Reconnect your {provider.label} account first."}
        ) from None
    host = account.instance_host if account else ""
    results = [_search_result(provider, item, host) for item in list(found)[:SEARCH_LIMIT]]
    results = [r for r in results if r]
    audit.record(
        AuditAction.INTEGRATION_SEARCHED,
        actor=user,
        lab=project.lab,
        target=project,
        request=request,
        metadata={"provider": provider.name, "target": target, "results": len(results)},
    )
    return results


@transaction.atomic
def remove_link(link, *, user, request=None) -> None:
    audit.record(
        AuditAction.EXTERNAL_LINK_REMOVED,
        actor=user,
        lab=link.lab,
        target=link,
        request=request,
        metadata={"provider": link.provider, "external_id": link.external_id},
    )
    link.delete()


# ---- freshness


def check_blocked(link) -> str:
    """Why `link` can't be checked: "" when it can. Freshness uses the linker's token, so it
    needs their account active and their access to the project to still hold (D78)."""
    if link.connected_account_id and link.connected_account.status != AccountStatus.ACTIVE:
        return "linker_inactive"
    if link.connected_account_id and not can(link.linked_by, Perm.VIEW_PROJECT, link.project):
        return "linker_access_lost"
    return ""


def check_link(link) -> ExternalLink:
    """Read the item's metadata now, with the linker's account, and record what was seen.
    A missing item sets `unavailable_since`; a later success clears it. Does nothing when
    `check_blocked` gives a reason (the UI shows it). Raises IntegrationError on a transient
    failure."""
    provider = registry.PROVIDERS.get(link.provider)
    account = link.connected_account
    if provider is None or provider.fetch_item is None:
        return link
    if provider.needs_account and account is None:
        return link
    if check_blocked(link):
        return link
    try:
        meta = provider.fetch_item(account, link.external_id)
    except AccountUnavailable:
        return link
    now = timezone.now()
    if meta is None:
        link.unavailable_since = link.unavailable_since or now
    else:
        link.unavailable_since = None
        link.remote_modified_at = meta.get("modified_at")
        link.remote_version = (meta.get("version") or "")[:100]
        link.remote_checksum = (meta.get("checksum") or "")[:140]
        if meta.get("title") and provider.auth_type != AuthType.LINK_ONLY:  # keep their title
            link.title = meta["title"][:500]
    link.last_checked_at = now
    link.save(
        update_fields=[
            "unavailable_since",
            "remote_modified_at",
            "remote_version",
            "remote_checksum",
            "title",
            "last_checked_at",
            "updated_at",
        ]
    )
    return link


@transaction.atomic
def accept_change(link, *, user, request=None) -> ExternalLink:
    """Record the values last seen as the new baseline. The linked dataset record is not
    touched (D76)."""
    link.linked_modified_at = link.remote_modified_at
    link.linked_version = link.remote_version
    link.linked_checksum = link.remote_checksum
    link.save(
        update_fields=["linked_modified_at", "linked_version", "linked_checksum", "updated_at"]
    )
    audit.record(
        AuditAction.EXTERNAL_LINK_CHANGE_ACCEPTED,
        actor=user,
        lab=link.lab,
        target=link,
        request=request,
        metadata={"provider": link.provider, "external_id": link.external_id},
    )
    return link


CHECK_MIN_INTERVAL = 60  # seconds between manual checks of one link (D78)
CHECK_PAUSE = 0.2  # seconds between provider calls in the daily job


def check_lab_links(lab) -> dict:
    """Refresh every link of `lab` whose linker's account is active, and every link of a
    provider that is read without an account and offers `fetch_item` (public, link_only).
    Others are skipped (the API reports `check_blocked`). One link gets a time budget (and one
    lab a larger one, D120): a slow or hostile server costs that link, never the rest. A
    failure on one link never stops the others."""
    accountless = [
        p.name for p in registry.PROVIDERS.values() if not p.needs_account and p.fetch_item
    ]
    done = skipped = failed = 0
    stop_at = time.monotonic() + settings.INTEGRATION_JOB_LAB_BUDGET
    links = ExternalLink.objects.for_lab(lab).select_related(
        "connected_account", "project", "linked_by"
    )
    checkable = Q(connected_account__isnull=False) | Q(provider__in=accountless)
    for link in links.filter(checkable).order_by("pk"):
        if time.monotonic() >= stop_at:
            log.warning("integration link checks for a lab stopped at its time budget")
            failed += 1  # the rest are checked tomorrow
            break
        if check_blocked(link):
            skipped += 1
            continue
        try:
            with http.budget(
                settings.INTEGRATION_JOB_LINK_BUDGET,
                per_request=settings.INTEGRATION_JOB_HTTP_DEADLINE,
            ):
                check_link(link)
            done += 1
        except Exception as exc:  # noqa: BLE001 - messages are fixed; log the type only
            log.warning("integration link check failed: %s", type(exc).__name__)
            failed += 1
        time.sleep(CHECK_PAUSE)
    return {"checked": done, "skipped": skipped, "failed": failed}


def check_all_links() -> dict:
    """Every lab in turn (`check_lab_links`); one lab's failure never stops the others. The
    daily schedule runs one Celery task per lab instead (jobs.check_lab_links)."""
    total = {"checked": 0, "skipped": 0, "failed": 0}
    for lab in Lab.objects.all():
        try:
            result = check_lab_links(lab)
        except Exception as exc:  # noqa: BLE001
            log.warning("integration link checks for a lab failed: %s", type(exc).__name__)
            total["failed"] += 1
            continue
        for key, value in result.items():
            total[key] += value
    return total


# ---- key rotation


def rotate_token_encryption() -> int:
    """Re-encrypt every stored token under the newest key (D63). Run after adding a key, before
    removing an old one. Each row is locked and re-read, so a concurrent disconnect's wiped
    tokens never come back. Returns the number of accounts rewritten."""
    count = 0
    for lab in Lab.objects.all():
        ids = ConnectedAccount.objects.for_lab(lab).values_list("pk", flat=True)
        for pk in list(ids):
            with transaction.atomic():
                row = ConnectedAccount.objects.for_lab(lab).select_for_update().get(pk=pk)
                if not (row.access_token_ct or row.refresh_token_ct):
                    continue
                row.access_token_ct = crypto.rotate(row.access_token_ct)
                row.refresh_token_ct = crypto.rotate(row.refresh_token_ct)
                row.save(update_fields=["access_token_ct", "refresh_token_ct"])
                count += 1
    return count


# ---- task import (D240)


def active_account_or_404(lab, user, provider) -> ConnectedAccount:
    """The person's own active account at `provider` here. The answer for "none" is the same as
    for a service that is switched off: 404."""
    account = (
        ConnectedAccount.objects.for_lab(lab)
        .filter(user=user, provider=provider.name, status=AccountStatus.ACTIVE)
        .first()
    )
    if account is None:
        raise Http404
    return account


def _task_provider(name):
    provider = registry.PROVIDERS.get(name)
    if provider is None or provider.fetch_tasks is None or not provider.configured:
        raise Http404
    return provider


@http.interactive
def task_sources(lab, *, user, provider_name) -> list[dict]:
    provider = _task_provider(provider_name)
    account = active_account_or_404(lab, user, provider)
    try:
        return provider.task_sources(account)
    except (KeyError, TypeError, ValueError):
        raise IntegrationError(f"{provider.label} returned an unreadable answer") from None


@http.interactive
def import_tasks(*, project, user, provider_name, source, request=None) -> dict:
    """Copy tasks from an outside list into `project`, unassigned and to do. A task whose title
    is already in the project is skipped, so importing twice adds nothing. ponytail: titles, not
    the outside ids, so a task renamed there comes in again; store ids if that is a nuisance."""
    from projects.models import Task
    from projects.services import create_task

    provider = _task_provider(provider_name)
    account = active_account_or_404(project.lab, user, provider)
    try:
        found = provider.fetch_tasks(account, source)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise IntegrationError(f"{provider.label} returned an unreadable answer") from None
    tasks = Task.objects.for_lab(project.lab).filter(project=project)
    seen = {title.casefold() for title in tasks.values_list("title", flat=True)}
    created = skipped = 0
    with transaction.atomic():
        for item in found:
            if item["title"].casefold() in seen:
                skipped += 1
                continue
            seen.add(item["title"].casefold())
            create_task(
                project=project,
                by=user,
                data={
                    "title": item["title"],
                    "description": item["notes"],
                    "due_date": item["due_date"],
                },
            )
            created += 1
        audit.record(
            AuditAction.TASKS_IMPORTED,
            actor=user,
            lab=project.lab,
            target=project,
            request=request,
            metadata={"provider": provider.name, "created": created, "skipped": skipped},
        )
    return {"created": created, "skipped": skipped}
