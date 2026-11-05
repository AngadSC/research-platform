"""Regression tests for the Phase 2 security review (D38 to D41). Each fails on the old code."""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
from django.apps import apps
from django.core import mail
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.permissions import Perm, can, project_role, require, users_with
from core.tenancy import LabScopedModel, UnscopedQueryError
from labs import services
from labs.models import Invite, LabMembership, LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parents[1]


def api(user=None):
    client = APIClient()
    if user:
        client.force_login(user)
    return client


def token_from_mail():
    return mail.outbox[-1].body.split("/invite/")[1].split()[0]


def invite_via_api(inviter, lab, email, role):
    with TestCase.captureOnCommitCallbacks(execute=True):
        resp = api(inviter).post(
            f"/api/labs/{lab.pk}/invites/", {"email": email, "role": role}, "json"
        )
    assert resp.status_code == 201, resp.content
    return resp.json()["id"]


@pytest.fixture
def lab_pi(make_lab, make_user, join):
    lab, pi = make_lab("L"), make_user()
    join(pi, lab, LabRole.PI)
    return lab, pi


# ---- 1 / D39: soft-deleted projects are invisible to every check


def test_soft_deleted_project_denies_everything(lab_pi, make_user, join, make_project):
    lab, pi = lab_pi
    lead = make_user()
    join(lead, lab, LabRole.MEMBER)
    project = make_project(lab)
    membership = ProjectMembership.objects.create(
        lab=lab, project=project, user=lead, role=ProjectRole.LEAD
    )
    assert can(lead, Perm.EXPORT, project)
    project.deleted_at = timezone.now()
    project.save()
    lead = type(lead).objects.get(pk=lead.pk)
    assert project_role(lead, project) is None
    assert project_role(pi, project) is None
    for user in (lead, pi):
        for perm in (Perm.EXPORT, Perm.EDIT_CONTENT, Perm.VIEW_PROJECT, Perm.DELETE_PROJECT):
            assert not can(user, perm, project)
            assert not can(user, perm, membership)  # a child of the deleted project
    with pytest.raises(Http404):
        require(lead, Perm.EXPORT, project)
    assert not users_with(Perm.VIEW_PROJECT, project).exists()
    assert not users_with(Perm.EXPORT, membership).exists()


# ---- 2 / D40: invites die with their issuer's authority


def test_removed_admin_cannot_resurrect_via_own_invite(lab_pi, make_user, join, verify_email):
    lab, pi = lab_pi
    admin, alt = make_user(), make_user(email="alt@example.com")
    verify_email(alt)
    membership = join(admin, lab, LabRole.LAB_ADMIN)
    invite_via_api(admin, lab, "alt@example.com", "lab_admin")
    token = token_from_mail()
    assert api(pi).delete(f"/api/labs/{lab.pk}/members/{membership.pk}/").status_code == 204
    assert api(alt).post("/api/invites/accept/", {"token": token}, "json").status_code == 404
    assert not LabMembership.objects.for_lab(lab).filter(user=alt).exists()
    assert Invite.objects.for_lab(lab).get(email="alt@example.com").revoked_at is not None


def test_demotion_revokes_open_invites_they_can_no_longer_issue(lab_pi, make_user, join):
    lab, pi = lab_pi
    admin = make_user()
    membership = join(admin, lab, LabRole.LAB_ADMIN)
    for i in range(2):
        Invite.issue(lab=lab, email=f"x{i}@example.com", role="member", invited_by=admin)
    services.change_role(membership=membership, by=pi, role=LabRole.VIEWER)
    assert not Invite.objects.for_lab(lab).filter(revoked_at__isnull=True).exists()


def test_pi_demotion_keeps_member_invites_but_revokes_pi_invites(lab_pi, make_user, join):
    lab, pi = lab_pi
    pi2 = make_user()
    membership = join(pi2, lab, LabRole.PI)
    Invite.issue(lab=lab, email="m@example.com", role="member", invited_by=pi2)
    Invite.issue(lab=lab, email="p@example.com", role="pi", invited_by=pi2)
    services.change_role(membership=membership, by=pi, role=LabRole.LAB_ADMIN)
    open_ = Invite.objects.for_lab(lab).filter(revoked_at__isnull=True)
    assert [i.email for i in open_] == ["m@example.com"]


def test_accept_rechecks_inviter_authority(lab_pi, make_user, join, verify_email):
    lab, pi = lab_pi
    admin, viewer = make_user(), make_user(email="v@example.com")
    verify_email(viewer)
    join(admin, lab, LabRole.LAB_ADMIN)
    # An admin may not grant PI, even if such an invite row exists.
    _, token = Invite.issue(lab=lab, email="v@example.com", role="pi", invited_by=admin)
    assert api(viewer).post("/api/invites/accept/", {"token": token}, "json").status_code == 404
    Invite.objects.for_lab(lab).delete()
    # Demoted behind the service's back (no revoke ran): still refused.
    _, token = Invite.issue(lab=lab, email="v@example.com", role="member", invited_by=admin)
    LabMembership.objects.for_lab(lab).filter(user=admin).update(role=LabRole.VIEWER)
    assert api(viewer).post("/api/invites/accept/", {"token": token}, "json").status_code == 404


# ---- 3 / D41: settings fail closed


def run_py(code, **env):
    full = {k: v for k, v in os.environ.items() if k not in ("DEBUG", "SECRET_KEY")}
    full.update(env, DJANGO_SETTINGS_MODULE="config.settings")
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=full, capture_output=True, text=True
    )


@pytest.mark.parametrize(
    "env",
    [
        {},  # DEBUG defaults to off, no key
        {"SECRET_KEY": "replace-with-a-long-random-string"},  # the .env.example placeholder
        {"DEBUG": "False", "SECRET_KEY": "django-insecure-dev-only"},
    ],
)
def test_placeholder_secret_key_refused_when_debug_off(env):
    result = run_py("import config.settings", **env)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


PROD_KEYS = {"SECRET_KEY": "x" * 50, "INTEGRATION_ENCRYPTION_KEYS": "A" * 43 + "="}  # D63


def test_real_secret_key_accepted_and_debug_dev_key_still_works():
    assert run_py("import config.settings", DEBUG="False", **PROD_KEYS).returncode == 0
    assert run_py("import config.settings", DEBUG="True").returncode == 0


def test_settings_module_default_is_closed():
    code = "import config.settings as s; print(s.DEBUG)"
    assert run_py(code, **PROD_KEYS).stdout.strip() == "False"


# ---- 4 / D38: unresolvable owner is denied, never lab-level


def test_project_typed_object_without_owner_is_denied(lab_pi, make_user):
    lab, pi = lab_pi
    orphan = ProjectMembership(lab=lab, user=make_user())  # project unset: owner unresolvable
    for perm in (Perm.VIEW_PROJECT, Perm.EDIT_CONTENT, Perm.VIEW_ETHICS, Perm.EDIT_ETHICS):
        assert not can(pi, perm, orphan)
    with pytest.raises((Http404, PermissionDenied)):
        require(pi, Perm.VIEW_PROJECT, orphan)
    assert not users_with(Perm.VIEW_PROJECT, orphan).exists()


def test_undeclared_permission_domain_is_denied(lab_pi, make_user, make_project, monkeypatch):
    lab, pi = lab_pi
    member = ProjectMembership(lab=lab, project=make_project(lab), user=make_user())
    assert can(pi, Perm.VIEW_PROJECT, member)
    monkeypatch.setattr(ProjectMembership, "permission_domain", None)
    assert not can(pi, Perm.VIEW_PROJECT, member)
    assert not can(pi, Perm.VIEW_ETHICS, member)
    with pytest.raises(ImproperlyConfigured):
        ProjectMembership.objects.visible_to(pi, lab)


def test_every_lab_model_declares_a_consistent_domain():
    for model in apps.get_models():
        if issubclass(model, LabScopedModel):
            domain = model.permission_domain
            assert domain in ("project", "lab"), model
            assert (domain == "lab") == (model.project_path is None), model


# ---- 5: combinators and raw SQL cannot bypass the scope guard


def test_union_intersection_difference_need_scoped_operands(make_lab, make_user, join):
    a, b = make_lab("A"), make_lab("B")
    join(make_user(), a, LabRole.PI)
    join(make_user(), b, LabRole.PI)
    scoped = LabMembership.objects.for_lab(a)
    for op in ("union", "intersection", "difference"):
        with pytest.raises(UnscopedQueryError):
            list(getattr(scoped, op)(LabMembership.objects.all()))
        with pytest.raises(UnscopedQueryError):
            list(getattr(LabMembership.objects.all(), op)(scoped))
    ok = scoped.union(LabMembership.objects.for_lab(b))
    assert {m.lab_id for m in ok} == {a.pk, b.pk}  # explicitly scoped on both sides is fine


def test_raw_raises_on_scoped_managers(make_lab):
    lab = make_lab()
    with pytest.raises(UnscopedQueryError):
        list(LabMembership.objects.raw("select * from labs_labmembership"))
    with pytest.raises(UnscopedQueryError):
        list(LabMembership.objects.for_lab(lab).raw("select * from labs_labmembership"))


# ---- 6 / D41: /admin/ only in DEBUG


def test_admin_not_mounted_when_debug_off():
    code = "import django; django.setup()\nfrom django.urls import resolve; resolve('/admin/')"
    off = run_py(code, DEBUG="False", **PROD_KEYS)
    assert off.returncode != 0 and "Resolver404" in off.stderr
    assert run_py(code, DEBUG="True").returncode == 0


# ---- 7: header injection, mail after commit, throttle


def test_control_characters_rejected_in_lab_and_display_name(make_user):
    user = make_user()
    assert api(user).post("/api/labs/", {"name": "Evil\nBcc: x@y.z"}, "json").status_code == 400
    assert (
        api(user).post("/api/labs/", {"name": "Mid" + chr(0x2028) + "dle"}, "json").status_code
        == 400
    )
    assert api(user).patch("/api/me/", {"display_name": "a\rb"}, "json").status_code == 400
    assert api(user).patch("/api/me/", {"display_name": "Ada"}, "json").status_code == 200


def test_legacy_newline_name_does_not_500_or_strand_invite(lab_pi):
    lab, pi = lab_pi
    lab.name = "Evil\nBcc: x@y.z"  # stored before validation existed
    lab.save()
    client = api(pi)
    client.raise_request_exception = False
    with TestCase.captureOnCommitCallbacks(execute=True):
        resp = client.post(
            f"/api/labs/{lab.pk}/invites/", {"email": "v@example.com", "role": "member"}, "json"
        )
    assert resp.status_code == 201
    assert "\n" not in mail.outbox[-1].subject


def test_invite_mail_failure_after_commit_keeps_invite(lab_pi):
    lab, pi = lab_pi
    client = api(pi)
    client.raise_request_exception = False
    with mock.patch("core.email._render_and_send", side_effect=OSError("smtp down")):
        with TestCase.captureOnCommitCallbacks(execute=True):
            resp = client.post(
                f"/api/labs/{lab.pk}/invites/", {"email": "v@example.com", "role": "member"}, "json"
            )
    assert resp.status_code == 201
    assert Invite.objects.for_lab(lab).filter(email="v@example.com").exists()


def test_invite_mail_not_sent_before_commit(lab_pi):
    lab, pi = lab_pi
    with TestCase.captureOnCommitCallbacks(execute=False) as callbacks:
        api(pi).post(
            f"/api/labs/{lab.pk}/invites/", {"email": "v@example.com", "role": "member"}, "json"
        )
    assert mail.outbox == [] and len(callbacks) == 1


def test_invite_creation_is_throttled(lab_pi):
    lab, pi = lab_pi
    client = api(pi)
    codes = [
        client.post(
            f"/api/labs/{lab.pk}/invites/", {"email": f"n{i}@example.com", "role": "member"}, "json"
        ).status_code
        for i in range(31)
    ]
    assert codes[:30] == [201] * 30 and codes[30] == 429
    assert client.get(f"/api/labs/{lab.pk}/invites/").status_code == 200  # listing is not throttled


# ---- 8 / D41: shared cache


def test_cache_is_redis_backed_by_default():
    code = (
        "import config.settings as s; c = s.CACHES['default']; print(c['BACKEND'], c['LOCATION'])"
    )
    out = run_py(code, DEBUG="True").stdout.split()
    assert out[0] == "django.core.cache.backends.redis.RedisCache"
    assert out[1].startswith("redis://")


# ---- audit schema


def test_audit_events_schema_declares_filters():
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    op = schema["paths"]["/api/labs/{lab_id}/audit-events/"]["get"]
    names = {p["name"] for p in op["parameters"]}
    assert {
        "actor",
        "action",
        "target_type",
        "target_id",
        "date_from",
        "date_to",
        "cursor",
    } <= names
