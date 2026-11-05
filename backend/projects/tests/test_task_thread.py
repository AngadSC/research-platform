"""Task documents, files and the update thread (Run 4, D141, D142)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from documents import services as doc_services
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task, TaskPost

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab, other = make_lab("Lab"), make_lab("Other Lab")
    pi, lead, worker, viewer, outsider = (make_user() for _ in range(5))
    join(pi, lab, LabRole.PI)
    for u in (lead, worker, viewer):
        join(u, lab, LabRole.MEMBER)
    join(outsider, other, LabRole.PI)
    project = Project.objects.create(lab=lab, name="P", created_by=pi)
    for user, role in [
        (lead, ProjectRole.LEAD),
        (worker, ProjectRole.CONTRIBUTOR),
        (viewer, ProjectRole.VIEWER),
    ]:
        ProjectMembership.objects.create(lab=lab, project=project, user=user, role=role)
    task = Task.objects.create(lab=lab, project=project, title="T", created_by=pi, assignee=worker)
    return dict(lab=lab, other=other, pi=pi, lead=lead, worker=worker, viewer=viewer,
                outsider=outsider, project=project, task=task)  # fmt: skip


def api(user):
    c = APIClient()
    c.force_login(user)
    return c


def url(w, suffix=""):
    return f"/api/labs/{w['lab'].pk}/tasks/{w['task'].pk}/{suffix}"


def post(w, user, body="hello"):
    return api(user).post(url(w, "posts/"), {"body": body}, "json")


def test_thread_post_list_order_and_author(w):
    first = post(w, w["lead"], "one").json()
    post(w, w["pi"], "two")
    rows = api(w["viewer"]).get(url(w, "posts/")).json()  # viewers read
    assert [r["body"] for r in rows] == ["one", "two"]
    assert rows[0]["author"]["id"] == str(w["lead"].pk) and first["created_at"]
    assert (
        api(w["worker"])
        .get(f"/api/labs/{w['lab'].pk}/projects/{w['project'].pk}/tasks/")
        .json()[0]["post_count"]
        == 2
    )


def test_viewer_cannot_post_and_empty_body_rejected(w):
    assert post(w, w["viewer"]).status_code == 403  # D142
    assert post(w, w["lead"], "   ").status_code == 400
    assert post(w, w["lead"], "x" * 5001).status_code == 400


def test_post_notifies_assignee_in_app_only(w, mailoutbox):
    assert post(w, w["lead"], "status update").status_code == 201
    n = Notification.objects.for_lab(w["lab"]).get(recipient=w["worker"])
    assert n.kind == NotificationKind.TASK_POST and "status update" in n.body
    assert n.target_id == w["task"].pk
    assert mailoutbox == []  # D71


def test_no_notification_for_own_post_or_unassigned(w):
    post(w, w["worker"], "mine")
    w["task"].assignee = None
    w["task"].save()
    post(w, w["lead"], "nobody home")
    assert not Notification.objects.for_lab(w["lab"]).exists()


def test_notification_hidden_after_access_lost(w):
    from core.notifications import visible_notifications

    post(w, w["lead"])
    qs = Notification.objects.for_lab(w["lab"]).filter(recipient=w["worker"])
    assert len(visible_notifications(w["worker"], w["lab"], qs)) == 1
    ProjectMembership.objects.for_lab(w["lab"]).filter(user=w["worker"]).delete()
    assert visible_notifications(w["worker"], w["lab"], qs) == []


def test_only_author_edits(w):
    pid = post(w, w["worker"]).json()["id"]
    item = f"/api/labs/{w['lab'].pk}/task-posts/{pid}/"
    assert api(w["lead"]).patch(item, {"body": "x"}, "json").status_code == 403
    resp = api(w["worker"]).patch(item, {"body": "fixed"}, "json")
    assert resp.status_code == 200 and resp.json()["body"] == "fixed" and resp.json()["edited_at"]


def test_author_and_lead_delete_and_audit(w):
    mine = post(w, w["worker"]).json()["id"]
    theirs = post(w, w["worker"]).json()["id"]
    item = lambda pid: f"/api/labs/{w['lab'].pk}/task-posts/{pid}/"  # noqa: E731
    assert api(w["worker"]).delete(item(mine)).status_code == 204
    other = post(w, w["lead"]).json()["id"]
    assert api(w["worker"]).delete(item(other)).status_code == 403  # not author, not lead
    assert api(w["lead"]).delete(item(theirs)).status_code == 204  # leads delete any
    events = AuditEvent.objects.filter(action=AuditAction.TASK_POST_DELETED).order_by("occurred_at")
    assert [e.actor_id for e in events] == [w["worker"].pk, w["lead"].pk]
    assert str(events[1].target_id) == theirs and events[1].lab_id == w["lab"].pk
    assert TaskPost.objects.for_lab(w["lab"]).count() == 1


def test_cross_lab_thread_is_404(w):
    assert api(w["outsider"]).get(url(w, "posts/")).status_code == 404
    assert api(w["outsider"]).post(url(w, "posts/"), {"body": "x"}, "json").status_code == 404
    pid = post(w, w["lead"]).json()["id"]
    assert (
        api(w["outsider"]).delete(f"/api/labs/{w['lab'].pk}/task-posts/{pid}/").status_code == 404
    )


def _doc(w, project=None, user=None):
    return doc_services.create_document(
        project=project or w["project"], user=user or w["pi"], title="D", content=[]
    )


def test_attach_and_detach_document_and_file(w):
    doc = _doc(w)
    att = doc_services.upload_attachment(
        user=w["pi"],
        project=w["project"],
        file=SimpleUploadedFile("a.txt", b"hi", content_type="text/plain"),
    )
    c = api(w["worker"])
    assert c.post(url(w, "documents/"), {"id": str(doc.pk)}, "json").status_code == 200
    resp = c.post(url(w, "attachments/"), {"id": str(att.pk)}, "json")
    body = resp.json()
    assert body["documents"][0]["id"] == str(doc.pk) and body["documents"][0]["version"] == 1
    assert body["attachments"][0]["original_filename"] == "a.txt"
    c.post(url(w, "documents/"), {"id": str(doc.pk)}, "json")  # idempotent
    assert w["task"].documents.count() == 1
    assert c.delete(url(w, f"documents/{doc.pk}/")).json()["documents"] == []
    assert c.delete(url(w, f"attachments/{att.pk}/")).json()["attachments"] == []
    assert (
        api(w["viewer"]).post(url(w, "documents/"), {"id": str(doc.pk)}, "json").status_code == 403
    )


def test_soft_deleted_document_drops_off_the_task(w):
    doc = _doc(w)
    w["task"].documents.add(doc)
    doc_services.delete_document(doc, user=w["pi"])
    resp = api(w["worker"]).get(f"/api/labs/{w['lab'].pk}/tasks/{w['task'].pk}/")
    assert resp.json()["documents"] == []


def test_other_project_document_is_rejected(w):
    p2 = Project.objects.create(lab=w["lab"], name="P2", created_by=w["pi"])
    stranger = _doc(w, project=p2)
    resp = api(w["lead"]).post(url(w, "documents/"), {"id": str(stranger.pk)}, "json")
    assert resp.status_code == 400
    assert w["task"].documents.count() == 0


def test_db_rejects_cross_project_and_cross_lab_links(w, make_user):
    p2 = Project.objects.create(lab=w["lab"], name="P2", created_by=w["pi"])
    other_project_doc = _doc(w, project=p2)
    through = Task.documents.through
    with pytest.raises(DatabaseError), transaction.atomic():  # raw row: skips the ORM checks
        through.objects.create(task_id=w["task"].pk, document_id=other_project_doc.pk)
    op = Project.objects.create(lab=w["other"], name="OP", created_by=w["outsider"])
    foreign = _doc(w, project=op, user=w["outsider"])
    with pytest.raises(DatabaseError), transaction.atomic():
        through.objects.create(task_id=w["task"].pk, document_id=foreign.pk)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # the composite (task, lab) FK is deferred
        cur.execute(
            "INSERT INTO projects_taskpost (id, lab_id, task_id, author_id, body, created_at,"
            " updated_at) VALUES (gen_random_uuid(), %s, %s, %s, 'x', now(), now())",
            [w["other"].pk, w["task"].pk, w["outsider"].pk],
        )


def test_task_delete_removes_thread(w):
    post(w, w["lead"])
    api(w["lead"]).delete(f"/api/labs/{w['lab'].pk}/tasks/{w['task'].pk}/")
    assert TaskPost.objects.for_lab(w["lab"]).count() == 0
