"""Handing a document to a new owner from the handover page (walkthrough fix)."""

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from documents import services
from labs.models import LabMembership, LabRole
from projects import handover
from projects.models import Project, ProjectMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab = make_lab("Lab")
    pi, leaver, heir, outsider = (make_user(display_name=n) for n in ("Pat", "Ana", "Bo", "Cy"))
    join(pi, lab, LabRole.PI)
    for u in (leaver, heir, outsider):
        join(u, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="Study", created_by=pi)
    for u in (leaver, heir):
        ProjectMembership.objects.create(lab=lab, project=project, user=u, role="contributor")
    doc = services.create_document(project=project, user=leaver, title="Notes", content=[])
    return dict(lab=lab, pi=pi, leaver=leaver, heir=heir, outsider=outsider, doc=doc)


def post(w, who, owner):
    client = APIClient()
    client.force_login(w[who])
    url = f"/api/labs/{w['lab'].pk}/documents/{w['doc'].pk}/owner/"
    return client.post(url, {"owner": str(owner.pk)}, format="json")


def orphans(w):
    m = LabMembership.objects.for_lab(w["lab"]).get(user=w["leaver"])
    report = handover.build_report(requester=w["pi"], lab=w["lab"], membership=m)
    return [i["title"] for i in report["no_other_owner"]]


def test_reassign_clears_needs_a_new_owner_audits_and_tells_the_new_owner(w):
    assert orphans(w) == ["Notes"]
    assert post(w, "pi", w["heir"]).status_code == 204
    w["doc"].refresh_from_db()
    assert w["doc"].created_by == w["heir"]
    assert orphans(w) == []
    (ev,) = AuditEvent.objects.filter(action=AuditAction.DOCUMENT_OWNER_CHANGED)
    assert ev.actor == w["pi"] and ev.metadata["old_owner_id"] == str(w["leaver"].pk)
    (note,) = Notification.objects.for_lab(w["lab"]).filter(kind=NotificationKind.DOCUMENT_OWNER)
    assert note.recipient == w["heir"] and note.title == "Pat made you the owner of Notes"


def test_new_owner_must_be_able_to_edit_the_project_and_contributors_cannot_reassign(w):
    res = post(w, "pi", w["outsider"])  # in the lab, not on the project
    assert res.status_code == 400 and "owner" in res.json()
    assert post(w, "heir", w["heir"]).status_code == 403  # a contributor
    assert not AuditEvent.objects.filter(action=AuditAction.DOCUMENT_OWNER_CHANGED).exists()
