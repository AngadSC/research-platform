"""Integration services (ARCHITECTURE section 9): the generic OAuth2 connect flow, token refresh,
disconnect and revoke. Views (next phase) call these and serialize the result."""

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
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from audit import services as audit
from audit.models import AuditAction
from core.models import NotificationKind
from core.notifications import notify
from core.permissions import Perm, get_lab_or_404, require
from integrations import crypto, http, registry
from integrations.http import AccountUnavailable, IntegrationError
from integrations.models import TARGET_FIELDS, AccountStatus, ConnectedAccount, ExternalLink
from labs.models import Lab
from provenance.models import validate_web_url

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


@sensitive_variables("token")
def _revoke_at_provider(row, token) -> bool:
    """Best effort: any failure means "not revoked" and never propagates."""
    provider = registry.PROVIDERS.get(row.provider)
    try:
        if provider is None or not provider.revoke_url or not token or _grant_used_elsewhere(row):
            return False
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


@transaction.atomic
def create_link(*, project, user, data, request=None) -> ExternalLink:
    """Link an outside item to `project` (the caller already holds edit_content). The provider
    is asked for the item's metadata with the linker's own active account in this lab."""
    provider = registry.PROVIDERS.get(data["provider"])
    if provider is None:
        raise ValidationError({"provider": "This service is not available."})
    if not provider.valid_external_id(data["external_id"]):
        raise ValidationError({"external_id": "This is not a valid item id."})
    account, meta = None, {}
    if provider.auth_type == registry.AuthType.LINK_ONLY:
        if not (data.get("url") and data.get("title")):
            raise ValidationError({"url": "Give the link's address and title."})
        meta = {k: data.get(k, "") for k in ("url", "title", "mime_type")}
    else:
        account = (
            ConnectedAccount.objects.for_lab(project.lab_id)
            .filter(user=user, provider=provider.name, status=AccountStatus.ACTIVE)
            .first()
        )
        if account is None:
            raise ValidationError({"provider": f"Connect your {provider.label} account first."})
        if provider.fetch_item is None:
            raise ValidationError({"provider": f"Linking {provider.label} items is not ready yet."})
        try:
            meta = provider.fetch_item(account, data["external_id"])
        except IntegrationError:
            raise ValidationError(
                {"external_id": f"{provider.label} could not be reached. Try again shortly."}
            ) from None
        if meta is None:
            raise ValidationError(
                {"external_id": f"Not found in {provider.label}, or you can't open it."}
            )
    try:
        validate_web_url(meta["url"])
    except DjangoValidationError:
        raise ValidationError({"url": "Enter a web address starting with http or https."}) from None
    targets = {f: _target(project, f, data[f]) for f in TARGET_FIELDS if data.get(f) is not None}
    now = timezone.now()
    link = ExternalLink.objects.create(
        lab=project.lab,
        project=project,
        provider=provider.name,
        connected_account=account,
        external_id=data["external_id"],
        url=meta["url"],
        title=(meta["title"] or data["external_id"])[:500],
        mime_type=(meta.get("mime_type") or "")[:255],
        linked_by=user,
        linked_modified_at=meta.get("modified_at"),
        linked_version=(meta.get("version") or "")[:100],
        linked_checksum=(meta.get("checksum") or "")[:140],
        remote_modified_at=meta.get("modified_at"),
        remote_version=(meta.get("version") or "")[:100],
        remote_checksum=(meta.get("checksum") or "")[:140],
        last_checked_at=now if account else None,
        **targets,
    )
    link.version_note = _copy_version(link, user=user, request=request)
    audit.record(
        AuditAction.EXTERNAL_LINK_CREATED,
        actor=user,
        lab=project.lab,
        target=link,
        request=request,
        metadata={
            "provider": provider.name,
            "external_id": link.external_id,
            **({"version_copy": link.version_note} if link.dataset_id else {}),
        },
    )
    return link


VERSION_PREFIX = {"google_drive": "drive-version"}  # for files with no checksum (D76)


def _copy_version(link, *, user, request) -> str:
    """D76: a linked file's checksum (or version) goes into the dataset record's `checksum`
    only while that is empty. Returns "copied", "same", "kept" (the record has a different
    value, left alone: a new version is a new row, D20) or "none" (the file has no version)."""
    if not link.dataset_id:
        return ""
    version = (link.remote_version or "").strip()
    prefix = VERSION_PREFIX.get(link.provider)
    value = link.remote_checksum or (f"{prefix}:{version}" if prefix and version.isdigit() else "")
    if not value:
        return "none"
    dataset = link.dataset
    if dataset.checksum == value:
        return "same"
    if dataset.checksum:
        return "kept"
    dataset.checksum = value
    dataset.save(update_fields=["checksum", "updated_at"])
    audit.record(
        AuditAction.DATASET_UPDATED,
        actor=user,
        lab=link.lab,
        target=dataset,
        request=request,
        metadata={"source": "external_link", "fields": ["checksum"]},
    )
    return "copied"


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


def check_link(link) -> ExternalLink:
    """Read the item's metadata now, with the linker's account, and record what was seen.
    A missing item sets `unavailable_since`; a later success clears it. Does nothing when the
    linker's account is not active (the UI says why). Raises IntegrationError on a transient
    failure."""
    provider = registry.PROVIDERS.get(link.provider)
    account = link.connected_account
    if provider is None or provider.fetch_item is None or account is None:
        return link
    if account.status != AccountStatus.ACTIVE:
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
        if meta.get("title"):
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


CHECK_PAUSE = 0.2  # seconds between provider calls in the daily job


def check_all_links() -> dict:
    """Daily job: refresh every link whose linker's account is active. Others are skipped (the
    API reports `check_blocked`). A failure on one link never stops the rest."""
    done = skipped = failed = 0
    for lab in Lab.objects.all():
        links = ExternalLink.objects.for_lab(lab).select_related("connected_account", "project")
        for link in links.filter(connected_account__isnull=False).order_by("pk"):
            if link.connected_account.status != AccountStatus.ACTIVE:
                skipped += 1
                continue
            try:
                check_link(link)
                done += 1
            except Exception as exc:  # noqa: BLE001 - messages are fixed; log the type only
                log.warning("integration link check failed: %s", type(exc).__name__)
                failed += 1
            time.sleep(CHECK_PAUSE)
    return {"checked": done, "skipped": skipped, "failed": failed}


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
