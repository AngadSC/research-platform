"""Every audited action that has a code path today, driven through the API: exactly one
AuditEvent with the right actor, action, target, lab and IP (ARCHITECTURE section 4)."""

import pytest
from allauth.mfa.totp.internal import auth as totp
from django.test import Client, TestCase, override_settings
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from labs.models import Invite, Lab, LabRole
from projects.models import ChatMessage

pytestmark = pytest.mark.django_db

IP = "203.0.113.7"
BASE = "/_allauth/browser/v1"


def api(user=None):
    client = APIClient(REMOTE_ADDR=IP)
    if user:
        client.force_login(user)
    return client


def one(action):
    qs = AuditEvent.objects.filter(action=action)
    assert qs.count() == 1, list(AuditEvent.objects.values_list("action", flat=True))
    return qs.get()


def check(event, *, actor, lab, target=None, ip=IP):
    assert event.actor == actor and event.lab == lab and event.ip == ip
    if target is None:
        assert event.target_type == "" and event.target_id is None
    else:
        assert (event.target_type, event.target_id) == (target._meta.label, target.pk)


@pytest.fixture
def lab_pi(make_lab, make_user, join):
    lab, pi = make_lab("Cov Lab"), make_user()
    join(pi, lab, LabRole.PI)
    return lab, pi


def test_lab_created(make_user):
    user = make_user()
    resp = api(user).post("/api/labs/", {"name": "New"}, "json")
    assert resp.status_code == 201
    check(one(AuditAction.LAB_CREATED), actor=user, lab=Lab.objects.get(pk=resp.json()["id"]))


def test_invite_create_revoke_accept(lab_pi, make_user, verify_email, mailoutbox):
    lab, pi = lab_pi
    body = {"email": "i@example.com", "role": "member"}
    resp = api(pi).post(f"/api/labs/{lab.pk}/invites/", body, "json")
    assert resp.status_code == 201
    revoked = Invite.objects.for_lab(lab).get(pk=resp.json()["id"])
    check(one(AuditAction.MEMBERSHIP_INVITED), actor=pi, lab=lab, target=revoked)

    assert api(pi).delete(f"/api/labs/{lab.pk}/invites/{revoked.pk}/").status_code == 204
    check(one(AuditAction.MEMBERSHIP_INVITE_REVOKED), actor=pi, lab=lab, target=revoked)

    with TestCase.captureOnCommitCallbacks(execute=True):
        api(pi).post(f"/api/labs/{lab.pk}/invites/", body, "json")
    token = mailoutbox[-1].body.split("/invite/")[1].split()[0]
    invitee = make_user(email="i@example.com")
    verify_email(invitee)
    resp = api(invitee).post("/api/invites/accept/", {"token": token}, "json")
    assert resp.status_code == 200, resp.content
    accepted = Invite.objects.for_lab(lab).exclude(pk=revoked.pk).get()
    check(one(AuditAction.MEMBERSHIP_INVITE_ACCEPTED), actor=invitee, lab=lab, target=accepted)


def test_role_change_and_removal(lab_pi, make_user, join):
    lab, pi = lab_pi
    m = join(make_user(), lab, LabRole.MEMBER)
    url = f"/api/labs/{lab.pk}/members/{m.pk}/"
    assert api(pi).patch(url, {"role": "viewer"}, "json").status_code == 200
    check(one(AuditAction.MEMBERSHIP_ROLE_CHANGED), actor=pi, lab=lab, target=m)
    assert api(pi).delete(url).status_code == 204
    event = one(AuditAction.MEMBERSHIP_REMOVED)  # the row is gone, so compare by label and id
    assert (event.actor, event.lab, event.ip) == (pi, lab, IP)
    assert (event.target_type, event.target_id) == ("labs.LabMembership", m.pk)


def test_audit_log_viewed(lab_pi):
    lab, pi = lab_pi
    assert api(pi).get(f"/api/labs/{lab.pk}/audit-events/").status_code == 200
    check(one(AuditAction.AUDIT_LOG_VIEWED), actor=pi, lab=lab)


# ---------------------------------------------------------------- auth (allauth headless)


def _csrf(client):
    return {"X-CSRFToken": client.cookies["csrftoken"].value}


def _login(client, password="pw"):
    client.get(f"{BASE}/config")
    body = {"email": "u@example.com", "password": password}
    return client.post(f"{BASE}/auth/login", body, "application/json", headers=_csrf(client))


@pytest.fixture
def auth_user(make_user, verify_email):
    user = make_user(email="u@example.com")
    verify_email(user)
    return user


def test_login_failed_login_logout(auth_user):
    client = Client(REMOTE_ADDR=IP)
    assert _login(client, "nope").status_code == 400
    check(one(AuditAction.AUTH_LOGIN_FAILED), actor=None, lab=None)
    assert _login(client).status_code == 200
    check(one(AuditAction.AUTH_LOGIN), actor=auth_user, lab=None)
    assert client.delete(f"{BASE}/auth/session", headers=_csrf(client)).status_code == 401
    check(one(AuditAction.AUTH_LOGOUT), actor=auth_user, lab=None)


def test_mfa_enable_and_disable(auth_user, django_capture_on_commit_callbacks):
    client = Client(REMOTE_ADDR=IP)
    assert _login(client).status_code == 200
    secret = client.get(f"{BASE}/account/authenticators/totp").json()["meta"]["secret"]
    counters = list(totp.yield_hotp_counters_from_time())
    code = totp.format_hotp_value(totp.hotp_value(secret, counters[len(counters) // 2]))
    url = f"{BASE}/account/authenticators/totp"
    reauth = {"password": "pw"}  # allauth asks for a recent password check first
    client.post(f"{BASE}/auth/reauthenticate", reauth, "application/json", headers=_csrf(client))
    with django_capture_on_commit_callbacks(execute=True):  # allauth signals fire on commit
        resp = client.post(url, {"code": code}, "application/json", headers=_csrf(client))
    assert resp.status_code == 200, resp.content
    check(one(AuditAction.AUTH_MFA_ENABLED), actor=auth_user, lab=None)
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(url, headers=_csrf(client)).status_code == 200
    check(one(AuditAction.AUTH_MFA_DISABLED), actor=auth_user, lab=None)


def test_forwarded_for_only_trusted_behind_proxies(auth_user):
    xff = {"HTTP_X_FORWARDED_FOR": "198.51.100.1, 198.51.100.2"}
    _login(Client(REMOTE_ADDR=IP, **xff))  # TRUSTED_PROXY_COUNT is 0: the header is ignored
    with override_settings(TRUSTED_PROXY_COUNT=1):
        _login(Client(REMOTE_ADDR=IP, **xff))
    ips = AuditEvent.objects.filter(action=AuditAction.AUTH_LOGIN).values_list("ip", flat=True)
    assert sorted(ips) == ["198.51.100.2", IP]


def test_chat_message_deleted_keeps_no_text(lab_pi, make_project):
    lab, pi = lab_pi
    project = make_project(lab)
    message = ChatMessage.objects.create(lab=lab, project=project, author=pi, body="secret text")
    assert api(pi).delete(f"/api/labs/{lab.pk}/messages/{message.pk}/").status_code == 204
    event = one(AuditAction.CHAT_MESSAGE_DELETED)
    check(event, actor=pi, lab=lab, target=message)
    assert "secret text" not in str(event.metadata)
