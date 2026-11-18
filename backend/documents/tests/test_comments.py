"""Comments on documents: threads one level deep, resolve and reopen, delete, notices."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from core.notifications import notification_url, visible_notifications
from documents import services
from documents.models import DocumentComment
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    """Lab with a pi, a project lead, the document's owner (a student), a project viewer and a
    member who is not on the project."""
    lab, project = make_lab(), None
    people = {n: make_user(display_name=n.title()) for n in ("pi", "lead", "student", "viewer")}
    people["outside"] = make_user(display_name="Outside")
    join(people["pi"], lab, LabRole.PI)
    for name in ("lead", "student", "viewer", "outside"):
        join(people[name], lab, LabRole.MEMBER)
    project = make_project(lab)
    for name, role in (
        ("lead", ProjectRole.LEAD),
        ("student", ProjectRole.CONTRIBUTOR),
        ("viewer", ProjectRole.VIEWER),
    ):
        ProjectMembership.objects.create(lab=lab, project=project, user=people[name], role=role)
    doc = services.create_document(
        project=project, user=people["student"], title="Draft", content=[]
    )
    return lab, project, doc, people


def client(user):
    c = APIClient()
    c.force_login(user)
    return c


def comments_url(lab, doc, comment=None):
    if comment is None:
        return reverse("documents:comment-list", kwargs={"lab_id": lab.pk, "document_id": doc.pk})
    kw = {"lab_id": lab.pk, "document_id": doc.pk, "comment_id": comment["id"]}
    return reverse("documents:comment-detail", kwargs=kw)


def post(user, lab, doc, body, **extra):
    return client(user).post(comments_url(lab, doc), {"body": body, **extra}, format="json")


def mention(user):
    return f"@[{user.display_name}](user:{user.pk})"


def notices(lab, user, kind=None):
    qs = Notification.objects.for_lab(lab).filter(recipient=user).order_by("created_at")
    return list(qs.filter(kind=kind) if kind else qs)


def resolve(user, lab, doc, comment, value=True):
    return client(user).patch(comments_url(lab, doc, comment), {"resolved": value}, format="json")


def test_thread_resolve_reopen_and_cascade(w):
    lab, _, doc, p = w
    top = post(p["pi"], lab, doc, "Tighten the intro", quote="In this thesis").json()
    assert top["quote"] == "In this thesis" and top["parent"] is None
    reply = post(p["student"], lab, doc, "Done", parent=top["id"]).json()
    assert reply["parent"] == top["id"]
    nested = post(p["pi"], lab, doc, "Too deep", parent=reply["id"])
    assert nested.status_code == 400  # one level of replies

    resolved = resolve(p["student"], lab, doc, top, True)
    assert resolved.json()["resolved_by"]["id"] == str(p["student"].pk)
    assert resolve(p["pi"], lab, doc, reply, True).status_code == 400
    reopened = resolve(p["pi"], lab, doc, top, False)
    assert reopened.json()["resolved_at"] is None

    rows = client(p["viewer"]).get(comments_url(lab, doc)).json()
    assert [r["body"] for r in rows] == ["Tighten the intro", "Done"]
    assert client(p["pi"]).delete(comments_url(lab, doc, top)).status_code == 204
    assert not DocumentComment.objects.for_lab(lab).exists()  # the reply went with it
    event = AuditEvent.objects.get(action=AuditAction.DOCUMENT_COMMENT_DELETED)
    assert event.metadata == {"comment": top["id"], "author": str(p["pi"].pk)}
    assert AuditEvent.objects.filter(action=AuditAction.DOCUMENT_COMMENTED).count() == 2


def test_a_reply_to_another_documents_comment_is_refused(w):
    lab, project, doc, p = w
    other = services.create_document(project=project, user=p["pi"], title="Other", content=[])
    top = post(p["pi"], lab, other, "Elsewhere").json()
    assert post(p["pi"], lab, doc, "Hi", parent=top["id"]).status_code == 400


def test_who_may_resolve_and_delete(w):
    lab, _, doc, p = w
    by_viewer = post(p["viewer"], lab, doc, "A reader's note").json()  # viewers comment (D206)
    by_lead = post(p["lead"], lab, doc, "Lead's note").json()
    student, viewer = client(p["student"]), client(p["viewer"])
    # the viewer resolves and deletes only their own
    assert resolve(p["viewer"], lab, doc, by_lead).status_code == 403
    assert viewer.delete(comments_url(lab, doc, by_lead)).status_code == 403
    assert resolve(p["viewer"], lab, doc, by_viewer).status_code == 200
    # an editor resolves anyone's, but deletes only their own
    assert resolve(p["student"], lab, doc, by_lead).status_code == 200
    assert student.delete(comments_url(lab, doc, by_lead)).status_code == 403
    # the lead deletes anyone's
    assert client(p["lead"]).delete(comments_url(lab, doc, by_viewer)).status_code == 204
    # someone who can't see the project can't see the document or its comments
    assert client(p["outside"]).get(comments_url(lab, doc)).status_code == 404


def test_lab_wide_document(w, join, make_user):
    lab, _, _, p = w
    manual = services.create_document(lab=lab, user=p["student"], title="Manual", content=[])
    lab_viewer = make_user(display_name="Lab viewer")
    join(lab_viewer, lab, LabRole.VIEWER)
    by_viewer = post(lab_viewer, lab, manual, "Typo on page 2").json()
    by_student = post(p["student"], lab, manual, "Fixed").json()
    # a member can't delete someone else's comment on a lab document; a PI can
    assert client(p["lead"]).delete(comments_url(lab, manual, by_student)).status_code == 403
    assert resolve(lab_viewer, lab, manual, by_student, True).status_code == 403
    assert client(p["pi"]).delete(comments_url(lab, manual, by_viewer)).status_code == 204
    n = notices(lab, p["student"], NotificationKind.DOCUMENT_COMMENT)[0]
    assert notification_url(n, p["student"]) == f"/labs/{lab.pk}/documents/{manual.pk}?comments=1"


def test_notices_go_to_the_owner_the_mentioned_and_the_thread(w):
    lab, project, doc, p = w
    top = post(p["pi"], lab, doc, f"See this {mention(p['lead'])} {mention(p['outside'])}").json()
    owner = notices(lab, p["student"])
    assert [(n.kind, n.title) for n in owner] == [
        (NotificationKind.DOCUMENT_COMMENT, "Pi commented on Draft")
    ]
    assert owner[0].body == "See this @Lead @Outside"
    url = f"/labs/{lab.pk}/projects/{project.pk}/documents/{doc.pk}?comments=1"
    assert notification_url(owner[0], p["student"]) == url
    lead = notices(lab, p["lead"])
    assert [n.title for n in lead] == ["Pi mentioned you in a comment on Draft"]
    assert notification_url(lead[0], p["lead"]) == url
    assert notices(lab, p["outside"]) == []  # can't read the document
    assert notices(lab, p["pi"]) == []  # never told about your own comment

    # mentioning the owner tells them once, as a mention
    post(p["lead"], lab, doc, f"{mention(p['student'])} please check", parent=top["id"])
    assert [n.kind for n in notices(lab, p["student"])] == [
        NotificationKind.DOCUMENT_COMMENT,
        NotificationKind.MENTION,
    ]
    # a reply tells whoever started the thread
    assert [n.title for n in notices(lab, p["pi"])] == ["Lead replied to your comment on Draft"]


def test_comments_go_with_their_document(w):
    lab, _, doc, p = w
    post(p["pi"], lab, doc, "Note")
    services.delete_document(doc, user=p["student"])
    assert client(p["pi"]).get(comments_url(lab, doc)).status_code == 404
    qs = Notification.objects.for_lab(lab).filter(recipient=p["student"])
    assert visible_notifications(p["student"], lab, qs) == []
