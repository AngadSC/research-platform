"""Lab-wide documents (D233). Who reaches the list route is in the permission matrix; this covers
the shared document routes, which the matrix only exercises with a project document."""

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.search import search
from documents import services
from documents.models import Document, Folder
from labs.models import LabRole
from projects.models import Project

pytestmark = pytest.mark.django_db


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Lab")
    people = {n: make_user() for n in ("pi", "member", "viewer", "outsider")}
    join(people["pi"], lab, LabRole.PI)
    join(people["member"], lab, LabRole.MEMBER)
    join(people["viewer"], lab, LabRole.VIEWER)
    other = make_lab("Other lab")
    join(people["outsider"], other, LabRole.PI)
    doc = services.create_document(lab=lab, user=people["pi"], title="Lab manual", content=[])
    return lab, other, people, doc


def url(lab, doc, tail=""):
    return f"/api/labs/{lab.pk}/documents/{doc.pk}/{tail}"


def save_body(version):
    return {"title": "Lab manual v2", "content": [], "base_version": version}


def test_any_lab_member_reads_even_without_a_project(world):
    lab, _, people, doc = world
    assert client(people["viewer"]).get(url(lab, doc)).status_code == 200
    rows = client(people["viewer"]).get(f"/api/labs/{lab.pk}/lab-documents/").json()
    assert [r["id"] for r in rows] == [str(doc.pk)]
    assert rows[0]["project"] is None


def test_creating_a_lab_document_is_audited(world):
    lab, _, people, _ = world
    body = {"title": "Safety rules", "content": []}
    response = client(people["member"]).post(f"/api/labs/{lab.pk}/lab-documents/", body, "json")
    assert response.status_code == 201
    event = AuditEvent.objects.get(
        action=AuditAction.DOCUMENT_CREATED, target_id=response.json()["id"]
    )
    assert (event.lab, event.actor, event.target_repr) == (lab, people["member"], "Safety rules")


def test_another_labs_document_is_a_404(world):
    lab, other, people, doc = world
    assert client(people["outsider"]).get(url(lab, doc)).status_code == 404
    # A member of another lab cannot reach it through their own lab's address either.
    assert client(people["outsider"]).get(url(other, doc)).status_code == 404


def test_members_edit_viewers_do_not(world):
    lab, _, people, doc = world
    assert (
        client(people["viewer"]).put(url(lab, doc), save_body(1), format="json").status_code == 403
    )
    response = client(people["member"]).put(url(lab, doc), save_body(1), format="json")
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_history_and_restore_work_without_a_project(world):
    lab, _, people, doc = world
    member = client(people["member"])
    member.put(url(lab, doc), save_body(1), format="json")
    assert [r["version"] for r in member.get(url(lab, doc, "revisions/")).json()] == [2, 1]
    assert member.get(url(lab, doc, "revisions/1/")).status_code == 200
    assert client(people["viewer"]).post(url(lab, doc, "revisions/1/restore/")).status_code == 403
    response = member.post(url(lab, doc, "revisions/1/restore/"))
    assert response.status_code == 200
    assert response.json()["title"] == "Lab manual"


def test_only_lab_managers_delete(world):
    lab, _, people, doc = world
    assert client(people["member"]).delete(url(lab, doc)).status_code == 403
    assert client(people["pi"]).delete(url(lab, doc)).status_code == 204
    assert client(people["pi"]).get(url(lab, doc)).status_code == 404
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_DELETED).count() == 1


def test_project_routes_and_folders_stay_project_only(world):
    lab, _, people, doc = world
    project = Project.objects.create(lab=lab, name="P", created_by=people["pi"])
    # Listing a project shows only that project's documents.
    assert (
        client(people["pi"]).get(f"/api/labs/{lab.pk}/projects/{project.pk}/documents/").json()
        == []
    )
    # A lab-wide document cannot be moved into a project's folder.
    folder = Folder.objects.create(project=project, name="F", created_by=people["pi"])
    response = client(people["pi"]).post(
        url(lab, doc, "move/"), {"folder": str(folder.pk)}, format="json"
    )
    assert response.status_code == 400
    assert Document.objects.for_lab(lab).get(pk=doc.pk).folder_id is None
    # ... and a lab folder is not listed, renamed or reached through a project.
    mine = (
        client(people["pi"])
        .post(f"/api/labs/{lab.pk}/lab-folders/", {"name": "SOPs"}, format="json")
        .json()
    )
    project_folders = (
        client(people["pi"]).get(f"/api/labs/{lab.pk}/projects/{project.pk}/folders/").json()
    )
    assert [f["name"] for f in project_folders] == ["F"]
    assert [
        f["id"] for f in client(people["pi"]).get(f"/api/labs/{lab.pk}/lab-folders/").json()
    ] == [mine["id"]]


def test_lab_folders_hold_lab_documents(world):
    lab, other, people, doc = world
    created = client(people["member"]).post(
        f"/api/labs/{lab.pk}/lab-folders/", {"name": "SOPs"}, format="json"
    )
    assert created.status_code == 201
    folder = created.json()
    assert folder["project"] is None
    # a new document can start in it, and an existing one can be moved in and out
    made = client(people["member"]).post(
        f"/api/labs/{lab.pk}/lab-documents/",
        {"title": "Cleaning", "content": [], "folder": folder["id"]},
        format="json",
    )
    assert made.status_code == 201 and made.json()["folder"] == folder["id"]
    move = lambda f: client(people["member"]).post(  # noqa: E731
        url(lab, doc, "move/"), {"folder": f}, format="json"
    )
    assert move(folder["id"]).status_code == 204
    assert Document.objects.for_lab(lab).get(pk=doc.pk).folder_id.hex == folder["id"].replace(
        "-", ""
    )
    assert move(None).status_code == 204
    # rename, then delete: the contents move up, nothing is lost
    detail = f"/api/labs/{lab.pk}/folders/{folder['id']}/"
    assert (
        client(people["member"]).patch(detail, {"name": "Procedures"}, format="json").status_code
        == 200
    )
    assert client(people["member"]).delete(detail).status_code == 204
    assert Document.objects.for_lab(lab).get(title="Cleaning").folder_id is None


def test_lab_folders_follow_the_lab_document_permissions(world):
    lab, other, people, doc = world
    folders = f"/api/labs/{lab.pk}/lab-folders/"
    assert client(people["viewer"]).post(folders, {"name": "x"}, format="json").status_code == 403
    assert client(people["viewer"]).get(folders).status_code == 200
    assert client(people["outsider"]).get(folders).status_code == 404
    folder = client(people["pi"]).post(folders, {"name": "x"}, format="json").json()
    detail = f"/api/labs/{lab.pk}/folders/{folder['id']}/"
    assert client(people["viewer"]).delete(detail).status_code == 403
    assert client(people["outsider"]).delete(detail).status_code == 404


def test_retention_cannot_be_set(world):
    lab, _, people, doc = world
    body = {**save_body(1), "retain_until": "2020-01-01"}
    assert client(people["pi"]).put(url(lab, doc), body, format="json").status_code == 200
    assert Document.objects.for_lab(lab).get(pk=doc.pk).retain_until is None


def test_search_finds_it_for_lab_members_only(world):
    lab, other, people, doc = world
    hits = search(people["viewer"], lab, "manual")
    assert [(h["type"], h["url"]) for h in hits] == [
        ("document", f"/labs/{lab.pk}/documents/{doc.pk}")
    ]
    assert search(people["outsider"], other, "manual") == []
