"""Phase 5 ethics: CRUD, D48, files, reminders (D29) and expiry. Notifications are covered in
core/tests/test_notifications.py; retention in projects/tests/test_retention.py."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification
from documents.models import Attachment
from documents.services import upload_attachment
from ethics.jobs import mark_expired, send_expiry_reminders
from ethics.models import ApprovalStatus, EthicsApproval
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4 ethics"


def day(n):
    return timezone.localdate() + datetime.timedelta(days=n)


class World:
    pass


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    w = World()
    w.lab, w.other_lab = make_lab("Lab A"), make_lab("Lab B")
    w.u = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("admin", LabRole.LAB_ADMIN),
        ("lead", LabRole.MEMBER),
        ("contrib", LabRole.MEMBER),
        ("pviewer", LabRole.MEMBER),
        ("nonproj", LabRole.MEMBER),
        ("lviewer", LabRole.VIEWER),
    ]:
        w.u[name] = make_user()
        join(w.u[name], w.lab, role)
    w.u["other_pi"] = make_user()
    join(w.u["other_pi"], w.other_lab, LabRole.PI)
    w.p1, w.p2 = make_project(w.lab, "P1"), make_project(w.lab, "P2 hidden")
    w.other_project = make_project(w.other_lab, "Other lab project")
    for name, role in [
        ("lead", ProjectRole.LEAD),
        ("contrib", ProjectRole.CONTRIBUTOR),
        ("pviewer", ProjectRole.VIEWER),
        ("lviewer", ProjectRole.CONTRIBUTOR),  # capped to viewer
    ]:
        ProjectMembership.objects.create(lab=w.lab, project=w.p1, user=w.u[name], role=role)
    return w


def api(user=None):
    client = APIClient()
    if user is not None:
        client.force_login(user)
    return client


def url(name, w, **kw):
    return reverse(name, kwargs={"lab_id": w.lab.pk, **kw})


def make_approval(w, *, days=100, projects=None, status=ApprovalStatus.ACTIVE, number=None):
    approval = EthicsApproval.objects.create(
        lab=w.lab,
        approval_number=number or f"IRB-{EthicsApproval.objects.for_lab(w.lab).count() + 1}",
        board="Test Board",
        title="Fake study approval",
        approval_date=day(-300),
        expiry_date=day(days),
        status=status,
        created_by=w.u["pi"],
    )
    approval.projects.add(*(projects if projects is not None else [w.p1]))
    return approval


def body(**kw):
    return {
        "approval_number": "IRB-NEW",
        "board": "Test Board",
        "title": "New approval",
        "approval_date": "2026-01-01",
        "expiry_date": "2027-01-01",
        **kw,
    }


def upload(client, w, approval, ack=True):
    data = {"file": SimpleUploadedFile("scan.pdf", PDF, content_type="application/pdf")}
    if ack:
        data["acknowledged_notice"] = "true"
    return client.post(
        url("ethics:approval-attachments", w, ethicsapproval_id=approval.pk),
        data,
        format="multipart",
    )


def file_for(w, approval):
    pdf = SimpleUploadedFile("f.pdf", PDF, content_type="application/pdf")
    return upload_attachment(approval=approval, user=w.u["pi"], file=pdf)


def download(client, w, attachment):
    return client.get(url("documents:attachment-download", w, attachment_id=attachment.pk))


def detail_url(w, approval):
    return url("ethics:approval-detail", w, ethicsapproval_id=approval.pk)


# ---------------------------------------------------------------- reminders (D29)


def test_25_days_gives_one_30_day_reminder_to_leads_and_pis_only(w):
    approval = make_approval(w, days=25)
    assert send_expiry_reminders() == 3
    got = {n.recipient_id: n for n in Notification.objects.for_lab(w.lab).all()}
    # pi and lab_admin (retention reviewers and implicit leads) plus P1's lead. Not the
    # contributor, viewer, non-project member, lab viewer, or anyone in the other lab.
    assert set(got) == {w.u["pi"].pk, w.u["admin"].pk, w.u["lead"].pk}
    for n in got.values():
        assert n.dedupe_key == f"ethics:{approval.pk}:30:{approval.expiry_date}"
        assert (n.kind, n.target_id, n.lab_id) == ("ethics_expiry", approval.pk, w.lab.pk)
        assert n.read_at is None and "30-day" in n.body


def test_running_twice_does_not_duplicate(w, mailoutbox):
    make_approval(w, days=25)
    assert send_expiry_reminders() == 3
    assert send_expiry_reminders() == 0
    assert Notification.objects.for_lab(w.lab).count() == 3
    assert len(mailoutbox) == 3  # the email stub only fires for new notifications


def test_renewal_rearms_reminders(w):
    approval = make_approval(w, days=25)
    send_expiry_reminders()
    resp = api(w.u["pi"]).patch(
        detail_url(w, approval), {"expiry_date": str(day(20))}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert send_expiry_reminders() == 3  # new expiry date, new key
    assert Notification.objects.for_lab(w.lab).count() == 6
    assert (
        Notification.objects.for_lab(w.lab).filter(dedupe_key__endswith=str(day(20))).count() == 3
    )


def test_61_days_gives_nothing(w):
    make_approval(w, days=61)
    assert send_expiry_reminders() == 0
    assert Notification.objects.for_lab(w.lab).count() == 0


@pytest.mark.parametrize(("days", "threshold"), [(60, 60), (45, 60), (31, 60), (30, 30), (8, 30)])
def test_tightest_threshold_only(w, days, threshold):
    approval = make_approval(w, days=days)
    send_expiry_reminders()
    keys = set(Notification.objects.for_lab(w.lab).values_list("dedupe_key", flat=True))
    assert keys == {f"ethics:{approval.pk}:{threshold}:{approval.expiry_date}"}


@pytest.mark.parametrize("days", [7, 5, 0])
def test_5_days_gives_only_the_7_day_reminder(w, days):
    approval = make_approval(w, days=days)
    assert send_expiry_reminders() == 3
    keys = set(Notification.objects.for_lab(w.lab).values_list("dedupe_key", flat=True))
    assert keys == {f"ethics:{approval.pk}:7:{approval.expiry_date}"}


def test_a_tighter_threshold_still_sends_after_the_wider_one(w):
    approval = make_approval(w, days=25)
    send_expiry_reminders()
    approval.expiry_date = day(5)  # time passes; a new expiry date means a new key anyway
    approval.save()
    assert send_expiry_reminders() == 3


def test_no_reminders_for_expired_or_withdrawn_and_inactive_users_are_skipped(w):
    make_approval(w, days=25, status=ApprovalStatus.EXPIRED, number="E1")
    make_approval(w, days=25, status=ApprovalStatus.WITHDRAWN, number="W1")
    assert send_expiry_reminders() == 0
    w.u["lead"].is_active = False
    w.u["lead"].save()
    make_approval(w, days=25, number="A1")
    assert send_expiry_reminders() == 2  # pi and lab_admin; the deactivated lead is skipped


def test_project_without_a_lead_only_reaches_the_pis(w):
    approval = make_approval(w, days=25, projects=[w.p2])  # nobody is on P2
    assert send_expiry_reminders() == 2
    recipients = set(Notification.objects.for_lab(w.lab).values_list("recipient_id", flat=True))
    assert recipients == {w.u["pi"].pk, w.u["admin"].pk}
    assert Notification.objects.for_lab(w.lab).filter(target_id=approval.pk).count() == 2


def test_mark_expired(w):
    past = make_approval(w, days=-1, number="PAST")
    pending = make_approval(w, days=-3, status=ApprovalStatus.PENDING, number="PEND")
    withdrawn = make_approval(w, days=-3, status=ApprovalStatus.WITHDRAWN, number="WD")
    today_ = make_approval(w, days=0, number="TODAY")  # expires today: not yet expired
    assert mark_expired() == 2
    for obj, status in [
        (past, "expired"),
        (pending, "expired"),
        (withdrawn, "withdrawn"),
        (today_, "active"),
    ]:
        obj.refresh_from_db()
        assert obj.status == status
    event = AuditEvent.objects.get(target_id=past.pk, action=AuditAction.ETHICS_APPROVAL_UPDATED)
    assert event.actor is None and event.actor_label == "job:ethics_expiry"
    assert mark_expired() == 0


def test_renewing_an_expired_approval_reactivates_it(w):
    approval = make_approval(w, days=-5, status=ApprovalStatus.EXPIRED)
    resp = api(w.u["pi"]).patch(
        detail_url(w, approval), {"expiry_date": str(day(40))}, format="json"
    )
    assert resp.status_code == 200 and resp.json()["status"] == "active"


# ---------------------------------------------------------------- CRUD and audit


def test_create_update_delete_are_audited(w):
    client = api(w.u["pi"])
    resp = client.post(url("ethics:approval-list", w), body(projects=[str(w.p1.pk)]), "json")
    assert resp.status_code == 201, resp.content
    approval = EthicsApproval.objects.for_lab(w.lab).get(pk=resp.json()["id"])
    assert [p["id"] for p in resp.json()["projects"]] == [str(w.p1.pk)]
    detail = detail_url(w, approval)
    assert client.patch(detail, {"projects": [str(w.p2.pk)]}, format="json").status_code == 200
    assert client.delete(detail).status_code == 204
    # events inside one transaction share a timestamp, so compare as a multiset
    actions = sorted(
        AuditEvent.objects.filter(target_id=approval.pk).values_list("action", flat=True)
    )
    assert actions == sorted(
        [
            "ethics_approval.created",
            "ethics_approval.links_changed",  # created with P1
            "ethics_approval.updated",
            "ethics_approval.links_changed",  # P1 swapped for P2
            "ethics_approval.deleted",
        ]
    )
    metadata = list(
        AuditEvent.objects.filter(action="ethics_approval.links_changed").values_list(
            "metadata", flat=True
        )
    )
    swap = {"added": [str(w.p2.pk)], "removed": [str(w.p1.pk)]}
    assert swap in metadata and {"added": [str(w.p1.pk)], "removed": []} in metadata
    changed = AuditEvent.objects.filter(action="ethics_approval.links_changed").first()
    assert changed.actor == w.u["pi"] and changed.lab == w.lab


def test_duplicate_number_and_bad_dates_are_400(w):
    client = api(w.u["pi"])
    assert client.post(url("ethics:approval-list", w), body(), "json").status_code == 201
    assert client.post(url("ethics:approval-list", w), body(), "json").status_code == 400
    backwards = body(approval_number="X", expiry_date="2025-01-01")
    assert client.post(url("ethics:approval-list", w), backwards, "json").status_code == 400


# ---------------------------------------------------------------- D48


def test_serialized_projects_are_only_the_visible_ones(w):
    approval = make_approval(w, projects=[w.p1, w.p2])
    detail = detail_url(w, approval)
    names = {
        who: sorted(p["name"] for p in api(w.u[who]).get(detail).json()["projects"])
        for who in ["pi", "admin", "lead", "contrib", "nonproj", "lviewer"]
    }
    assert names["pi"] == names["admin"] == ["P1", "P2 hidden"]
    assert names["lead"] == names["contrib"] == names["lviewer"] == ["P1"]
    assert names["nonproj"] == []
    assert (
        "P2 hidden" not in api(w.u["contrib"]).get(url("ethics:approval-list", w)).content.decode()
    )
    # D52: editing needs every linked project to be visible, so contrib is refused here
    resp = api(w.u["contrib"]).patch(detail, {"title": "Renamed"}, format="json")
    assert resp.status_code == 403
    only_p1 = make_approval(w, projects=[w.p1], number="ONLY-P1")
    resp = api(w.u["contrib"]).patch(detail_url(w, only_p1), {"title": "R"}, format="json")
    assert resp.status_code == 200 and "P2 hidden" not in resp.content.decode()


def test_linking_needs_edit_content_on_the_project(w):
    one = body(projects=[str(w.p1.pk)])
    listing = url("ethics:approval-list", w)
    assert api(w.u["pviewer"]).post(listing, one, "json").status_code == 403
    assert api(w.u["lviewer"]).post(listing, one, "json").status_code == 403
    assert api(w.u["contrib"]).post(listing, one, "json").status_code == 201
    # a project the member cannot see is a 400, like a missing id; so is another lab's
    for hidden in (w.p2, w.other_project):
        data = body(approval_number="Z", projects=[str(hidden.pk)])
        assert api(w.u["contrib"]).post(listing, data, "json").status_code == 400
    # the pi may link anything in the lab
    both = body(approval_number="Y", projects=[str(w.p1.pk), str(w.p2.pk)])
    assert api(w.u["pi"]).post(listing, both, "json").status_code == 201


def test_patch_link_and_unlink_need_edit_content(w):
    approval = make_approval(w, projects=[w.p1])
    detail = detail_url(w, approval)
    # a project viewer may edit the approval (edit_ethics) but not change its links
    assert api(w.u["pviewer"]).patch(detail, {"projects": []}, format="json").status_code == 403
    assert api(w.u["pviewer"]).patch(detail, {"title": "Fine"}, format="json").status_code == 200
    assert list(approval.projects.all()) == [w.p1]
    unlinked = make_approval(w, projects=[], number="NOLINKS")
    odetail = detail_url(w, unlinked)
    link = {"projects": [str(w.p1.pk)]}
    assert api(w.u["pviewer"]).patch(odetail, link, format="json").status_code == 403
    assert unlinked.projects.count() == 0
    assert api(w.u["contrib"]).patch(odetail, link, format="json").status_code == 200
    assert unlinked.projects.count() == 1


def test_unlinking_never_touches_projects_the_user_cannot_see(w):
    approval = make_approval(w, projects=[w.p1, w.p2])
    detail = detail_url(w, approval)
    # D52: contrib sees only P1, so they cannot edit this approval at all, let alone unlink P2
    resp = api(w.u["contrib"]).patch(detail, {"projects": []}, format="json")
    assert resp.status_code == 403
    assert set(approval.projects.all()) == {w.p1, w.p2}
    # a pi sees everything and may unlink
    resp = api(w.u["pi"]).patch(detail, {"projects": [str(w.p2.pk)]}, format="json")
    assert resp.status_code == 200
    assert list(approval.projects.all()) == [w.p2]
    # an editor who sees every linked project still cannot link one they cannot see
    visible = make_approval(w, projects=[w.p1], number="VIS")
    resp = api(w.u["contrib"]).patch(
        detail_url(w, visible), {"projects": [str(w.p2.pk)]}, format="json"
    )
    assert resp.status_code == 400


def test_file_access_needs_a_visible_linked_project_or_pi_admin(w):
    attachment = file_for(w, make_approval(w, projects=[w.p1]))
    expected = {
        "pi": 200,
        "admin": 200,
        "lead": 200,
        "contrib": 200,
        "pviewer": 200,
        "lviewer": 200,  # a lab viewer on P1 sees P1 (capped to viewer)
        "nonproj": 403,  # view_ethics, but sees no linked project
    }
    for who, code in expected.items():
        assert download(api(w.u[who]), w, attachment).status_code == code, who
    assert download(api(w.u["other_pi"]), w, attachment).status_code == 404
    assert download(api(), w, attachment).status_code == 401
    resp = download(api(w.u["pi"]), w, attachment)
    assert b"".join(resp.streaming_content) == PDF
    assert resp["Cache-Control"] == "private, no-store"
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Content-Disposition"].startswith("inline")  # PDF


def test_unlinked_or_hidden_only_approval_files_are_pi_admin_only(w):
    for projects in ([], [w.p2]):
        approval = make_approval(w, projects=projects, number=f"X{len(projects)}")
        attachment = file_for(w, approval)
        for who, code in {"pi": 200, "admin": 200, "lead": 403, "contrib": 403}.items():
            assert download(api(w.u[who]), w, attachment).status_code == code, (who, projects)


def test_attachment_listing_in_the_approval_follows_file_access(w):
    approval = make_approval(w)
    file_for(w, approval)
    detail = detail_url(w, approval)
    seen = api(w.u["contrib"]).get(detail).json()
    assert seen["can_view_files"] is True and len(seen["attachments"]) == 1
    hidden = api(w.u["nonproj"]).get(detail).json()
    assert hidden["can_view_files"] is False and hidden["attachments"] == []
    assert "f.pdf" not in api(w.u["nonproj"]).get(url("ethics:approval-list", w)).content.decode()


def test_ethics_files_are_not_reachable_through_project_attachment_routes(w):
    attachment = file_for(w, make_approval(w))
    client = api(w.u["pi"])
    item = url("documents:attachment-detail", w, attachment_id=attachment.pk)
    assert client.get(item).status_code == 404
    assert client.delete(item).status_code == 404
    project_files = reverse(
        "documents:attachment-list", kwargs={"lab_id": w.lab.pk, "project_id": w.p1.pk}
    )
    assert client.get(project_files).json() == []


def test_a_soft_deleted_linked_project_no_longer_counts_as_visible(w):
    attachment = file_for(w, make_approval(w, projects=[w.p1]))
    Project.objects.for_lab(w.lab).filter(pk=w.p1.pk).update(deleted_at=timezone.now())
    assert download(api(w.u["contrib"]), w, attachment).status_code == 403
    assert download(api(w.u["pi"]), w, attachment).status_code == 200


# ---------------------------------------------------------------- uploads


def test_upload_needs_the_notice_and_uploads_and_downloads_are_audited(w):
    approval = make_approval(w)
    client = api(w.u["lead"])
    assert upload(client, w, approval, ack=False).status_code == 400
    assert Attachment.objects.for_lab(w.lab).count() == 0
    resp = upload(client, w, approval)
    assert resp.status_code == 201, resp.content
    attachment = Attachment.objects.for_lab(w.lab).get(pk=resp.json()["id"])
    assert attachment.ethics_approval_id == approval.pk and attachment.project_id is None
    assert attachment.notice_acknowledged_at is not None
    up = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_UPLOADED)
    assert up.actor == w.u["lead"] and up.target_id == attachment.pk and up.lab == w.lab
    assert up.metadata["notice_acknowledged_at"]
    assert up.metadata["ethics_approval"] == str(approval.pk)
    assert download(api(w.u["contrib"]), w, attachment).status_code == 200
    down = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED)
    assert down.actor == w.u["contrib"] and down.target_id == attachment.pk


def test_upload_needs_edit_ethics_and_file_access(w):
    approval = make_approval(w)
    assert upload(api(w.u["lviewer"]), w, approval).status_code == 403
    assert upload(api(w.u["nonproj"]), w, approval).status_code == 403  # D48: no visible project
    assert upload(api(w.u["pi"]), w, approval).status_code == 201


def test_oversize_upload_is_rejected_with_413_before_reading(w, settings):
    approval = make_approval(w)
    resp = api(w.u["pi"]).post(
        url("ethics:approval-attachments", w, ethicsapproval_id=approval.pk),
        {"acknowledged_notice": "true"},
        format="multipart",
        CONTENT_LENGTH=str(settings.ATTACHMENT_MAX_BYTES + 10 * 1024 * 1024),
    )
    assert resp.status_code == 413


def test_upload_is_throttled(w, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"uploads": "2/hour"})
    approval = make_approval(w)
    client = api(w.u["pi"])
    assert [upload(client, w, approval).status_code for _ in range(3)] == [201, 201, 429]


def test_attachment_must_have_exactly_one_owner(w):
    approval = make_approval(w)
    common = {
        "lab": w.lab,
        "original_filename": "a",
        "content_type": "x/y",
        "size_bytes": 1,
        "sha256": "0" * 64,
        "uploaded_by": w.u["pi"],
        "notice_acknowledged_at": timezone.now(),
    }
    for i, owners in enumerate([{}, {"project": w.p1, "ethics_approval": approval}]):
        with pytest.raises(IntegrityError), transaction.atomic():
            Attachment.objects.create(storage_key=f"k{i}", **common, **owners)


def test_deleting_an_approval_keeps_the_stored_bytes(w, lab_files):
    approval = make_approval(w)
    attachment = file_for(w, approval)
    assert api(w.u["pi"]).delete(detail_url(w, approval)).status_code == 204
    assert lab_files.exists(attachment.storage_key)
