from datetime import timedelta

import pytest
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from labs.models import Invite, Lab, LabMembership, LabRole

pytestmark = pytest.mark.django_db

CREATE = "/api/invites/accept/"


@pytest.fixture
def setup(make_lab, make_user, join, verify_email):
    lab = make_lab("Lab X")
    pi = make_user()
    join(pi, lab, LabRole.PI)
    invitee = make_user(email="invitee@example.com")
    verify_email(invitee)
    return lab, pi, invitee


def api(user=None):
    client = APIClient()
    if user:
        client.force_login(user)
    return client


def send_invite(lab, pi, email="invitee@example.com", role="member"):
    mail.outbox.clear()
    with TestCase.captureOnCommitCallbacks(execute=True):  # mail is sent after commit
        resp = api(pi).post(f"/api/labs/{lab.pk}/invites/", {"email": email, "role": role}, "json")
    assert resp.status_code == 201, resp.content
    body = mail.outbox[0].body
    token = body.split("/invite/")[1].split()[0]
    return resp.json(), token


def events(action):
    return AuditEvent.objects.filter(action=action)


def test_invite_token_only_in_email_and_hashed_at_rest(setup):
    lab, pi, _ = setup
    data, token = send_invite(lab, pi)
    assert token not in str(data)
    invite = Invite.objects.for_lab(lab).get(pk=data["id"])
    assert token not in invite.token_hash and invite.token_hash != token
    assert timedelta(days=6, hours=23) < invite.expires_at - timezone.now() <= timedelta(days=7)
    assert events(AuditAction.MEMBERSHIP_INVITED).filter(actor=pi).count() == 1
    assert not any(token in str(e.metadata) for e in AuditEvent.objects.all())


def test_accept_creates_membership_and_audits(setup):
    lab, pi, invitee = setup
    _, token = send_invite(lab, pi, role="viewer")
    assert api().post("/api/invites/preview/", {"token": token}, "json").json() == {
        "lab_name": "Lab X",
        "role": "viewer",
        "email": "invitee@example.com",
    }
    resp = api(invitee).post(CREATE, {"token": token}, "json")
    assert resp.status_code == 200
    assert resp.json()["my_role"] == "viewer" and "view_lab" in resp.json()["my_permissions"]
    assert LabMembership.objects.for_lab(lab).get(user=invitee).role == LabRole.VIEWER
    assert events(AuditAction.MEMBERSHIP_INVITE_ACCEPTED).filter(actor=invitee).count() == 1


def test_expired_invite_is_rejected(setup):
    lab, pi, invitee = setup
    data, token = send_invite(lab, pi)
    Invite.objects.for_lab(lab).filter(pk=data["id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert api(invitee).post(CREATE, {"token": token}, "json").status_code == 404
    assert api().post("/api/invites/preview/", {"token": token}, "json").status_code == 404
    assert not LabMembership.objects.for_lab(lab).filter(user=invitee).exists()


def test_wrong_email_is_rejected(setup, make_user, verify_email):
    lab, pi, _ = setup
    _, token = send_invite(lab, pi)
    other = make_user(email="other@example.com")
    verify_email(other)
    assert api(other).post(CREATE, {"token": token}, "json").status_code == 403
    assert not LabMembership.objects.for_lab(lab).filter(user=other).exists()
    assert Invite.objects.for_lab(lab).get().accepted_at is None


def test_unverified_email_is_rejected(setup, make_user, verify_email):
    lab, pi, _ = setup
    _, token = send_invite(lab, pi, email="fresh@example.com")
    fresh = make_user(email="fresh@example.com")
    verify_email(fresh, verified=False)
    assert api(fresh).post(CREATE, {"token": token}, "json").status_code == 403
    # No address on file at all is the same thing.
    nobody = make_user(email="Fresh2@example.com")
    _, token2 = send_invite(lab, pi, email="fresh2@example.com")
    assert api(nobody).post(CREATE, {"token": token2}, "json").status_code == 403
    assert LabMembership.objects.for_lab(lab).count() == 1


def test_reuse_after_accept_is_rejected(setup, make_user, verify_email):
    lab, pi, invitee = setup
    _, token = send_invite(lab, pi)
    assert api(invitee).post(CREATE, {"token": token}, "json").status_code == 200
    assert api(invitee).post(CREATE, {"token": token}, "json").status_code == 404
    assert api().post("/api/invites/preview/", {"token": token}, "json").status_code == 404
    assert LabMembership.objects.for_lab(lab).filter(user=invitee).count() == 1


def test_revoked_invite_is_rejected(setup):
    lab, pi, invitee = setup
    data, token = send_invite(lab, pi)
    assert api(pi).delete(f"/api/labs/{lab.pk}/invites/{data['id']}/").status_code == 204
    assert events(AuditAction.MEMBERSHIP_INVITE_REVOKED).filter(actor=pi).count() == 1
    assert api(invitee).post(CREATE, {"token": token}, "json").status_code == 404
    assert api(pi).get(f"/api/labs/{lab.pk}/invites/").json() == []
    # A fresh invite to the same address is allowed again once the old one is revoked.
    send_invite(lab, pi)


def test_unknown_token_and_duplicate_open_invite(setup):
    lab, pi, invitee = setup
    assert api(invitee).post(CREATE, {"token": "nope"}, "json").status_code == 404
    send_invite(lab, pi)
    resp = api(pi).post(
        f"/api/labs/{lab.pk}/invites/", {"email": "Invitee@example.com", "role": "member"}, "json"
    )
    assert resp.status_code == 400


def test_only_a_pi_can_invite_a_pi(setup, make_user, join):
    lab, pi, _ = setup
    admin = make_user()
    join(admin, lab, LabRole.LAB_ADMIN)
    body = {"email": "x@example.com", "role": "pi"}
    assert api(admin).post(f"/api/labs/{lab.pk}/invites/", body, "json").status_code == 403
    assert api(pi).post(f"/api/labs/{lab.pk}/invites/", body, "json").status_code == 201


def test_member_role_change_and_removal(setup, make_user, join, make_project):
    lab, pi, _ = setup
    member = make_user()
    mship = join(member, lab, LabRole.MEMBER)
    project = make_project(lab)
    from projects.models import ProjectMembership

    ProjectMembership.objects.create(lab=lab, project=project, user=member, role="lead")
    url = f"/api/labs/{lab.pk}/members/{mship.pk}/"
    assert api(pi).patch(url, {"role": "viewer"}, "json").json()["role"] == "viewer"
    assert events(AuditAction.MEMBERSHIP_ROLE_CHANGED).count() == 1
    assert api(pi).delete(url).status_code == 204
    assert events(AuditAction.MEMBERSHIP_REMOVED).count() == 1
    assert not ProjectMembership.objects.for_lab(lab).filter(user=member).exists()


def test_a_lab_keeps_its_last_pi_and_only_pis_touch_pis(setup, make_user, join):
    lab, pi, _ = setup
    pi_ms = LabMembership.objects.for_lab(lab).get(user=pi)
    url = f"/api/labs/{lab.pk}/members/{pi_ms.pk}/"
    assert api(pi).patch(url, {"role": "member"}, "json").status_code == 400
    assert api(pi).delete(url).status_code == 400
    admin = make_user()
    join(admin, lab, LabRole.LAB_ADMIN)
    assert api(admin).patch(url, {"role": "member"}, "json").status_code == 403
    assert api(admin).delete(url).status_code == 403
    second = make_user()
    join(second, lab, LabRole.PI)
    assert api(pi).patch(url, {"role": "member"}, "json").status_code == 200


def test_create_lab_makes_creator_pi_on_placeholder_institution(make_user):
    user = make_user()
    resp = api(user).post("/api/labs/", {"name": "New"}, "json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["my_role"] == "pi" and "manage_billing" in data["my_permissions"]
    assert "PLACEHOLDER" in data["institution"]["name"]
    assert Lab.objects.get(pk=data["id"]).created_by == user
    assert events(AuditAction.LAB_CREATED).filter(actor=user).count() == 1
    listed = api(user).get("/api/labs/").json()
    assert [lab["id"] for lab in listed] == [data["id"]]
