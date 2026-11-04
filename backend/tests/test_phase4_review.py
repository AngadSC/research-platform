"""Regression tests for the Phase 4 security review (D49, D50). Each fails on the old code."""

import re
import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.functional import SimpleLazyObject
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm, can, forget, lab_role, users_with
from labs.models import LabMembership, LabRole
from projects.models import ProjectMembership, ProjectRole, Task
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db
BACKEND = Path(__file__).resolve().parents[1]


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("L")
    project = make_project(lab)
    users = {}
    for name, role in (("member", LabRole.MEMBER), ("viewer", LabRole.VIEWER)):
        users[name] = make_user()
        join(users[name], lab, role)
    for name, prole in (("lead", ProjectRole.LEAD), ("contrib", ProjectRole.CONTRIBUTOR)):
        users[name] = make_user()
        join(users[name], lab, LabRole.MEMBER)
        ProjectMembership.objects.create(lab=lab, project=project, user=users[name], role=prole)
    users["pi"] = make_user()
    join(users["pi"], lab, LabRole.PI)
    return lab, project, users


# ---- 1: project perms exist only on project objects; the ethics mapping only on ethics


def test_project_perms_denied_on_a_non_ethics_lab_object(world):
    lab, _, u = world
    membership = LabMembership.objects.for_lab(lab).get(user=u["member"])
    assert not can(u["member"], Perm.EDIT_CONTENT, membership)
    assert not can(u["viewer"], Perm.VIEW_PROJECT, membership)
    assert not users_with(Perm.EDIT_CONTENT, membership).exists()


def test_ethics_domain_object_still_maps_to_ethics_perms(world, monkeypatch):
    lab, _, u = world
    membership = LabMembership.objects.for_lab(lab).get(user=u["member"])
    monkeypatch.setattr(LabMembership, "permission_domain", "ethics")
    assert can(u["member"], Perm.EDIT_CONTENT, membership)  # member holds edit_ethics
    assert not can(u["viewer"], Perm.EDIT_CONTENT, membership)
    assert can(u["viewer"], Perm.VIEW_PROJECT, membership)  # view_ethics
    assert u["member"] in users_with(Perm.EDIT_CONTENT, membership)


# ---- 2: lab-level perms on a project's object need visibility of the project


def test_lab_perm_on_project_object_needs_project_visibility(world):
    lab, project, u = world
    task = Task.objects.create(lab=lab, project=project, title="t", created_by=u["lead"])
    assert not can(u["member"], Perm.VIEW_LAB, task)  # member not on the project
    assert not can(u["member"], Perm.VIEW_LAB, project)
    assert can(u["contrib"], Perm.VIEW_LAB, task)
    assert can(u["pi"], Perm.VIEW_LAB, task)  # implicit lead
    assert u["member"] not in users_with(Perm.VIEW_LAB, task)
    assert {u["contrib"], u["pi"]} <= set(users_with(Perm.VIEW_LAB, task))


# ---- 3 / D49: views and serializers never call for_lab()


def test_for_lab_is_not_used_in_views_or_serializers():
    pattern = re.compile(r"\.for_lab\(")
    offenders = [
        str(p.relative_to(BACKEND))
        for p in BACKEND.rglob("*.py")
        if p.name in ("views.py", "serializers.py")
        and ".venv" not in p.parts
        and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# ---- 4 / D50: ran_by, decided_by, controlled_by default to the actor


def _analysis_body(**kw):
    return {
        "title": "A",
        "code_repo_url": "https://example.com/r.git",
        "code_commit": "abc1234",
        **kw,
    }


def test_provenance_user_fields_default_to_actor_and_need_edit_project(world):
    lab, project, u = world
    kw = {"lab_id": lab.pk, "project_id": project.pk}
    base = reverse("provenance:analysis-list", kwargs=kw)
    # a contributor cannot name someone else
    resp = api(u["contrib"]).post(base, _analysis_body(ran_by=str(u["lead"].pk)), format="json")
    assert resp.status_code == 403
    # default is the actor
    resp = api(u["contrib"]).post(base, _analysis_body(), format="json")
    assert resp.status_code == 201 and resp.json()["ran_by"]["id"] == str(u["contrib"].pk)
    # a lead may name someone else who can view the project
    resp = api(u["lead"]).post(base, _analysis_body(ran_by=str(u["contrib"].pk)), format="json")
    assert resp.status_code == 201 and resp.json()["ran_by"]["id"] == str(u["contrib"].pk)
    # dataset: controlled_by defaults to the actor; a contributor cannot name another
    ds = reverse("provenance:dataset-list", kwargs=kw)
    body = {"name": "d", "version_label": "v1", "location_text": "x"}
    resp = api(u["contrib"]).post(ds, {**body, "controlled_by": str(u["lead"].pk)}, format="json")
    assert resp.status_code == 403
    assert api(u["contrib"]).post(ds, body, format="json").status_code == 201
    assert DatasetRecord.objects.for_lab(lab).get().controlled_by == u["contrib"]


# ---- 5 / D50: oversize uploads are refused from Content-Length; uploads are throttled


def _upload_url(lab, project):
    return reverse("documents:attachment-list", kwargs={"lab_id": lab.pk, "project_id": project.pk})


def test_oversize_upload_rejected_before_body_is_read(world, settings, monkeypatch):
    lab, project, u = world
    settings.ATTACHMENT_MAX_BYTES = 1000

    def boom(self, *a, **k):
        raise AssertionError("body was parsed")

    monkeypatch.setattr("rest_framework.request.Request._load_data_and_files", boom)
    monkeypatch.setattr("django.http.request.HttpRequest._load_post_and_files", boom)
    resp = api(u["contrib"]).post(
        _upload_url(lab, project),
        data=b"x" * 200_000,
        content_type="multipart/form-data; boundary=b",
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]


def test_uploads_are_throttled(world, monkeypatch):
    lab, project, u = world
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "uploads", "2/hour")
    client = api(u["contrib"])

    def post():
        file = SimpleUploadedFile("a.pdf", b"%PDF-1", content_type="application/pdf")
        body = {"file": file, "acknowledged_notice": "true"}
        return client.post(_upload_url(lab, project), body, format="multipart").status_code

    assert [post() for _ in range(3)] == [201, 201, 429]


# ---- 6: forget() works on a lazy request.user


def test_forget_clears_cache_on_a_lazy_user(world):
    lab, _, u = world
    lazy = SimpleLazyObject(lambda: u["member"])
    assert lab_role(lazy, lab) == LabRole.MEMBER
    LabMembership.objects.for_lab(lab).filter(user=u["member"]).update(role=LabRole.VIEWER)
    assert lab_role(lazy, lab) == LabRole.MEMBER  # still cached
    forget(lazy)
    assert lab_role(lazy, lab) == LabRole.VIEWER
    LabMembership.objects.for_lab(lab).filter(user=u["member"]).update(role=LabRole.PI)
    forget(u["member"])  # also fine unwrapped
    assert lab_role(u["member"], lab) == LabRole.PI


# ---- 7 / D50: lab creation and invites are capped


def test_lab_creation_is_throttled(make_user):
    client = api(make_user())
    codes = [client.post("/api/labs/", {"name": f"Lab {i}"}, format="json") for i in range(6)]
    assert [r.status_code for r in codes] == [201] * 5 + [429]
    assert client.get("/api/labs/").status_code == 200  # listing is not throttled


def test_invites_per_lab_per_day_are_capped(world, settings):
    lab, _, u = world
    settings.INVITES_PER_LAB_PER_DAY = 3
    client = api(u["pi"])
    url = f"/api/labs/{lab.pk}/invites/"
    resps = [
        client.post(url, {"email": f"n{i}@example.com", "role": "member"}, format="json")
        for i in range(4)
    ]
    assert [r.status_code for r in resps] == [201, 201, 201, 429]
    assert "too many invites" in resps[3].json()["detail"]


# ---- 8 / D49: SECRET_KEY is never the placeholder

SETTINGS = BACKEND / "config" / "settings.py"
PLACEHOLDERS = ("replace-with", "django-insecure")


def _settings(monkeypatch, tmp_path, *, debug, key):
    monkeypatch.setenv("DEBUG", debug)
    monkeypatch.setenv("DEV_SECRET_KEY_FILE", str(tmp_path / ".dev_secret_key"))
    monkeypatch.setenv("SECRET_KEY", key)
    return runpy.run_path(str(SETTINGS))


@pytest.mark.parametrize("key", ["", "replace-with-a-long-random-string", "django-insecure-x"])
def test_debug_generates_and_persists_a_dev_key(monkeypatch, tmp_path, key):
    first = _settings(monkeypatch, tmp_path, debug="True", key=key)["SECRET_KEY"]
    assert first and not first.startswith(PLACEHOLDERS)
    assert (tmp_path / ".dev_secret_key").read_text() == first
    assert _settings(monkeypatch, tmp_path, debug="True", key=key)["SECRET_KEY"] == first
    assert not list(tmp_path.glob("*.tmp"))


def test_real_key_is_kept_and_placeholder_refused_without_debug(monkeypatch, tmp_path):
    assert _settings(monkeypatch, tmp_path, debug="True", key="s3cret")["SECRET_KEY"] == "s3cret"
    for key in ("", "replace-with-x", "django-insecure-x"):
        with pytest.raises(ImproperlyConfigured):
            _settings(monkeypatch, tmp_path, debug="False", key=key)
    assert not (tmp_path / ".dev_secret_key").exists()
