"""Walkthrough fixes of 13 Nov: review step, archived projects, recents, export."""

import pytest
from django.urls import reverse

from core.recents import prune_recents
from projects.models import ProjectStatus
from provenance.models import ReviewItem
from provenance.tests.test_provenance import World

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    return World(make_lab, make_user, make_project, join)


def kw(w):
    return {"lab_id": w.lab.pk, "project_id": w.project.pk}


def test_review_cannot_be_marked_done_while_an_item_is_waiting(w):
    ReviewItem.objects.create(lab=w.lab, project=w.project, title="Sign-off", created_by=w.pi)
    mark = reverse("provenance:workflow-progress", kwargs=kw(w))
    resp = w.client().patch(mark, {"stage": "review", "done": True}, format="json")
    assert resp.status_code == 400 and "Sign-off" in resp.content.decode()
    assert w.client().patch(mark, {"stage": "data", "done": True}, format="json").status_code == 200


def test_archived_project_refuses_new_tasks_and_documents(w):
    w.project.status = ProjectStatus.ARCHIVED
    w.project.save()
    tasks = reverse("projects:task-list", kwargs=kw(w))
    resp = w.client().post(tasks, {"title": "x"}, format="json")
    assert resp.status_code == 400 and "archived" in resp.content.decode()
    docs = reverse("documents:document-list", kwargs=kw(w))
    assert w.client().post(docs, {"title": "x"}, format="json").status_code == 400


def test_my_tasks_leaves_out_archived_projects(w):
    w.client().post(
        reverse("projects:task-list", kwargs=kw(w)),
        {"title": "t", "assignee": str(w.pi.pk)},
        format="json",
    )
    mine = reverse("projects:my-tasks", kwargs={"lab_id": w.lab.pk})
    assert len(w.client().get(mine).json()) == 1
    w.project.status = ProjectStatus.ARCHIVED
    w.project.save()
    assert w.client().get(mine).json() == []


def test_export_has_members_without_emails_and_ethics(w):
    w.member("contributor")
    body = w.client().post(w.url("export"), {}, format="json").json()
    assert body["members"] and set(body["members"][0]) == {"name", "role"}
    assert body["ethics_approvals"] == []


def test_recents_of_deleted_projects_are_dropped(w):
    live = f"/labs/{w.lab.pk}/projects/{w.project.pk}/overview"
    gone = f"/labs/{w.lab.pk}/projects/{w.other.pk}/overview"
    w.other.deleted_at = "2030-01-01T00:00:00Z"
    w.other.save()
    at = "2030-01-01T00:00:00Z"
    w.pi.preferences = {
        "recents": [
            {"url": live, "label": "A", "kind": "project", "at": at},
            {"url": gone, "label": "B", "kind": "project", "at": at},
        ]
    }
    w.pi.save()
    prune_recents(w.pi)
    w.pi.refresh_from_db()
    assert [r["label"] for r in w.pi.preferences["recents"]] == ["A"]
