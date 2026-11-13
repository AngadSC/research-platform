"""UX review fixes, 12 Nov 2026: archiving by a lead, changing an invite's role, funding kept from
non-PIs, readable audit labels that never name a PI-only file to a lab admin, flagged files refused
as analysis code, and "last activity" moved by writes only."""

from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from audit.services import record
from documents.models import Attachment
from labs.models import Invite, LabRole
from projects.models import ProjectMembership, ProjectRole, ProjectStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    lab, other_lab = make_lab("Lab A"), make_lab("Lab B")
    people = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("admin", LabRole.LAB_ADMIN),
        ("lead", LabRole.MEMBER),
        ("contrib", LabRole.MEMBER),
        ("pviewer", LabRole.MEMBER),
        ("lviewer", LabRole.VIEWER),
    ]:
        people[name] = make_user(display_name=f"{name.title()} Example")
        join(people[name], lab, role)
    outsider = make_user()
    join(outsider, other_lab, LabRole.PI)
    project = make_project(lab, "Sleep Study")
    for name, role in [
        ("lead", ProjectRole.LEAD),
        ("contrib", ProjectRole.CONTRIBUTOR),
        ("pviewer", ProjectRole.VIEWER),
        ("lviewer", ProjectRole.CONTRIBUTOR),  # capped to viewer (D19)
    ]:
        ProjectMembership.objects.create(lab=lab, project=project, user=people[name], role=role)

    def client(name):
        c = APIClient()
        c.force_login(outsider if name == "outsider" else people[name])
        return c

    return SimpleNamespace(lab=lab, project=project, client=client, outsider=outsider, **people)


def project_url(w, name="project-detail", **kw):
    return reverse(f"projects:{name}", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk})


def upload(w, who="pi", **extra):
    body = {
        "file": SimpleUploadedFile("grant-letter.pdf", b"%PDF-1.4 x", "application/pdf"),
        "acknowledged_notice": "true",
        **extra,
    }
    url = reverse(
        "documents:attachment-list", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk}
    )
    resp = w.client(who).post(url, body, format="multipart")
    assert resp.status_code == 201, resp.content
    return Attachment.objects.for_lab(w.lab).get(pk=resp.json()["id"])


def audit_list(w, who, **params):
    url = reverse("audit:audit-event-list", kwargs={"lab_id": w.lab.pk})
    resp = w.client(who).get(url, params)
    assert resp.status_code == 200, resp.content
    return resp


# ---------------------------------------------------------------- archive


def test_a_lead_can_archive_but_not_delete(w):
    archive = {"status": ProjectStatus.ARCHIVED}
    for who in ("contrib", "pviewer", "lviewer"):
        assert w.client(who).patch(project_url(w), archive, format="json").status_code == 403
    assert w.client("lead").delete(project_url(w)).status_code == 403  # D28
    resp = w.client("lead").patch(project_url(w), archive, format="json")
    assert resp.status_code == 200 and resp.json()["status"] == "archived"
    event = AuditEvent.objects.get(action=AuditAction.PROJECT_ARCHIVED)
    assert event.actor == w.lead and event.target_id == w.project.pk
    assert event.metadata["old_status"] == "planning" and event.metadata["new_status"] == "archived"
    # bringing it back is an ordinary update
    w.client("lead").patch(project_url(w), {"status": "active"}, format="json")
    assert AuditEvent.objects.filter(action=AuditAction.PROJECT_UPDATED).exists()


# ---------------------------------------------------------------- invite role


def test_changing_an_invites_role(w):
    invite, _ = Invite.issue(
        lab=w.lab, email="new@example.test", role=LabRole.MEMBER, invited_by=w.pi
    )
    url = reverse("labs:invite-detail", kwargs={"lab_id": w.lab.pk, "invite_id": invite.pk})
    assert w.client("lead").patch(url, {"role": "viewer"}, format="json").status_code == 403
    assert w.client("outsider").patch(url, {"role": "viewer"}, format="json").status_code == 404
    # only a PI grants the PI role (D40)
    assert w.client("admin").patch(url, {"role": "pi"}, format="json").status_code == 403
    resp = w.client("admin").patch(url, {"role": "lab_admin"}, format="json")
    assert resp.status_code == 200 and resp.json()["role"] == "lab_admin"
    invite.refresh_from_db()
    assert invite.role == "lab_admin" and invite.invited_by == w.admin
    event = AuditEvent.objects.get(action=AuditAction.MEMBERSHIP_INVITE_ROLE_CHANGED)
    assert event.metadata == {
        "email": "new@example.test",
        "old_role": "member",
        "new_role": "lab_admin",
    }
    assert w.client("pi").patch(url, {"role": "pi"}, format="json").status_code == 200
    # and an admin can no longer touch an invite for a PI
    assert w.client("admin").patch(url, {"role": "member"}, format="json").status_code == 403


# ---------------------------------------------------------------- funding (D226)


def test_funding_never_reaches_non_pis(w):
    funding = reverse(
        "provenance:funding-list", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk}
    )
    body = {"funder": "Example Funder", "program": "Example Grant", "status": "active"}
    assert w.client("pi").post(funding, body, format="json").status_code == 201
    assert w.client("pi").get(funding).status_code == 200
    for who in ("admin", "lead", "contrib", "pviewer"):
        assert w.client(who).get(funding).status_code == 403
        detail = w.client(who).get(project_url(w))
        assert b"Example Funder" not in detail.content
        assert "access_funding" not in detail.json()["my_permissions"]


# ---------------------------------------------------------------- audit labels


def test_audit_names_the_person_and_project(w):
    url = project_url(w, "projectmember-list")
    pm = ProjectMembership.objects.for_lab(w.lab).get(user=w.contrib)
    pm.delete()
    body = {"user": str(w.contrib.pk), "role": "contributor"}
    assert w.client("pi").post(url, body, format="json").status_code == 201
    pm = ProjectMembership.objects.for_lab(w.lab).get(user=w.contrib)
    detail = reverse(
        "projects:projectmember-detail",
        kwargs={"lab_id": w.lab.pk, "projectmembership_id": pm.pk},
    )
    assert w.client("pi").patch(detail, {"role": "viewer"}, format="json").status_code == 200
    labels = [e["target_label"] for e in audit_list(w, "admin").json()["results"]]
    assert "Contrib Example (Contributor to Viewer) in Sleep Study" in labels
    assert "Contrib Example (Contributor) in Sleep Study" in labels


def test_lab_role_casing(w):
    from labs.models import LabMembership

    members = LabMembership.objects.for_lab(w.lab)
    assert str(members.get(user=w.admin)) == "Admin Example (Lab admin)"
    assert str(members.get(user=w.pi)) == "Pi Example (PI)"


def test_audit_never_names_a_pi_only_file_to_a_lab_admin(w):
    letter = upload(w, pi_only="true")
    # e.g. a PI's AI app reading the letter
    record(AuditAction.ATTACHMENT_DOWNLOADED, actor=w.pi, lab=w.lab, target=letter)
    admin = audit_list(w, "admin")
    assert b"grant-letter" not in admin.content
    assert "A file only PIs can open" in [e["target_label"] for e in admin.json()["results"]]
    assert b"grant-letter.pdf" in audit_list(w, "pi").content


def test_changes_only_leaves_out_reads(w):
    record(AuditAction.DOCUMENT_VIEWED, actor=w.pi, lab=w.lab)
    record(AuditAction.LAB_UPDATED, actor=w.pi, lab=w.lab)
    actions = [e["action"] for e in audit_list(w, "pi", changes_only="true").json()["results"]]
    assert "lab.updated" in actions and "document.viewed" not in actions
    actions = [e["action"] for e in audit_list(w, "pi").json()["results"]]
    assert "document.viewed" in actions


def test_removing_the_identifying_mark_is_audited(w):
    f = upload(w, contains_participant_data="true")
    url = reverse("documents:attachment-detail", kwargs={"lab_id": w.lab.pk, "attachment_id": f.pk})
    resp = w.client("contrib").patch(url, {"contains_participant_data": False}, format="json")
    assert resp.status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_PARTICIPANT_FLAG_CHANGED)
    assert event.actor == w.contrib and event.metadata == {"old": True, "new": False}


# ---------------------------------------------------------------- analysis code (VISION C1)


def test_flagged_files_are_refused_as_analysis_code(w):
    flagged = upload(w, contains_participant_data="true")
    clean = upload(w)
    files = project_url(w) + "attachments/"
    ids = [a["id"] for a in w.client("contrib").get(files, {"unflagged": "1"}).json()]
    assert ids == [str(clean.pk)]
    assert len(w.client("contrib").get(files).json()) == 2  # the Documents list is unchanged
    analyses = reverse(
        "provenance:analysis-list", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk}
    )
    resp = w.client("contrib").post(
        analyses, {"title": "A", "code_attachment": str(flagged.pk)}, format="json"
    )
    assert resp.status_code == 400 and "code_attachment" in resp.json()
    ok = w.client("contrib").post(
        analyses, {"title": "A", "code_attachment": str(clean.pk)}, format="json"
    )
    assert ok.status_code == 201, ok.content
    detail = reverse(
        "provenance:analysis-detail", kwargs={"lab_id": w.lab.pk, "analysis_id": ok.json()["id"]}
    )
    resp = w.client("contrib").patch(detail, {"code_attachment": str(flagged.pk)}, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------- last activity (D139)


def test_reading_never_moves_last_activity(w):
    read = project_url(w, "chatmessage-read")
    for who in ("lviewer", "pviewer"):
        assert w.client(who).post(read, {"last_read_at": "2030-01-01T00:00:00Z"}).status_code < 300
        w.client(who).get(project_url(w))
        w.client(who).get(project_url(w, "chatmessage-list"))
    w.project.refresh_from_db()
    assert w.project.last_activity_at is None
    w.client("contrib").post(project_url(w, "task-list"), {"title": "T"}, format="json")
    w.project.refresh_from_db()
    assert w.project.last_activity_by == w.contrib
