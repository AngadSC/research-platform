"""Lab notebooks (D330): personal and per project, lockable, exportable. Who reaches each
endpoint is in tests/test_permission_matrix.py."""

import json

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditEvent
from labs.models import LabRole, NotebookEntry
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Wet Lab")
    ann, ben = make_user(), make_user()
    for u in (ann, ben):
        join(u, lab, LabRole.MEMBER)
    project = make_project(lab, "Assay development")
    for u in (ann, ben):
        ProjectMembership.objects.create(
            lab=lab, project=project, user=u, role=ProjectRole.CONTRIBUTOR
        )
    return lab, ann, ben, project


def mine(lab, *tail):
    return reverse("labs:notebook-mine", kwargs={"lab_id": lab.pk}) + "".join(tail)


def shared(lab, project, name="notebook-project", **kw):
    return reverse(f"labs:{name}", kwargs={"lab_id": lab.pk, "project_id": project.pk, **kw})


def test_a_personal_notebook_is_only_its_authors(world):
    lab, ann, ben, _ = world
    r = api(ann).post(
        mine(lab), {"title": "Western blot, day 1", "body": "Ran gel at 120 V."}, "json"
    )
    assert r.status_code == 201, r.content
    assert [e["title"] for e in api(ann).get(mine(lab)).json()] == ["Western blot, day 1"]
    assert api(ben).get(mine(lab)).json() == []
    one = reverse("labs:notebook-mine-entry", kwargs={"lab_id": lab.pk, "entry_id": r.json()["id"]})
    assert api(ben).patch(one, {"title": "x"}, "json").status_code == 404
    assert api(ann).patch(one, {"body": "Ran gel at 100 V."}, "json").status_code == 200


def test_a_project_notebook_is_shared_with_the_project(world):
    lab, ann, ben, project = world
    r = api(ann).post(shared(lab, project), {"title": "Buffer batch 3"}, "json")
    assert r.status_code == 201
    assert len(api(ben).get(shared(lab, project)).json()) == 1
    assert api(ann).get(mine(lab)).json() == []  # not in anyone's personal notebook
    other = reverse(
        "labs:notebook-project-entry",
        kwargs={"lab_id": lab.pk, "project_id": project.pk, "pentry_id": r.json()["id"]},
    )
    assert api(ben).patch(other, {"title": "Mine now"}, "json").status_code == 403  # not the author
    assert api(ann).patch(other, {"title": "Buffer batch 3b"}, "json").status_code == 200


def test_a_locked_entry_cannot_change_or_go(world):
    lab, ann, _, project = world
    entry = api(ann).post(shared(lab, project), {"title": "Plate 4 read"}, "json").json()
    kw = {"entry_id": entry["id"]}
    lock = shared(lab, project, "notebook-project-lock", pentry_id=entry["id"])
    r = api(ann).post(lock)
    assert r.status_code == 200 and r.json()["locked_at"] and r.json()["can_edit"] is False
    one = shared(lab, project, "notebook-project-entry", pentry_id=entry["id"])
    assert api(ann).patch(one, {"title": "Changed"}, "json").status_code == 400
    assert api(ann).delete(one).status_code == 400
    assert api(ann).post(lock).status_code == 400  # already locked
    assert NotebookEntry.objects.for_lab(lab).get(pk=entry["id"]).title == "Plate 4 read"
    assert AuditEvent.objects.filter(action="notebook.locked").count() == 1
    del kw


def test_exports_in_three_formats_escape_what_they_hold(world):
    lab, ann, _, project = world
    api(ann).post(
        shared(lab, project),
        {
            "title": "Run <b>1</b>",
            "body": "<script>alert(1)</script>\n10 mL buffer",
            "entry_date": "2026-03-02",
        },
        "json",
    )
    url = shared(lab, project, "notebook-project-export")
    md = api(ann).get(url + "?fmt=md")
    assert md.status_code == 200 and md["Content-Type"].startswith("text/markdown")
    assert "## Run <b>1</b>" in md.content.decode() and "10 mL buffer" in md.content.decode()
    html = api(ann).get(url + "?fmt=html").content.decode()
    assert "<script>" not in html and "&lt;script&gt;" in html
    data = json.loads(api(ann).get(url + "?fmt=json").content)
    assert data["entries"][0]["date"] == "2026-03-02"
    assert api(ann).get(url + "?fmt=docx").status_code == 400
    assert api(ann).get(url + "?from=2026-04-01&fmt=json").json()["entries"] == []
    assert AuditEvent.objects.filter(action="notebook.exported").count() >= 4


def test_my_notebook_exports_only_my_entries(world):
    lab, ann, ben, _ = world
    api(ann).post(mine(lab), {"title": "Ann's note"}, "json")
    api(ben).post(mine(lab), {"title": "Ben's note"}, "json")
    out = api(ann).get(mine(lab, "export/") + "?fmt=md").content.decode()
    assert "Ann's note" in out and "Ben's note" not in out


def test_a_blank_title_is_refused(world):
    lab, ann, *_ = world
    assert api(ann).post(mine(lab), {"title": "   "}, "json").status_code == 400
