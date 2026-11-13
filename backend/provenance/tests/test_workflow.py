"""Run 4 workflow records: funding, review items, recruitment (D132 to D139)."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from audit.models import AuditEvent
from labs.models import LabRole
from projects.models import DeadlinePriority, ProjectDeadline, ProjectRole
from provenance.models import FundingRecord, RecruitmentEntry, ReviewItem
from provenance.tests.test_provenance import World

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    return World(make_lab, make_user, make_project, join)


def pk(w, project=None):
    return {"lab_id": w.lab.pk, "project_id": (project or w.project).pk}


def url(w, name, project=None, **kw):
    kwargs = {"lab_id": w.lab.pk, **kw}
    if name.endswith("-list") or name == "recruitment-plan":
        kwargs = pk(w, project)
    return reverse(f"provenance:{name}", kwargs=kwargs)


def audited(*names):
    qs = AuditEvent.objects.filter(action__in=names).order_by("occurred_at", "id")
    return list(qs.values_list("action", flat=True))


def post(w, name, body, user=None, project=None):
    return w.client(user).post(url(w, name, project), body, format="json")


# ---------------------------------------------------------------- funding


def test_funding_crud_is_audited_and_the_amount_is_returned(w):
    lead = w.pi
    holder = w.member(ProjectRole.CONTRIBUTOR)
    body = {
        "funder": "NSERC",
        "program": "Discovery",
        "award_number": "RGPIN-1",
        "amount": "12500.50",
        "currency": "CAD",
        "start_date": "2030-01-01",
        "end_date": "2031-01-01",
        "status": "awarded",
        "holder": str(holder.pk),
        "notes": "Year one",
    }
    resp = post(w, "funding-list", body, lead)
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["amount"] == "12500.50" and data["holder"]["id"] == str(holder.pk)
    item = url(w, "funding-detail", fundingrecord_id=data["id"])
    assert w.client(lead).patch(item, {"status": "active"}, format="json").status_code == 200
    assert w.client(lead).delete(item).status_code == 204
    assert audited("funding.created", "funding.updated", "funding.deleted") == [
        "funding.created",
        "funding.updated",
        "funding.deleted",
    ]
    assert not FundingRecord.objects.for_lab(w.lab).exists()


def test_funding_is_pi_only_everywhere(w):
    """D226: every way funding data leaves the server, for a lab admin and a project lead."""
    from audit.models import AuditEvent
    from core.search import search
    from documents import services as doc_services
    from labs.dashboard import build_dashboard
    from labs.lab_calendar import build_calendar
    from provenance.services import workflow_progress

    lead, admin = w.member(ProjectRole.LEAD), w.make_user()
    w.join(admin, w.lab, LabRole.LAB_ADMIN)
    upload = SimpleUploadedFile("grant.pdf", b"%PDF-1.4 grant", content_type="application/pdf")
    letter = doc_services.upload_attachment(project=w.project, user=w.pi, file=upload)
    made = post(
        w,
        "funding-list",
        {
            "funder": "Wellcome",
            "amount": "99.00",
            "status": "active",
            "end_date": str(date.today()),
            "attachment": str(letter.pk),
        },
    ).json()
    assert w.client().get(url(w, "funding-list")).json()[0]["amount"] == "99.00"  # the PI
    assert search(w.pi, w.lab, "Wellcome")
    one = url(w, "funding-detail", fundingrecord_id=made["id"])

    def blocked(user):
        c = w.client(user)
        assert c.get(url(w, "funding-list")).status_code == 403
        assert post(w, "funding-list", {"funder": "X"}, user).status_code == 403
        assert c.get(one).status_code == 404
        assert c.patch(one, {"notes": "n"}, format="json").status_code == 404
        assert search(user, w.lab, "Wellcome") == []
        stages = workflow_progress(w.project, user)["stages"]
        assert "funding" not in [s["key"] for s in stages]
        body = {"stage": "funding", "done": True}
        mark = reverse("provenance:workflow-progress", kwargs=pk(w))
        assert c.patch(mark, body, format="json").status_code == 403
        # the grant letter disappears with the record: no list, no download, no export
        files = reverse("documents:attachment-list", kwargs=pk(w))
        assert str(letter.pk) not in c.get(files).content.decode()
        grabbed = reverse(
            "documents:attachment-download", kwargs={"lab_id": w.lab.pk, "attachment_id": letter.pk}
        )
        assert c.get(grabbed).status_code == 404
        export = c.post(reverse("provenance:export", kwargs=pk(w)))
        assert export.status_code == 200 and "Wellcome" not in export.content.decode()
        assert str(letter.pk) not in export.content.decode()

    blocked(lead)
    blocked(admin)
    day = date.today()
    assert not [r for r in build_calendar(admin, w.lab, day, day) if r["kind"] == "funding"]
    board = build_dashboard(admin, w.lab)
    assert not board["attention"]["funding"]["items"] and board["summary"]["funding_ending"] == 0
    assert {r["funding_end_date"] for r in board["projects"]} == {None}
    assert build_dashboard(w.pi, w.lab)["attention"]["funding"]["items"]
    # the audit log is read by lab admins too, and it names the funder
    audit_url = reverse("audit:audit-event-list", kwargs={"lab_id": w.lab.pk})
    actions = {r["action"] for r in w.client(admin).get(audit_url).json()["results"]}
    assert "funding.created" not in actions
    assert "funding.created" in {r["action"] for r in w.client().get(audit_url).json()["results"]}
    assert AuditEvent.objects.filter(action="funding.created").count() == 1


def _letter(w, name="letter.pdf", **kw):
    from documents import services as doc_services

    upload = SimpleUploadedFile(name, b"%PDF-1.4 grant", content_type="application/pdf")
    return doc_services.upload_attachment(project=w.project, user=w.pi, file=upload, **kw)


def _files(w, user):
    return w.client(user).get(reverse("documents:attachment-list", kwargs=pk(w))).content.decode()


def test_a_grant_letter_stays_pi_only_after_the_link_goes(w):
    """D244: deleting the funding record, or pointing it at another file, must not reopen it."""
    member = w.member(ProjectRole.CONTRIBUTOR)
    letter, other = _letter(w), _letter(w, "second.pdf")
    made = post(w, "funding-list", {"funder": "A", "attachment": str(letter.pk)}).json()
    assert str(letter.pk) not in _files(w, member)
    one = url(w, "funding-detail", fundingrecord_id=made["id"])
    assert w.client().patch(one, {"attachment": str(other.pk)}, format="json").status_code == 200
    assert str(letter.pk) not in _files(w, member) and str(other.pk) not in _files(w, member)
    assert w.client().delete(one).status_code == 204
    assert str(letter.pk) not in _files(w, member) and str(other.pk) not in _files(w, member)
    assert str(letter.pk) in _files(w, w.pi)  # the PI keeps it


def test_a_pi_can_upload_a_letter_that_is_private_from_the_start(w):
    member = w.member(ProjectRole.CONTRIBUTOR)
    files = reverse("documents:attachment-list", kwargs=pk(w))

    def send(user):
        upload = SimpleUploadedFile("award.pdf", b"%PDF-1.4", content_type="application/pdf")
        return w.client(user).post(
            files, {"file": upload, "acknowledged_notice": "true", "pi_only": "true"}
        )

    assert send(member).status_code == 403  # edit_content alone is not enough
    made = send(w.pi)
    assert made.status_code == 201, made.content
    assert made.json()["id"] not in _files(w, member) and made.json()["id"] in _files(w, w.pi)
    actions = AuditEvent.objects.filter(target_id=made.json()["id"])
    assert list(actions.values_list("action", flat=True)) == ["funding.updated"]


def test_a_letter_on_a_task_is_not_named_in_the_export(w):
    from projects.models import Task

    admin = w.make_user()
    w.join(admin, w.lab, LabRole.LAB_ADMIN)
    letter = _letter(w)
    Task.objects.create(lab=w.lab, project=w.project, title="T", created_by=w.pi).attachments.add(
        letter
    )
    post(w, "funding-list", {"funder": "A", "attachment": str(letter.pk)})
    export = reverse("provenance:export", kwargs=pk(w))
    assert w.client(admin).post(export).json()["tasks"][0]["attachments"] == []
    assert w.client().post(export).json()["tasks"][0]["attachments"][0]["id"] == str(letter.pk)


def test_marking_the_funding_stage_is_hidden_from_a_lab_admin(w):
    admin = w.make_user()
    w.join(admin, w.lab, LabRole.LAB_ADMIN)
    mark = reverse("provenance:workflow-progress", kwargs=pk(w))
    assert (
        w.client().patch(mark, {"stage": "funding", "done": True}, format="json").status_code == 200
    )
    audit_url = reverse("audit:audit-event-list", kwargs={"lab_id": w.lab.pk})

    def seen(user):
        return [r["metadata"] for r in w.client(user).get(audit_url).json()["results"]]

    assert not [m for m in seen(admin) if m.get("stage") == "funding"]
    assert [m for m in seen(w.pi) if m.get("stage") == "funding"]


def test_a_one_file_link_never_names_a_letter(w):
    """D226: the External record stays, but its reference to a grant letter does not."""
    member = w.member(ProjectRole.CONTRIBUTOR)
    letter = _letter(w)
    body = {"type": "other", "title": "Talk", "date": "2030-01-01", "attachment": str(letter.pk)}
    made = post(w, "external-list", body, member)
    assert made.status_code == 201, made.content
    post(w, "funding-list", {"funder": "A", "attachment": str(letter.pk)})
    assert w.client(member).get(url(w, "external-list")).json()[0]["attachment"] is None
    assert w.client().get(url(w, "external-list")).json()[0]["attachment"]["id"] == str(letter.pk)


def test_funding_validation(w):
    def bad(body):
        return post(w, "funding-list", {"funder": "A", **body}).status_code

    assert bad({"start_date": "2030-05-01", "end_date": "2030-01-01"}) == 400
    assert bad({"status": "pending"}) == 400
    assert bad({"amount": "-1"}) == 400
    assert bad({"currency": "cad"}) == 400
    stranger = w.make_user()
    w.join(stranger, w.lab, LabRole.MEMBER)  # a lab member who is not on the project
    assert bad({"holder": str(stranger.pk)}) == 400


def test_funding_attachment_must_be_in_the_project(w):
    from documents.models import Attachment

    other = Attachment.objects.create(
        lab=w.lab,
        project=w.other,
        storage_key="k/other",
        original_filename="o.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        uploaded_by=w.pi,
        notice_acknowledged_at="2030-01-01T00:00:00Z",
    )
    resp = post(w, "funding-list", {"funder": "A", "attachment": str(other.pk)})
    assert resp.status_code == 400


def test_funding_from_another_lab_is_invisible(w):
    made = post(w, "funding-list", {"funder": "Secret"})
    assert made.status_code == 201
    item = reverse(
        "provenance:funding-detail",
        kwargs={"lab_id": w.lab_b.pk, "fundingrecord_id": made.json()["id"]},
    )
    assert w.client(w.pi_b).get(item).status_code == 404
    listing = reverse(
        "provenance:funding-list", kwargs={"lab_id": w.lab.pk, "project_id": w.project_b.pk}
    )
    assert w.client().get(listing).status_code == 404


def test_workflow_records_are_in_the_export(w):
    post(w, "funding-list", {"funder": "F", "amount": "5"})
    post(w, "review-list", {"title": "R"})
    resp = w.client().post(reverse("provenance:export", kwargs=pk(w)), {}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["funding"][0]["amount"] == "5.00" and body["review_items"][0]["title"] == "R"
    assert body["recruitment_plan"] == {"target_enrolment": None, "notes": ""}


# ---------------------------------------------------------------- review items


def test_review_item_flow_and_audit(w):
    reviewer = w.member(ProjectRole.VIEWER)  # any lab member who can view the project
    resp = post(
        w,
        "review-list",
        {"title": "Methods sign-off", "reviewer": str(reviewer.pk), "due_date": "2030-03-01"},
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["status"] == "requested"
    assert resp.json()["reviewer"]["id"] == str(reviewer.pk)
    one = url(w, "review-detail", reviewitem_id=resp.json()["id"])
    for status in ("in_review", "changes_requested", "approved"):
        assert w.client().patch(one, {"status": status}, format="json").status_code == 200
    assert w.client().patch(one, {"status": "done"}, format="json").status_code == 400
    assert w.client().delete(one).status_code == 204
    assert len(audited("review_item.created", "review_item.updated", "review_item.deleted")) == 5
    assert not ReviewItem.objects.for_lab(w.lab).exists()


def test_reviewer_must_see_the_project(w):
    stranger = w.make_user()
    w.join(stranger, w.lab, LabRole.MEMBER)
    resp = post(w, "review-list", {"title": "T", "reviewer": str(stranger.pk)})
    assert resp.status_code == 400


# ---------------------------------------------------------------- recruitment


def test_recruitment_entries_and_plan(w):
    empty = w.client().get(url(w, "recruitment-plan"))
    assert empty.status_code == 200 and empty.json() == {"target_enrolment": None, "notes": ""}
    assert audited("recruitment_plan.updated") == []  # a read writes nothing
    plan = url(w, "recruitment-plan")
    first = w.client().patch(plan, {"target_enrolment": 60, "notes": "Rolling"}, format="json")
    assert first.status_code == 200 and first.json()["target_enrolment"] == 60
    again = w.client().patch(plan, {"target_enrolment": 80}, format="json")
    assert again.json() == {"target_enrolment": 80, "notes": "Rolling"}
    assert len(audited("recruitment_plan.updated")) == 2

    for status, count in (("screened", 10), ("enrolled", 7), ("enrolled", 3)):
        body = {"entry_date": "2030-02-01", "status": status, "count": count}
        assert post(w, "recruitment-list", body).status_code == 201
    rows = w.client().get(url(w, "recruitment-list")).json()
    assert sum(r["count"] for r in rows if r["status"] == "enrolled") == 10
    one = url(w, "recruitment-detail", recruitmententry_id=rows[0]["id"])
    assert w.client().delete(one).status_code == 204
    assert RecruitmentEntry.objects.for_lab(w.lab).count() == 2
    assert len(audited("recruitment_entry.created", "recruitment_entry.deleted")) == 4


def test_recruitment_refuses_obvious_personal_data_and_bad_values(w):
    def entry(**extra):
        body = {"entry_date": "2030-02-01", "status": "screened", "count": 1, **extra}
        return post(w, "recruitment-list", body).status_code

    assert entry(notes="jane.doe@example.com called back") == 400
    assert entry(notes="two from the clinic list") == 201
    assert entry(status="bored") == 400
    assert entry(count=-1) == 400
    patch = w.client().patch(url(w, "recruitment-plan"), {"notes": "contact a@b.co"}, format="json")
    assert patch.status_code == 400


def test_recruitment_plan_hidden_across_labs(w):
    other = reverse(
        "provenance:recruitment-plan", kwargs={"lab_id": w.lab_b.pk, "project_id": w.project.pk}
    )
    assert w.client(w.pi_b).get(other).status_code == 404


# ---------------------------------------------------------------- deadline priority (D137)


def test_deadline_priority_default_edit_and_order(w):
    listing = reverse("projects:deadline-list", kwargs=pk(w))

    def mk(title, due, priority=None):
        body = {"title": title, "due_date": due, **({"priority": priority} if priority else {})}
        return w.client().post(listing, body, format="json")

    first = mk("plain", "2030-01-01")
    assert first.json()["priority"] == "medium"
    mk("low early", "2029-01-01", "low")
    mk("high late", "2031-01-01", "high")
    mk("high early", "2030-06-01", "high")
    order = [d["title"] for d in w.client().get(listing).json()]
    assert order == ["high early", "high late", "plain", "low early"]
    item = reverse(
        "projects:deadline-detail",
        kwargs={"lab_id": w.lab.pk, "projectdeadline_id": first.json()["id"]},
    )
    assert w.client().patch(item, {"priority": "low"}, format="json").json()["priority"] == "low"
    assert w.client().patch(item, {"priority": "urgent"}, format="json").status_code == 400
    saved = ProjectDeadline.objects.for_lab(w.lab).get(pk=first.json()["id"])
    assert saved.priority == DeadlinePriority.LOW


# ---------------------------------------------------------------- last activity (D139)


def test_last_activity_follows_signed_in_edits_only(w):
    contrib = w.member(ProjectRole.CONTRIBUTOR)
    detail = reverse("projects:project-detail", kwargs=pk(w))
    assert w.client().get(detail).json()["last_activity_at"] is None  # fixtures are made in code
    assert post(w, "review-list", {"title": "anything"}, contrib).status_code == 201
    after = w.client().get(detail).json()
    assert after["last_activity_by"]["id"] == str(contrib.pk) and after["last_activity_at"]
    # a read, and a save with no request behind it (a job), change nothing
    w.client().get(url(w, "review-list"))
    ReviewItem.objects.for_lab(w.lab).first().save()
    assert w.client().get(detail).json()["last_activity_by"]["id"] == str(contrib.pk)
    # an edit in another project never moves this one
    assert post(w, "review-list", {"title": "x"}, project=w.other).status_code == 201
    assert w.client().get(detail).json()["last_activity_by"]["id"] == str(contrib.pk)


def test_last_activity_counts_task_edits(w):
    contrib = w.member(ProjectRole.CONTRIBUTOR)
    resp = w.client(contrib).post(
        reverse("projects:task-list", kwargs=pk(w)), {"title": "T"}, format="json"
    )
    assert resp.status_code == 201, resp.content
    w.project.refresh_from_db()
    assert w.project.last_activity_by_id == contrib.pk


# ---------------------------------------------------------------- ethics tab filter (D134)


def test_ethics_list_filters_by_visible_project(w):
    from ethics.models import EthicsApproval

    def mk(number, project):
        EthicsApproval.objects.create(
            lab=w.lab,
            approval_number=number,
            board="REB",
            title=number,
            approval_date=date(2030, 1, 1),
            expiry_date=date(2031, 1, 1),
            created_by=w.pi,
        ).projects.add(project)

    mk("A-1", w.project)
    mk("A-2", w.other)
    listing = reverse("ethics:approval-list", kwargs={"lab_id": w.lab.pk})
    got = w.client().get(listing, {"project": str(w.project.pk)}).json()
    assert [a["approval_number"] for a in got] == ["A-1"]
    assert len(w.client().get(listing).json()) == 2
    assert w.client().get(listing, {"project": "nope"}).json() == []
    # a project the member cannot see reads as empty, never as "linked to something hidden"
    member = w.make_user()
    w.join(member, w.lab, LabRole.MEMBER)
    assert w.client(member).get(listing, {"project": str(w.project.pk)}).json() == []


# ---------------------------------------------------------------- search urls (D132)


def test_search_urls_point_at_workflow(w):
    from core.search import search

    post(w, "funding-list", {"funder": "Wellcome Trust"})
    ds = post(w, "dataset-list", {"name": "Wellcome data", "version_label": "v1"}).json()["id"]
    hits = {h["type"]: h for h in search(w.pi, w.lab, "Wellcome")}
    assert hits["funding"]["url"].endswith(f"/projects/{w.project.pk}/workflow/funding")
    assert hits["dataset"]["url"].endswith(f"/workflow/data/datasets/{ds}")


def test_a_non_pi_cannot_attach_a_pi_only_file_as_code(w):
    """Files are looked up as the file list shows them, so a hidden one reads as unknown."""
    lead = w.member(ProjectRole.LEAD)
    letter = _letter(w, pi_only=True)
    body = {"title": "A", "datasets": [], "code_attachment": str(letter.pk)}
    resp = post(w, "analysis-list", body, lead)
    assert resp.status_code == 400
    assert "code_attachment" in resp.json()
