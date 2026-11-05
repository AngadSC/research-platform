"""Regression tests for the integrations security review: shared grants, lifecycle revoke,
the orphan sweep, key rotation under a concurrent disconnect, and external id / port checks."""

import pytest
import requests
from cryptography.fernet import Fernet
from django.test import Client

from audit.models import AuditAction, AuditEvent
from config.settings import CELERY_BEAT_SCHEDULE
from integrations import http, registry, services
from integrations.http import IntegrationError
from integrations.jobs import revoke_orphans
from integrations.models import AccountStatus, ConnectedAccount
from integrations.tests.fake import FAKE, response
from labs.models import LabMembership

pytestmark = pytest.mark.django_db


def fresh(account):
    return ConnectedAccount.objects.for_lab(account.lab_id).get(pk=account.pk)


def assert_revoked(account):
    row = fresh(account)
    assert row.status == AccountStatus.REVOKED
    assert row.access_token_ct == "" and row.refresh_token_ct == "" and row.token_expires_at is None


# ---- 1. a grant shared with anyone else is never revoked at the provider


def test_grant_shared_with_another_user_in_another_lab_is_not_revoked(
    lab_users, connect, make_lab, make_user, join, transport
):
    lab, u = lab_users
    other_lab, other_user = make_lab("Other"), make_user()
    join(other_user, other_lab, "member")
    mine = connect(u["member"], lab, ext_id="shared")
    theirs = connect(other_user, other_lab, ext_id="shared")
    services.disconnect(mine, actor=u["member"])
    assert transport.sent("POST", FAKE.revoke_url) == []
    assert_revoked(mine)
    assert fresh(theirs).status == AccountStatus.ACTIVE
    # once nobody else holds it, the grant is revoked
    transport.on("POST", FAKE.revoke_url, response(200))
    services.disconnect(theirs, actor=other_user)
    assert len(transport.sent("POST", FAKE.revoke_url)) == 1


# ---- 2. lifecycle revoke


def test_http_wraps_every_requests_error(lab_users, connect, transport):
    lab, u = lab_users
    account = connect(u["member"], lab)
    url = "https://api.fake.test/files/1"
    for exc in (requests.exceptions.ChunkedEncodingError("x"), requests.exceptions.InvalidURL("x")):
        transport.on("POST", url, exc)
        with pytest.raises(IntegrationError):
            http.send("POST", url, provider=FAKE, account=account)


@pytest.mark.parametrize(
    "error",
    [
        requests.exceptions.ChunkedEncodingError("cut off"),
        RuntimeError("unexpected"),
    ],
)
def test_failing_provider_revoke_never_undoes_the_local_revoke(
    lab_users, connect, transport, django_capture_on_commit_callbacks, error
):
    lab, u = lab_users
    account = connect(u["member"], lab)
    transport.on("POST", FAKE.revoke_url, error)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        assert services.revoke_member_accounts(lab, u["member"], reason="member_removed") == 1
    # revoked, wiped and audited in the caller's transaction, before any provider call
    assert_revoked(account)
    assert transport.sent("POST", FAKE.revoke_url) == []
    assert AuditEvent.objects.filter(action=AuditAction.INTEGRATION_REVOKED).count() == 1
    for callback in callbacks:
        callback()  # must not raise
    assert len(transport.sent("POST", FAKE.revoke_url)) >= 1
    assert_revoked(account)


def test_undecryptable_tokens_are_still_wiped(lab_users, connect, transport):
    lab, u = lab_users
    account = connect(u["member"], lab)
    ConnectedAccount.objects.for_lab(lab).filter(pk=account.pk).update(refresh_token_ct="garbage")
    services.revoke_member_accounts(lab, u["member"], reason="member_removed")
    assert_revoked(account)


def test_lifecycle_revoke_is_atomic_with_the_membership_change(lab_users, connect, transport):
    from django.db import transaction

    lab, u = lab_users
    account = connect(u["member"], lab)
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            services.revoke_member_accounts(lab, u["member"], reason="member_removed")
            assert_revoked(account)  # already done inside the caller's transaction
            raise RuntimeError("the membership change failed")
    assert fresh(account).status == AccountStatus.ACTIVE  # rolled back together


# ---- the daily sweep


def test_sweep_is_scheduled_daily():
    assert CELERY_BEAT_SCHEDULE["integrations-revoke-orphans"]["task"] == (
        "integrations.jobs.revoke_orphans"
    )


def test_sweep_revokes_orphaned_accounts_only(
    lab_users, connect, transport, make_user, join, django_capture_on_commit_callbacks
):
    lab, u = lab_users
    transport.on("POST", FAKE.revoke_url, response(200))
    left = connect(u["member"], lab, ext_id="e1")  # membership deleted behind our back
    gone = connect(u["viewer"], lab, ext_id="e2")  # user deactivated without the signal
    kept = connect(u["pi"], lab, ext_id="e3")
    LabMembership.objects.for_lab(lab).filter(user=u["member"]).delete()
    type(u["viewer"]).objects.filter(pk=u["viewer"].pk).update(is_active=False)
    with django_capture_on_commit_callbacks(execute=True):
        assert revoke_orphans() == 2
    assert_revoked(left)
    assert_revoked(gone)
    assert fresh(kept).status == AccountStatus.ACTIVE
    assert AuditEvent.objects.filter(actor_label="lifecycle:orphan_sweep").count() == 2
    assert revoke_orphans() == 0


# ---- 3. rotation never resurrects a concurrently wiped token


def test_rotation_skips_rows_wiped_meanwhile(lab_users, connect, settings, monkeypatch):
    lab, u = lab_users
    connect(u["member"], lab, ext_id="e1")
    connect(u["viewer"], lab, ext_id="e2")
    settings.INTEGRATION_ENCRYPTION_KEYS = [
        Fernet.generate_key().decode(),
        *settings.INTEGRATION_ENCRYPTION_KEYS,
    ]
    real, wiped = services.crypto.rotate, []

    def rotate_and_wipe_the_other_row(ct):
        if not wiped:  # a disconnect lands while the first row is being rotated
            others = ConnectedAccount.objects.for_lab(lab).exclude(access_token_ct=ct)
            wiped.extend(others.values_list("pk", flat=True))
            others.update(access_token_ct="", refresh_token_ct="", status=AccountStatus.REVOKED)
        return real(ct)

    monkeypatch.setattr(services.crypto, "rotate", rotate_and_wipe_the_other_row)
    assert services.rotate_token_encryption() == 1
    (other,) = ConnectedAccount.objects.for_lab(lab).filter(pk__in=wiped)
    assert other.access_token_ct == "" and other.refresh_token_ct == ""


# ---- 4. external ids and ports


def test_default_external_id_pattern():
    ok = ["abc", "A-b_c.1", "x" * 255]
    bad = ["", "a/b", "../x", "a?b", "a b", "a\n", "x" * 256, "a#b", "a%2Fb"]
    assert all(registry.GOOGLE.valid_external_id(v) for v in ok)
    assert not any(registry.GOOGLE.valid_external_id(v) for v in bad)


def test_provider_can_narrow_the_pattern():
    drive = registry.Provider(
        name="d",
        label="D",
        auth_type=registry.AuthType.LINK_ONLY,
        external_id_pattern=r"^[A-Za-z0-9_-]+$",
    )
    assert drive.valid_external_id("1aB_-") and not drive.valid_external_id("a.b")


@pytest.mark.parametrize("external_id", ["../../x", "a/b", "a?x=1", "a b", "a#b"])
def test_link_create_refuses_a_malformed_external_id(
    lab_users, connect, transport, make_project, external_id
):
    lab, u = lab_users
    connect(u["pi"], lab)
    project = make_project(lab)
    c = Client()
    c.force_login(u["pi"])
    before = len(transport.calls)
    resp = c.post(
        f"/api/labs/{lab.pk}/projects/{project.pk}/external-links/",
        {"provider": "fake", "external_id": external_id},
        "application/json",
    )
    assert resp.status_code == 400 and "external_id" in resp.json()
    assert len(transport.calls) == before  # nothing was sent to the provider


def test_service_refuses_a_malformed_external_id_too(lab_users, connect, make_project):
    from rest_framework.exceptions import ValidationError

    lab, u = lab_users
    connect(u["pi"], lab)
    with pytest.raises(ValidationError) as exc:
        services.create_link(
            project=make_project(lab),
            user=u["pi"],
            data={"provider": "fake", "external_id": "../etc"},
        )
    assert "external_id" in exc.value.detail


def test_non_default_port_is_refused(lab_users, connect, transport):
    lab, u = lab_users
    account = connect(u["member"], lab)
    for url in ("https://api.fake.test:8443/files/1", "https://api.fake.test:80/files/1"):
        with pytest.raises(IntegrationError, match="refused a request"):
            http.send("GET", url, provider=FAKE, account=account)
    assert not any(":8443" in c[1] or ":80/" in c[1] for c in transport.calls)
    transport.on("GET", "https://api.fake.test:443/files/1", response(200, {}))
    assert http.send("GET", "https://api.fake.test:443/files/1", provider=FAKE).status_code == 200
