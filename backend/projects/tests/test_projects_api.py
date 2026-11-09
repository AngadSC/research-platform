"""Phase 3 projects, members, deadlines and tasks through the API."""

import uuid

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def lab(make_lab):
    return make_lab("Lab")


@pytest.fixture
def people(lab, make_user, join):
    """pi, admin, lead (project lead), contrib, lview (lab viewer) and a project P."""
    out = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("admin", LabRole.LAB_ADMIN),
        ("lead", LabRole.MEMBER),
        ("contrib", LabRole.MEMBER),
        ("outside", LabRole.MEMBER),  # lab member, not on P
        ("lview", LabRole.VIEWER),
    ]:
        out[name] = make_user()
        join(out[name], lab, role)
    project = Project.objects.create(lab=lab, name="P", created_by=out["pi"])
    for name, role in [
        ("lead", ProjectRole.LEAD),
        ("contrib", ProjectRole.CONTRIBUTOR),
        ("lview", ProjectRole.CONTRIBUTOR),
    ]:
        ProjectMembership.objects.create(lab=lab, project=project, user=out[name], role=role)
    out["project"] = project
    return out


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def base(lab):
    return f"/api/labs/{lab.pk}"


def test_assignee_outside_project_is_rejected(lab, people):
    url = f"{base(lab)}/projects/{people['project'].pk}/tasks/"
    for who in ("outside", "lview", "contrib"):
        resp = api(people["lead"]).post(
            url, {"title": "T", "assignee": str(people[who].pk)}, "json"
        )
        assert resp.status_code == (201 if who == "contrib" else 400), who
    assert (
        Task.objects.for_lab(lab).count() == 1
    )  # only contrib can edit content (a lab viewer is capped at viewer)
    # a stranger from no lab at all, and an unknown id: same 400
    bad = str(uuid.UUID(int=1))
    assert api(people["lead"]).post(url, {"title": "T", "assignee": bad}, "json").status_code == 400
    # changing the assignee through PATCH is validated too
    task = Task.objects.for_lab(lab).first()
    resp = api(people["lead"]).patch(
        f"{base(lab)}/tasks/{task.pk}/", {"assignee": str(people["outside"].pk)}, "json"
    )
    assert resp.status_code == 400


def test_soft_deleted_project_404s_and_hides_tasks(lab, people):
    project = people["project"]
    task = Task.objects.create(lab=lab, project=project, title="T", created_by=people["pi"])
    resp = api(people["pi"]).delete(f"{base(lab)}/projects/{project.pk}/")
    assert resp.status_code == 204
    project.refresh_from_db()
    assert project.deleted_at is not None  # soft: the row is still there
    assert Task.objects.for_lab(lab).filter(pk=task.pk).exists()
    for who in ("pi", "lead"):
        c = api(people[who])
        assert c.get(f"{base(lab)}/projects/{project.pk}/").status_code == 404
        assert c.get(f"{base(lab)}/projects/{project.pk}/tasks/").status_code == 404
        assert c.get(f"{base(lab)}/tasks/{task.pk}/").status_code == 404
        assert c.patch(f"{base(lab)}/tasks/{task.pk}/", {"title": "x"}, "json").status_code == 404
        assert c.get(f"{base(lab)}/projects/").json() == []
    assert one(AuditAction.PROJECT_DELETED).target_id == project.pk


def one(action):
    qs = AuditEvent.objects.filter(action=action)
    assert qs.count() == 1
    return qs.get()


def test_lab_viewer_cannot_edit(lab, people):
    project, c = people["project"], api(people["lview"])
    assert c.get(f"{base(lab)}/projects/{project.pk}/").status_code == 200
    assert c.post(f"{base(lab)}/projects/", {"name": "N"}, "json").status_code == 403
    assert (
        c.post(f"{base(lab)}/projects/{project.pk}/tasks/", {"title": "T"}, "json").status_code
        == 403
    )
    assert c.patch(f"{base(lab)}/projects/{project.pk}/", {"name": "x"}, "json").status_code == 403
    body = c.get(f"{base(lab)}/projects/{project.pk}/").json()
    assert body["my_project_role"] == "viewer"  # contributor row, capped (D19)
    assert body["my_permissions"] == ["view_project"]


def test_pi_and_admin_are_implicit_leads(lab, people):
    project = people["project"]
    for who in ("pi", "admin"):
        c = api(people[who])
        body = c.get(f"{base(lab)}/projects/{project.pk}/").json()  # no ProjectMembership row
        assert body["my_project_role"] == "lead"
        assert {"edit_project", "manage_project_members", "export", "delete_project"} <= set(
            body["my_permissions"]
        )
        assert (
            c.patch(f"{base(lab)}/projects/{project.pk}/", {"status": "active"}, "json").status_code
            == 200
        )
        assert (
            c.post(
                f"{base(lab)}/projects/{project.pk}/deadlines/",
                {"title": "D", "due_date": "2030-01-01"},
                "json",
            ).status_code
            == 201
        )
    lead = api(people["lead"]).get(f"{base(lab)}/projects/{project.pk}/").json()
    assert "delete_project" not in lead["my_permissions"]  # D28


def test_project_list_shows_only_visible_and_creator_becomes_lead(lab, people):
    Project.objects.create(lab=lab, name="Hidden", created_by=people["pi"])

    def names(who):
        return [p["name"] for p in api(people[who]).get(f"{base(lab)}/projects/").json()]

    assert names("lead") == ["P"] and sorted(names("pi")) == ["Hidden", "P"]
    assert names("outside") == []
    resp = api(people["outside"]).post(f"{base(lab)}/projects/", {"name": "Mine"}, "json")
    assert resp.status_code == 201 and resp.json()["my_project_role"] == "lead"
    assert "Mine" in names("outside")
    created = one(AuditAction.PROJECT_CREATED)
    assert created.actor == people["outside"] and created.lab == lab


def test_member_audit_and_rules(lab, people, make_user):
    project, c = people["project"], api(people["lead"])
    url = f"{base(lab)}/projects/{project.pk}/members/"
    resp = c.post(url, {"user": str(people["outside"].pk), "role": "viewer"}, "json")
    assert resp.status_code == 201
    mid = resp.json()["id"]
    assert (
        c.post(url, {"user": str(people["outside"].pk), "role": "viewer"}, "json").status_code
        == 400
    )
    stranger = make_user()  # not in the lab
    assert c.post(url, {"user": str(stranger.pk), "role": "viewer"}, "json").status_code == 400
    assert (
        c.patch(f"{base(lab)}/project-members/{mid}/", {"role": "contributor"}, "json").status_code
        == 200
    )
    assert c.delete(f"{base(lab)}/project-members/{mid}/").status_code == 204
    for action in (
        AuditAction.PROJECT_MEMBERSHIP_ADDED,
        AuditAction.PROJECT_MEMBERSHIP_ROLE_CHANGED,
        AuditAction.PROJECT_MEMBERSHIP_REMOVED,
    ):
        assert one(action).project_id == project.pk


def test_task_filters_reorder_and_delete_audit(lab, people):
    project, c = people["project"], api(people["contrib"])
    url = f"{base(lab)}/projects/{project.pk}/tasks/"
    ids = [c.post(url, {"title": t}, "json").json()["id"] for t in "abc"]
    ids.append(
        c.post(
            url, {"title": "d", "status": "done", "assignee": str(people["lead"].pk)}, "json"
        ).json()["id"]
    )

    def titles(q=""):
        return [t["title"] for t in c.get(url + q).json()]

    def detail(i):
        return f"{base(lab)}/tasks/{ids[i]}/"

    assert titles("?status=todo") == ["a", "b", "c"]
    assert titles(f"?assignee={people['lead'].pk}") == ["d"]
    assert c.get(url + "?status=nope").status_code == 400
    # move c to the top of todo, then to the done column at index 0
    assert c.patch(detail(2), {"position": 0}, "json").status_code == 200
    assert titles("?status=todo") == ["c", "a", "b"]
    assert c.patch(detail(0), {"status": "done", "position": 0}, "json").status_code == 200
    assert titles("?status=done") == ["a", "d"] and titles("?status=todo") == ["c", "b"]
    assert c.delete(detail(1)).status_code == 204
    assert one(AuditAction.TASK_DELETED).target_id.hex == ids[1].replace("-", "")


def test_deadline_delete_audit_and_project_update_audit(lab, people):
    project, c = people["project"], api(people["lead"])
    dl = c.post(
        f"{base(lab)}/projects/{project.pk}/deadlines/",
        {"title": "D", "due_date": "2030-01-01"},
        "json",
    ).json()
    assert c.patch(f"{base(lab)}/deadlines/{dl['id']}/", {"done": True}, "json").json()["done"]
    assert c.delete(f"{base(lab)}/deadlines/{dl['id']}/").status_code == 204
    assert one(AuditAction.DEADLINE_DELETED).project_id == project.pk
    c.patch(f"{base(lab)}/projects/{project.pk}/", {"status": "active"}, "json")
    assert one(AuditAction.PROJECT_UPDATED).metadata == {"fields": ["status"]}


def test_new_projects_take_the_least_used_colour(lab, people):
    c = api(people["pi"])
    url = f"{base(lab)}/projects/"
    first = c.post(url, {"name": "A"}, "json").json()  # P already holds the first colour
    assert first["color"] == "orange"
    assert c.post(url, {"name": "B", "color": "red"}, "json").json()["color"] == "red"
    assert c.post(url, {"name": "C"}, "json").json()["color"] == "green"
    assert c.post(url, {"name": "D", "color": "#ff0000"}, "json").status_code == 400
    resp = c.patch(f"{url}{first['id']}/", {"color": "teal"}, "json")
    assert resp.json()["color"] == "teal"


def test_migration_spreads_colours_within_each_lab(lab, people, make_lab):
    from importlib import import_module

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    second = Project.objects.create(lab=lab, name="Q", created_by=people["pi"])
    elsewhere = Project.objects.create(lab=make_lab("B"), name="R", created_by=people["pi"])
    node = ("projects", "0007_project_color")
    apps = MigrationExecutor(connection).loader.project_state(node).apps
    import_module("projects.migrations.0007_project_color").assign_colors(apps, None)
    for project in (people["project"], second, elsewhere):
        project.refresh_from_db()
    assert people["project"].color == "blue"
    assert second.color == "orange"
    assert elsewhere.color == "blue"
