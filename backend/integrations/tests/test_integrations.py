import base64
import hashlib
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from audit.models import AuditEvent
from core.models import Notification
from core.tenancy import CrossLabError
from documents.models import Document
from integrations import crypto, http, services
from integrations.http import AccountUnavailable, IntegrationError
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink
from integrations.services import OAuthError
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import FAKE, response

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parents[2]


def actions(lab):
    return list(AuditEvent.objects.filter(lab=lab).values_list("action", flat=True))


# ---- crypto and settings


def test_crypto_round_trip_and_rotation(settings):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.INTEGRATION_ENCRYPTION_KEYS = [old]
    ct = crypto.encrypt("secret-token")
    assert "secret-token" not in ct and crypto.decrypt(ct) == "secret-token"
    settings.INTEGRATION_ENCRYPTION_KEYS = [new, old]  # newest first
    assert crypto.decrypt(ct) == "secret-token"
    rotated = crypto.rotate(ct)
    settings.INTEGRATION_ENCRYPTION_KEYS = [new]
    assert crypto.decrypt(rotated) == "secret-token"
    with pytest.raises(ImproperlyConfigured):
        crypto.decrypt(ct)  # the old key is gone


def test_malformed_key_fails_without_echoing_it(settings):
    settings.INTEGRATION_ENCRYPTION_KEYS = ["not-a-key-CANARY"]
    with pytest.raises(ImproperlyConfigured) as exc:
        crypto.encrypt("x")
    assert "CANARY" not in str(exc.value)


def _settings_env(**env):
    full = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DEBUG", "SECRET_KEY", "INTEGRATION_ENCRYPTION_KEYS")
    }
    full.update(env, DJANGO_SETTINGS_MODULE="config.settings")
    return full


def test_missing_keys_fail_closed_outside_debug():
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=BACKEND,
        env=_settings_env(DEBUG="False", SECRET_KEY="x" * 50),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "INTEGRATION_ENCRYPTION_KEYS" in result.stderr


def test_debug_uses_a_persisted_random_dev_key(tmp_path):
    key_file = tmp_path / "dev_key"
    code = "import config.settings as s; print(s.INTEGRATION_ENCRYPTION_KEYS[0])"
    env = _settings_env(DEBUG="True", DEV_INTEGRATION_KEY_FILE=str(key_file))
    run = lambda: subprocess.run(  # noqa: E731
        [sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True
    ).stdout.strip()
    first = run()
    assert key_file.exists() and first == run()
    Fernet(first)  # a valid key


# ---- connect flow


def _state(url):
    return parse_qs(urlsplit(url).query)


def test_start_builds_pkce_url_bound_to_session(lab_users, settings):
    lab, u = lab_users
    request = make_request(u["viewer"])  # every lab role may connect its own account
    q = _state(services.start_connect(request, lab, "fake"))
    assert q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == [settings.INTEGRATION_OAUTH_REDIRECT_URI]
    assert q["include_granted_scopes"] == ["true"] and q["client_id"] == ["fake-client"]
    entry = request.session[services.SESSION_KEY][q["state"][0]]
    assert entry["user"] == str(u["viewer"].pk) and entry["lab"] == str(lab.pk)
    digest = hashlib.sha256(entry["verifier"].encode()).digest()
    assert q["code_challenge"] == [base64.urlsafe_b64encode(digest).decode().rstrip("=")]
    assert settings.INTEGRATION_OAUTH_REDIRECT_URI.endswith("/api/integrations/oauth/callback/")


def test_start_rejects_unknown_scope_provider_and_outsider(lab_users, make_user):
    lab, u = lab_users
    with pytest.raises(OAuthError, match="invalid_scope"):
        services.start_connect(make_request(u["member"]), lab, "fake", ["admin.everything"])
    with pytest.raises(OAuthError, match="unknown_provider"):
        services.start_connect(make_request(u["member"]), lab, "nope")
    with pytest.raises(Http404):
        services.start_connect(make_request(make_user()), lab, "fake")


def test_pending_states_are_capped(lab_users):
    lab, u = lab_users
    request = make_request(u["member"])
    for _ in range(services.MAX_PENDING + 3):
        services.start_connect(request, lab, "fake")
    assert len(request.session[services.SESSION_KEY]) == services.MAX_PENDING


def test_callback_stores_encrypted_tokens_and_audits(lab_users, connect, transport):
    lab, u = lab_users
    account = connect(u["member"], lab, access="at-plain", refresh="rt-plain")
    assert account.status == AccountStatus.ACTIVE and account.external_email == "a@fake.test"
    assert account.granted_scopes == ["files.meta", "files.read"]
    assert "at-plain" not in account.access_token_ct and account.access_token() == "at-plain"
    assert account.refresh_token() == "rt-plain"
    sent = transport.sent("POST", FAKE.token_url)[0]["data"]
    assert sent["grant_type"] == "authorization_code" and sent["code_verifier"]
    identity = transport.sent("GET", FAKE.identity_url)[0]["headers"]
    assert identity["Authorization"] == "Bearer at-plain"
    assert actions(lab) == ["integration.connected"]


def test_state_is_single_use_and_bound_to_user_and_session(lab_users, transport):
    lab, u = lab_users
    request = make_request(u["member"])
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    with pytest.raises(OAuthError, match="invalid_state"):  # another user, same session
        services.complete_connect(make_request(u["pi"], request.session), state=state, code="c")
    with pytest.raises(OAuthError, match="invalid_state"):  # consumed by the failed attempt
        services.complete_connect(request, state=state, code="c")
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    with pytest.raises(OAuthError, match="invalid_state"):  # another session
        services.complete_connect(make_request(u["member"]), state=state, code="c")
    assert transport.calls == []


def test_expired_state_and_denied_consent(lab_users, transport):
    lab, u = lab_users
    request = make_request(u["member"])
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    pending = request.session[services.SESSION_KEY]
    pending[state]["at"] -= services.STATE_TTL + 1
    request.session[services.SESSION_KEY] = pending
    with pytest.raises(OAuthError, match="invalid_state"):
        services.complete_connect(request, state=state, code="c")
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    with pytest.raises(OAuthError, match="access_denied"):
        services.complete_connect(request, state=state, error="access_denied")


def test_callback_rechecks_membership(lab_users, transport):
    lab, u = lab_users
    request = make_request(u["member"])
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    from labs.models import LabMembership

    LabMembership.objects.for_lab(lab).filter(user=u["member"]).delete()
    from core.permissions import forget

    forget(u["member"])
    with pytest.raises(Http404):
        services.complete_connect(request, state=state, code="c")


def test_ungranted_scope_is_refused(lab_users, transport):
    lab, u = lab_users
    request = make_request(u["member"])
    state = _state(services.start_connect(request, lab, "fake"))["state"][0]
    transport.on("POST", FAKE.token_url, token_reply("at", "rt", scope="files.read"))
    with pytest.raises(OAuthError, match="scope_not_granted"):
        services.complete_connect(request, state=state, code="c")
    assert not ConnectedAccount.objects.for_lab(lab).exists()


def test_reconnect_reuses_row_and_other_account_is_refused(lab_users, connect, transport):
    lab, u = lab_users
    first = connect(u["member"], lab)
    transport.on("POST", FAKE.revoke_url, response(200))
    services.disconnect(first, actor=u["member"])
    again = connect(u["member"], lab, access="at-2", refresh="rt-2")
    assert again.pk == first.pk and again.status == AccountStatus.ACTIVE
    with pytest.raises(OAuthError, match="other_account_connected"):
        connect(u["member"], lab, ext_id="ext-other")


# ---- HTTP client


@pytest.fixture
def account(lab_users, connect):
    lab, u = lab_users
    return connect(u["member"], lab)


FILE_URL = "https://api.fake.test/files/1"


def test_refuses_foreign_host_and_plain_http(account, transport):
    for url in ("https://evil.test/x", "http://api.fake.test/x"):
        with pytest.raises(IntegrationError, match="refused a request"):
            http.send("GET", url, provider=FAKE, account=account)
    assert transport.sent("GET", "https://evil.test/x") == []


def test_cross_host_redirect_refused_same_host_followed(account, transport):
    transport.on("GET", FILE_URL, response(302, headers={"Location": "https://evil.test/steal"}))
    with pytest.raises(IntegrationError, match="redirect to another host"):
        http.send("GET", FILE_URL, provider=FAKE, account=account)
    assert transport.sent("GET", "https://evil.test/steal") == []
    transport.on("GET", FILE_URL, response(302, headers={"Location": "/files/2"}))
    transport.on("GET", "https://api.fake.test/files/2", response(200, {"ok": True}))
    assert http.send("GET", FILE_URL, provider=FAKE, account=account).json() == {"ok": True}
    assert transport.calls[-1][2]["allow_redirects"] is False
    assert transport.calls[-1][2]["timeout"] == http.TIMEOUT


def test_retries_idempotent_requests_only(account, transport):
    transport.on("GET", FILE_URL, response(503), requests.ConnectionError("x"), response(200, {}))
    assert http.send("GET", FILE_URL, provider=FAKE, account=account).status_code == 200
    assert len(transport.sent("GET", FILE_URL)) == 3
    transport.on("POST", FILE_URL, response(503))
    assert http.send("POST", FILE_URL, provider=FAKE, account=account).status_code == 503
    assert len(transport.sent("POST", FILE_URL)) == 1
    transport.on("GET", FILE_URL, requests.Timeout("detail"))
    with pytest.raises(IntegrationError) as exc:
        http.send("GET", FILE_URL, provider=FAKE, account=account)
    assert "detail" not in str(exc.value) and exc.value.__cause__ is None


def test_401_refreshes_once_and_retries(account, transport):
    transport.on("GET", FILE_URL, response(401), response(200, {}))
    transport.on("POST", FAKE.token_url, token_reply("at-new", None))
    assert http.send("GET", FILE_URL, provider=FAKE, account=account).status_code == 200
    auth = [kw["headers"]["Authorization"] for kw in transport.sent("GET", FILE_URL)]
    assert auth == ["Bearer at-1", "Bearer at-new"]
    account.refresh_from_db()
    assert account.access_token() == "at-new" and account.refresh_token() == "rt-1"
    assert account.last_used_at is not None


def test_expiring_token_is_refreshed_first(account, transport):
    ConnectedAccount.objects.for_lab(account.lab).filter(pk=account.pk).update(
        token_expires_at=timezone.now() + timedelta(seconds=10)
    )
    account.refresh_from_db()
    transport.on("POST", FAKE.token_url, token_reply("at-new", "rt-rotated"))
    transport.on("GET", FILE_URL, response(200, {}))
    http.send("GET", FILE_URL, provider=FAKE, account=account)
    assert transport.sent("GET", FILE_URL)[0]["headers"]["Authorization"] == "Bearer at-new"
    assert account.refresh_token() == "rt-rotated"


def test_refused_refresh_marks_expired_audits_and_notifies(account, transport):
    transport.on("GET", FILE_URL, response(401))
    transport.on("POST", FAKE.token_url, response(400, {"error": "invalid_grant"}))
    with pytest.raises(AccountUnavailable):
        http.send("GET", FILE_URL, provider=FAKE, account=account)
    assert account.status == AccountStatus.EXPIRED
    assert account.access_token_ct == "" and account.refresh_token_ct == ""
    event = AuditEvent.objects.get(action="integration.refresh_failed")
    assert event.metadata == {"provider": "fake", "reason": "invalid_grant", "status": "expired"}
    assert Notification.objects.for_lab(account.lab).get().recipient_id == account.user_id
    with pytest.raises(AccountUnavailable):  # no further calls on an unusable account
        http.send("GET", FILE_URL, provider=FAKE, account=account)


def test_other_refresh_errors_mark_error_and_transient_ones_change_nothing(account, transport):
    transport.on("GET", FILE_URL, response(401))
    transport.on("POST", FAKE.token_url, response(503))
    with pytest.raises(IntegrationError):
        http.send("GET", FILE_URL, provider=FAKE, account=account)
    account.refresh_from_db()
    assert account.status == AccountStatus.ACTIVE and account.access_token() == "at-1"
    transport.on("POST", FAKE.token_url, response(401, {"error": "invalid_client"}))
    with pytest.raises(AccountUnavailable):
        http.send("GET", FILE_URL, provider=FAKE, account=account)
    assert account.status == AccountStatus.ERROR


# ---- disconnect, revoke, lifecycle


def test_own_disconnect_revokes_at_provider(account, transport):
    transport.on("POST", FAKE.revoke_url, response(200))
    services.disconnect(account, actor=account.user)
    assert transport.sent("POST", FAKE.revoke_url)[0]["data"] == {"token": "rt-1"}
    assert account.status == AccountStatus.REVOKED and account.refresh_token_ct == ""
    event = AuditEvent.objects.get(action="integration.disconnected")
    assert event.metadata == {"provider": "fake", "provider_revoked": True}


def test_revoking_another_members_account_needs_lab_permission(lab_users, account, transport):
    lab, u = lab_users
    transport.on("POST", FAKE.revoke_url, requests.ConnectionError("down"))
    with pytest.raises(PermissionDenied):  # a viewer holds manage_integrations only
        services.disconnect(account, actor=u["viewer"])
    services.disconnect(account, actor=u["lab_admin"])  # provider down: still wiped
    assert account.status == AccountStatus.REVOKED and account.access_token_ct == ""
    event = AuditEvent.objects.get(action="integration.revoked")
    assert event.actor == u["lab_admin"] and event.metadata["provider_revoked"] is False


def test_grant_shared_with_another_lab_is_not_revoked_at_provider(
    lab_users, connect, make_lab, join, transport
):
    lab, u = lab_users
    other = make_lab("Other")
    join(u["member"], other, "member")
    here, there = connect(u["member"], lab), connect(u["member"], other)
    services.revoke_member_accounts(lab, u["member"], reason="member_removed")
    assert transport.sent("POST", FAKE.revoke_url) == []
    here.refresh_from_db()
    there.refresh_from_db()
    assert here.status == AccountStatus.REVOKED and there.status == AccountStatus.ACTIVE
    event = AuditEvent.objects.get(action="integration.revoked")
    assert event.actor is None and event.actor_label == "lifecycle:member_removed"


def test_visible_rows_own_accounts_unless_lab_manager(lab_users, connect):
    lab, u = lab_users
    mine = connect(u["member"], lab)
    theirs = connect(u["viewer"], lab, ext_id="ext-2")
    assert list(ConnectedAccount.objects.visible_to(u["member"], lab)) == [mine]
    assert set(ConnectedAccount.objects.visible_to(u["pi"], lab)) == {mine, theirs}


def test_rotate_token_encryption(account, settings):
    new = Fernet.generate_key().decode()
    settings.INTEGRATION_ENCRYPTION_KEYS = [new, *settings.INTEGRATION_ENCRYPTION_KEYS]
    assert services.rotate_token_encryption() == 1
    settings.INTEGRATION_ENCRYPTION_KEYS = [new]
    account.refresh_from_db()
    assert account.access_token() == "at-1" and account.refresh_token() == "rt-1"


# ---- ExternalLink


@pytest.fixture
def project_doc(lab_users, make_project):
    lab, u = lab_users
    project = make_project(lab)
    doc = Document.objects.create(
        lab=lab, project=project, title="d", created_by=u["pi"], updated_by=u["pi"]
    )
    return project, doc


def _link(**kw):
    return ExternalLink(provider="fake", external_id="f1", url="https://x.test/f1", title="F", **kw)


def test_external_link_stays_in_one_lab_and_project(
    lab_users, project_doc, make_lab, make_project, account
):
    lab, u = lab_users
    project, doc = project_doc
    link = _link(project=project, document=doc, linked_by=u["member"], connected_account=account)
    link.save()
    assert link.lab_id == lab.pk
    with pytest.raises(CrossLabError):
        _link(project=make_project(lab, "P2"), document=doc, linked_by=u["pi"]).save()
    with pytest.raises(CrossLabError):
        _link(project=make_project(make_lab("B")), document=doc, linked_by=u["pi"]).save()


def test_external_link_has_at_most_one_target(lab_users, project_doc):
    lab, u = lab_users
    project, doc = project_doc
    from provenance.models import DatasetRecord

    ds = DatasetRecord.objects.create(
        lab=lab, project=project, name="d", version_label="v1", created_by=u["pi"]
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        _link(project=project, document=doc, dataset=ds, linked_by=u["pi"]).save()


def test_changed_since_linked():
    now = timezone.now()
    assert _link(linked_version="3", remote_version="4").changed_since_linked
    assert not _link(linked_version="3", remote_version="3").changed_since_linked
    assert _link(linked_modified_at=now, remote_modified_at=now + timedelta(1)).changed_since_linked
    assert not _link().changed_since_linked
