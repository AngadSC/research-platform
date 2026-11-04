"""Phase 5 security review regressions (D52 to D55)."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification
from core.notifications import notify
from core.tenancy import CrossLabError
from core.uploads import PayloadTooLarge, SizeLimitUploadHandler
from documents.models import Attachment, Document
from documents.services import create_document
from ethics.jobs import mark_expired, send_expiry_reminders
from ethics.models import EthicsApproval
from labs.models import Invite, LabMembership, LabRole
from projects.jobs import retention_scan
from projects.models import Project, ProjectMembership, ProjectRole
from provenance.models import Analysis, Result

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def day(n):
    return timezone.localdate() + datetime.timedelta(days=n)


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    class W:
        pass

    w = W()
    w.lab = make_lab("L")
    w.u = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("admin", LabRole.LAB_ADMIN),
        ("lead", LabRole.MEMBER),
        ("outsider", LabRole.MEMBER),  # on no project
    ]:
        w.u[name] = make_user()
        join(w.u[name], w.lab, role)
    w.p1, w.p2 = make_project(w.lab, "P1"), make_project(w.lab, "P2 hidden")
    ProjectMembership.objects.create(
        lab=w.lab, project=w.p1, user=w.u["lead"], role=ProjectRole.LEAD
    )
    return w


def make_approval(w, projects, days=20):
    a = EthicsApproval.objects.create(
        lab=w.lab,
        approval_number=f"N{EthicsApproval.objects.for_lab(w.lab).count()}",
        board="B",
        title="T",
        approval_date=day(-300),
        expiry_date=day(days),
        created_by=w.u["pi"],
    )
    a.projects.add(*projects)
    return a


def make_attachment(w, approval=None, project=None):
    return Attachment.objects.create(
        lab=w.lab,
        ethics_approval=approval,
        project=project,
        storage_key=f"k/{timezone.now().timestamp()}",
        original_filename="f.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        uploaded_by=w.u["pi"],
        notice_acknowledged_at=timezone.now(),
    )


def detail(w, a):
    return reverse("ethics:approval-detail", kwargs={"lab_id": w.lab.pk, "ethicsapproval_id": a.pk})


# ---- 1 (D52): approval edit/delete needs visibility of every linked project


def test_member_cannot_patch_or_delete_approval_linked_to_hidden_project(w):
    a = make_approval(w, [w.p2])
    att = make_attachment(w, approval=a)
    c = api(w.u["outsider"])
    assert c.patch(detail(w, a), {"status": "withdrawn"}, format="json").status_code == 403
    assert c.delete(detail(w, a)).status_code == 403
    a.refresh_from_db()
    att.refresh_from_db()
    assert a.status == "active" and a.deleted_at is None and att.deleted_at is None


def test_lead_of_only_one_of_two_linked_projects_cannot_edit(w):
    a = make_approval(w, [w.p1, w.p2])
    assert api(w.u["lead"]).delete(detail(w, a)).status_code == 403
    assert api(w.u["lead"]).patch(detail(w, a), {"title": "x"}, format="json").status_code == 403


def test_member_edits_when_all_linked_projects_visible_or_none_linked(w):
    for ap in (make_approval(w, [w.p1]), make_approval(w, [])):
        r = api(w.u["lead"]).patch(detail(w, ap), {"title": "ok"}, format="json")
        assert r.status_code == 200, r.content


def test_delete_is_soft_audited_and_keeps_attachments(w):
    a = make_approval(w, [w.p2])
    att = make_attachment(w, approval=a)
    assert api(w.u["pi"]).delete(detail(w, a)).status_code == 204
    a.refresh_from_db()
    att.refresh_from_db()
    assert a.deleted_at is not None and att.deleted_at is not None
    assert api(w.u["pi"]).get(detail(w, a)).status_code == 404
    assert (
        AuditEvent.objects.filter(lab=w.lab)
        .filter(action=AuditAction.ETHICS_APPROVAL_DELETED, target_id=a.pk)
        .exists()
    )
    listing = api(w.u["pi"]).get(reverse("ethics:approval-list", kwargs={"lab_id": w.lab.pk}))
    assert listing.json() == []


def test_hard_delete_of_approval_with_attachments_is_blocked(w):
    a = make_approval(w, [w.p2])
    make_attachment(w, approval=a)
    with pytest.raises(ProtectedError):
        a.delete()


def test_deleted_approval_is_skipped_by_jobs(w):
    for days in (20, -2):
        a = make_approval(w, [w.p1], days=days)
        a.deleted_at = timezone.now()
        a.save()
    assert send_expiry_reminders() == 0
    assert mark_expired() == 0


# ---- 2 (D53): size limit enforced while streaming


def test_handler_aborts_past_limit_without_content_length(settings):
    settings.ATTACHMENT_MAX_BYTES = 100
    h = SizeLimitUploadHandler()
    h.new_file("file", "a.pdf", "application/pdf", None)
    assert h.receive_data_chunk(b"x" * 60, 0) == b"x" * 60
    with pytest.raises(PayloadTooLarge) as exc:
        h.receive_data_chunk(b"x" * 60, 60)
    assert exc.value.status_code == 413


def test_oversize_file_within_middleware_allowance_gets_413(w, settings):
    settings.ATTACHMENT_MAX_BYTES = 1000  # body < limit + allowance, so Content-Length passes
    a = make_approval(w, [w.p1])
    resp = api(w.u["pi"]).post(
        reverse(
            "ethics:approval-attachments",
            kwargs={"lab_id": w.lab.pk, "ethicsapproval_id": a.pk},
        ),
        {
            "acknowledged_notice": "true",
            "file": SimpleUploadedFile("big.pdf", b"%PDF" + b"x" * 5000, "application/pdf"),
        },
        format="multipart",
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]
    assert not Attachment.objects.for_lab(w.lab).exists()


# ---- 3 (D54): notifications are re-checked when listed


def notes(w, user, q=""):
    url = reverse("core:notification-list", kwargs={"lab_id": w.lab.pk})
    return api(user).get(url + q).json()


def test_ethics_notification_hidden_after_losing_the_project(w):
    make_approval(w, [w.p1])
    send_expiry_reminders()
    lead = w.u["lead"]
    assert len(notes(w, lead)) == 1 and len(notes(w, lead, "?unread=true")) == 1
    ProjectMembership.objects.for_lab(w.lab).filter(user=lead).delete()
    assert notes(w, lead) == []
    assert notes(w, lead, "?unread=true") == []


def test_retention_notification_hidden_after_demotion(w):
    Project.objects.for_lab(w.lab).filter(pk=w.p1.pk).update(retain_until=day(-5))
    retention_scan()
    assert len(notes(w, w.u["admin"])) == 1
    LabMembership.objects.for_lab(w.lab).filter(user=w.u["admin"]).update(role=LabRole.MEMBER)
    assert notes(w, w.u["admin"]) == []


# ---- 4 (D54): an ethics-owned attachment cannot link into a project


def test_fk_and_m2m_to_ethics_owned_attachment_fail(w):
    ethics_att = make_attachment(w, approval=make_approval(w, []))
    kw = {
        "lab": w.lab,
        "project": w.p1,
        "title": "a",
        "ran_by": w.u["pi"],
        "ran_at": timezone.now(),
    }
    with pytest.raises(CrossLabError):
        Analysis.objects.create(code_attachment=ethics_att, **kw)
    own = make_attachment(w, project=w.p1)
    analysis = Analysis.objects.create(code_attachment=own, **kw)  # same project is fine
    result = Result.objects.create(
        lab=w.lab, project=w.p1, title="r", analysis=analysis, created_by=w.u["pi"]
    )
    result.attachments.add(own)
    with pytest.raises(CrossLabError):
        result.attachments.add(ethics_att)


# ---- 5 (D54): row filters on lab-wide models


def test_visible_to_filters_notifications_and_invites(w):
    for u in (w.u["pi"], w.u["lead"]):
        notify(lab=w.lab, recipient=u, kind="task_assigned", title="t", dedupe_key="k")
    mine = Notification.objects.visible_to(w.u["lead"], w.lab)
    assert [n.recipient_id for n in mine] == [w.u["lead"].pk]
    Invite.objects.create(
        lab=w.lab,
        email="x@example.com",
        role=LabRole.MEMBER,
        token_hash="h" * 64,
        invited_by=w.u["pi"],
        expires_at=timezone.now() + datetime.timedelta(days=1),
    )
    assert Invite.objects.visible_to(w.u["lead"], w.lab).count() == 0
    assert Invite.objects.visible_to(w.u["pi"], w.lab).count() == 1


# ---- 6 (D55): retention changes need view_retention and are audited


def project_url(w):
    return reverse("projects:project-detail", kwargs={"lab_id": w.lab.pk, "project_id": w.p1.pk})


def test_lead_cannot_change_or_clear_project_retention(w):
    Project.objects.for_lab(w.lab).filter(pk=w.p1.pk).update(
        retain_until=day(100), retention_note="keep"
    )
    c = api(w.u["lead"])
    assert c.patch(project_url(w), {"retain_until": None}, format="json").status_code == 403
    assert c.patch(project_url(w), {"retention_note": "x"}, format="json").status_code == 403
    same = {"retain_until": str(day(100)), "retention_note": "keep", "name": "renamed"}
    assert c.patch(project_url(w), same, format="json").status_code == 200  # unchanged is fine
    w.p1.refresh_from_db()
    assert w.p1.retain_until == day(100) and w.p1.name == "renamed"


def test_pi_changes_project_retention_and_it_is_audited(w):
    r = api(w.u["pi"]).patch(project_url(w), {"retain_until": str(day(50))}, format="json")
    assert r.status_code == 200
    ev = AuditEvent.objects.filter(lab=w.lab).get(action=AuditAction.RETENTION_CHANGED)
    assert ev.actor == w.u["pi"] and ev.target_id == w.p1.pk
    assert ev.metadata["changes"]["retain_until"] == [None, str(day(50))]


def test_member_cannot_create_project_with_retention(w):
    url = reverse("projects:project-list", kwargs={"lab_id": w.lab.pk})
    c = api(w.u["lead"])
    assert c.post(url, {"name": "n", "retain_until": str(day(9))}, format="json").status_code == 403
    assert c.post(url, {"name": "n"}, format="json").status_code == 201


def test_my_permissions_exposes_view_retention(w):
    assert "view_retention" not in api(w.u["lead"]).get(project_url(w)).json()["my_permissions"]
    assert "view_retention" in api(w.u["pi"]).get(project_url(w)).json()["my_permissions"]


def test_document_retention_needs_view_retention_even_for_a_lead(w):
    doc = create_document(project=w.p1, user=w.u["lead"], title="d", content=[])
    url = reverse("documents:document-detail", kwargs={"lab_id": w.lab.pk, "document_id": doc.pk})
    put = {"title": "d", "content": [], "base_version": doc.version, "retain_until": str(day(5))}
    assert api(w.u["lead"]).put(url, put, format="json").status_code == 403
    assert Document.objects.for_lab(w.lab).get(pk=doc.pk).retain_until is None
    r = api(w.u["pi"]).put(url, put, format="json")
    assert r.status_code == 200, r.content
    ev = AuditEvent.objects.filter(lab=w.lab).get(action=AuditAction.RETENTION_CHANGED)
    assert ev.target_id == doc.pk
    again = {**put, "base_version": doc.version + 1}  # unchanged retention in a lead's save
    assert api(w.u["lead"]).put(url, again, format="json").status_code == 200


# ---- 7 (D56): restricted approvals


def test_restricted_approval_is_hidden_from_non_project_members(w):
    restricted = make_approval(w, [w.p1])
    restricted.restricted = True
    restricted.save()
    open_one = make_approval(w, [w.p1])
    att = make_attachment(w, approval=restricted)
    lst = reverse("ethics:approval-list", kwargs={"lab_id": w.lab.pk})
    dl = reverse(
        "documents:attachment-download", kwargs={"lab_id": w.lab.pk, "attachment_id": att.pk}
    )
    for who in ("pi", "admin", "lead"):
        ids = {r["id"] for r in api(w.u[who]).get(lst).json()}
        assert ids == {str(restricted.pk), str(open_one.pk)}, who
        assert api(w.u[who]).get(detail(w, restricted)).status_code == 200
    c = api(w.u["outsider"])
    assert [r["id"] for r in c.get(lst).json()] == [str(open_one.pk)]
    assert c.get(detail(w, restricted)).status_code == 404
    assert c.get(detail(w, open_one)).status_code == 200  # unrestricted: as before
    assert c.get(dl).status_code == 404
    # reminders: the outsider is never a candidate, and the lead still is
    send_expiry_reminders()
    got = {
        n.recipient_id for n in Notification.objects.for_lab(w.lab).filter(target_id=restricted.pk)
    }
    assert w.u["outsider"].pk not in got and w.u["lead"].pk in got


def test_restricted_flag_follows_the_edit_rule(w):
    a = make_approval(w, [w.p2])
    r = api(w.u["outsider"]).patch(detail(w, a), {"restricted": True}, format="json")
    assert r.status_code == 403
    r = api(w.u["pi"]).patch(detail(w, a), {"restricted": True}, format="json")
    assert r.status_code == 200 and r.json()["restricted"] is True


def test_restricted_notification_hidden_once_access_is_lost(w):
    a = make_approval(w, [w.p1])
    a.restricted = True
    a.save()
    send_expiry_reminders()
    ProjectMembership.objects.for_lab(w.lab).filter(user=w.u["lead"]).delete()
    assert notes(w, w.u["lead"]) == []
