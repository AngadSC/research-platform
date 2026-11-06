"""Data management plan (Run 5, D180 to D182): the singleton per project, revisions, approval
by leads, the reopen-on-edit rule, the attachment scope and the audit trail."""

import pytest
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from documents.models import Attachment
from projects.models import ProjectRole
from provenance.models import DataManagementPlan
from provenance.tests.test_provenance import World

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    return World(make_lab, make_user, make_project, join)


def url(w, name="dmp", project=None):
    kwargs = {"lab_id": w.lab.pk, "project_id": (project or w.project).pk}
    return reverse(f"provenance:{name}", kwargs=kwargs)


def patch(w, body, user=None, project=None):
    return w.client(user).patch(url(w, project=project), body, format="json")


def audited(*names):
    qs = AuditEvent.objects.filter(action__in=names).order_by("occurred_at", "id")
    return list(qs.values_list("action", flat=True))


def attachment(w, project=None):
    return Attachment.objects.create(
        lab=w.lab,
        project=project or w.project,
        storage_key=f"dmp/{timezone.now().timestamp()}",
        original_filename="dmp.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        uploaded_by=w.pi,
        notice_acknowledged_at=timezone.now(),
    )


def test_no_plan_reads_as_an_empty_draft_and_writes_nothing(w):
    data = w.client().get(url(w)).json()
    assert data["exists"] is False and data["status"] == "draft" and data["storage"] == ""
    assert not DataManagementPlan.objects.for_lab(w.lab).exists()
    assert w.client().get(url(w, "dmp-revisions")).json() == []


def test_create_edit_and_revisions(w):
    contributor = w.member(ProjectRole.CONTRIBUTOR)
    first = patch(w, {"data_description": "Interviews", "sharing": "Borealis"}, contributor)
    assert first.status_code == 200, first.content
    assert first.json()["exists"] is True
    assert first.json()["updated_by"]["id"] == str(contributor.pk)
    patch(w, {"storage": "Encrypted lab server", "status": "submitted"})
    revs = w.client().get(url(w, "dmp-revisions")).json()
    assert [r["number"] for r in revs] == [2, 1]
    assert revs[1]["snapshot"]["data_description"] == "Interviews"
    assert revs[1]["snapshot"]["storage"] == "" and revs[0]["snapshot"]["status"] == "submitted"
    assert audited("dmp.created", "dmp.updated") == ["dmp.created", "dmp.updated"]
    event = AuditEvent.objects.filter(action="dmp.updated").get()
    assert event.metadata["fields"] == ["status", "storage"]


def test_validation_of_url_status_and_sections(w):
    assert patch(w, {"external_url": "javascript:alert(1)"}).status_code == 400
    ok_url = "https://assistant.portagenetwork.ca/plan/1"
    assert patch(w, {"external_url": ok_url}).status_code == 200
    assert patch(w, {"status": "approved"}).status_code == 400  # only the approve endpoint
    assert patch(w, {"storage": "x" * 20001}).status_code == 400
    assert patch(w, {"last_reviewed": "2030-05-01"}).json()["last_reviewed"] == "2030-05-01"


def test_approve_needs_a_lead_and_a_saved_plan(w):
    contributor = w.member(ProjectRole.CONTRIBUTOR)
    lead = w.member(ProjectRole.LEAD)
    approve = url(w, "dmp-approve")
    assert w.client(lead).post(approve).status_code == 400  # nothing saved yet
    patch(w, {"storage": "Server"})
    assert w.client(contributor).post(approve).status_code == 403
    resp = w.client(lead).post(approve)
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert data["status"] == "approved" and data["approved_by"]["id"] == str(lead.pk)
    assert data["approved_at"] and data["last_reviewed"]
    assert audited("dmp.approved") == ["dmp.approved"]
    assert w.client().get(url(w, "dmp-revisions")).json()[0]["snapshot"]["status"] == "approved"


def test_editing_an_approved_plan_reopens_it(w):
    patch(w, {"storage": "Server"})
    w.client().post(url(w, "dmp-approve"))
    same = patch(w, {"storage": "Server"}).json()  # no change keeps the approval
    assert same["status"] == "approved"
    edited = patch(w, {"storage": "Cloud"}).json()
    assert edited["status"] == "draft" and edited["approved_by"] is None
    assert edited["approved_at"] is None


def test_delete_needs_a_lead_and_is_audited(w):
    contributor = w.member(ProjectRole.CONTRIBUTOR)
    patch(w, {"storage": "Server"})
    assert w.client(contributor).delete(url(w)).status_code == 403
    assert w.client().delete(url(w)).status_code == 204
    assert not DataManagementPlan.objects.for_lab(w.lab).exists()
    assert w.client().delete(url(w)).status_code == 204  # idempotent
    assert audited("dmp.deleted") == ["dmp.deleted"]


def test_attachment_must_be_a_live_file_of_this_project(w):
    mine, theirs = attachment(w), attachment(w, w.other)
    assert patch(w, {"attachment": str(theirs.pk)}).status_code == 400
    ok = patch(w, {"attachment": str(mine.pk)})
    assert ok.status_code == 200 and ok.json()["attachment"]["original_filename"] == "dmp.pdf"
    assert patch(w, {"attachment": None}).json()["attachment"] is None
    mine.deleted_at = timezone.now()
    mine.save()
    assert patch(w, {"attachment": str(mine.pk)}).status_code == 400


def test_plans_are_per_project_and_isolated_from_other_labs(w):
    patch(w, {"storage": "P1 only"})
    assert w.client().get(url(w, project=w.other)).json()["exists"] is False
    # another lab's PI cannot see this project at all
    resp = w.client(w.pi_b).get(url(w))
    assert resp.status_code == 404
    assert w.client(w.pi_b).patch(url(w), {"storage": "x"}, format="json").status_code == 404


def test_a_viewer_reads_but_cannot_write(w):
    viewer = w.member(ProjectRole.VIEWER)
    patch(w, {"storage": "Server"})
    assert w.client(viewer).get(url(w)).json()["storage"] == "Server"
    assert patch(w, {"storage": "x"}, viewer).status_code == 403
