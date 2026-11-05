"""Training: privacy, compliance statuses, reminders, attachments, cross-lab (D175-D179)."""

import datetime
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from documents.models import Attachment
from labs.admin_serializers import OnboardingItemSerializer
from labs.models import Lab, LabRole, OnboardingItem
from training import jobs, services
from training.models import AppliesTo, TrainingRecord, TrainingRequirement

pytestmark = pytest.mark.django_db
TODAY = datetime.date(2030, 6, 15)
D = datetime.timedelta
NOW = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)


@pytest.fixture
def world(make_lab, make_user, join, monkeypatch):
    lab = make_lab("T Lab")
    # The jobs walk every lab. The permission matrix keeps a committed world (with training
    # rows and managers) for the whole session, so counts here must look at this lab only.
    monkeypatch.setattr(jobs, "Lab", SimpleNamespace(objects=Lab.objects.filter(pk=lab.pk)))
    users = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("admin", LabRole.LAB_ADMIN),
        ("ann", LabRole.MEMBER),
        ("bob", LabRole.MEMBER),
        ("vic", LabRole.VIEWER),
    ]:
        users[name] = make_user(display_name=name.title())
        join(users[name], lab, role)
    return lab, users


def api(user):
    c = APIClient()
    c.force_login(user)
    return c


def url(lab, path=""):
    return f"/api/labs/{lab.pk}/training/{path}"


def req(lab, name="WHMIS", months=12, **kw):
    return TrainingRequirement.objects.create(
        lab=lab, name=name, category="safety", validity_months=months, **kw
    )


def rec(lab, user, requirement, completed, expires="auto"):
    if expires == "auto":
        expires = services.computed_expiry(requirement, completed)
    return TrainingRecord.objects.create(
        lab=lab, requirement=requirement, user=user, completed_on=completed, expires_on=expires
    )


def pdf(name="cert.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 cert", content_type="application/pdf")


def cert_body(name="cert.pdf"):
    return {"file": pdf(name), "acknowledged_notice": "true"}


# ---------------------------------------------------------------- dates and statuses


def test_add_months_clamps_to_month_end():
    assert services.add_months(datetime.date(2030, 1, 31), 1) == datetime.date(2030, 2, 28)
    assert services.add_months(datetime.date(2030, 11, 30), 3) == datetime.date(2031, 2, 28)


def test_expiry_computed_on_create_and_editable(world):
    lab, u = world
    r = req(lab, months=24)
    c = api(u["ann"])
    body = {"requirement": str(r.pk), "completed_on": "2030-01-31"}
    made = c.post(url(lab, "records/"), body, "json")
    assert made.status_code == 201 and made.json()["expires_on"] == "2032-01-31"
    custom = c.post(url(lab, "records/"), {**body, "expires_on": "2030-12-01"}, "json")
    assert custom.json()["expires_on"] == "2030-12-01"
    never = req(lab, "Ethics", months=None)
    n = c.post(url(lab, "records/"), {**body, "requirement": str(never.pk)}, "json")
    assert n.json()["expires_on"] is None
    bad = c.post(url(lab, "records/"), {**body, "expires_on": "2029-01-01"}, "json")
    assert bad.status_code == 400


def test_compliance_statuses(world):
    lab, u = world
    w, never = req(lab, "WHMIS"), req(lab, "TCPS 2", months=None)
    rec(lab, u["ann"], w, TODAY - D(days=30), expires=TODAY + D(days=61))  # done
    rec(lab, u["bob"], w, TODAY - D(days=300), expires=TODAY + D(days=60))  # expiring (boundary)
    rec(lab, u["pi"], w, TODAY - D(days=400), expires=TODAY - D(days=1))  # expired
    rec(lab, u["ann"], never, TODAY - D(days=3000), expires=None)  # never expires: done
    data = services.compliance(lab, today=TODAY)
    cell = {
        (row["user"].display_name, r.name): row["cells"][str(r.pk)]["status"]
        for row in data["members"]
        for r in data["requirements"]
    }
    assert cell[("Ann", "WHMIS")] == "done" and cell[("Ann", "TCPS 2")] == "done"
    assert cell[("Bob", "WHMIS")] == "expiring" and cell[("Bob", "TCPS 2")] == "missing"
    assert cell[("Pi", "WHMIS")] == "expired" and cell[("Admin", "WHMIS")] == "missing"
    assert data["summary"] == {"done": 2, "expiring": 1, "expired": 1, "missing": 6}


def test_latest_record_counts_and_deleted_ignored(world):
    lab, u = world
    w = req(lab)
    rec(lab, u["ann"], w, TODAY - D(days=500))  # old, expired
    new = rec(lab, u["ann"], w, TODAY - D(days=10))
    cells = services.compliance(lab, today=TODAY, user=u["ann"])["members"][0]["cells"]
    assert cells[str(w.pk)]["status"] == "done"
    new.deleted_at = NOW
    new.save()
    cells = services.compliance(lab, today=TODAY, user=u["ann"])["members"][0]["cells"]
    assert cells[str(w.pk)]["status"] == "expired"


def test_applies_to_roles_and_projects(world, make_project):
    from projects.models import ProjectMembership

    lab, u = world
    roles = req(lab, "Roles", applies_to=AppliesTo.ROLES, roles=["member"])
    by_project = req(lab, "Biosafety", applies_to=AppliesTo.PROJECTS)
    project = make_project(lab)
    by_project.projects.add(project)
    ProjectMembership.objects.create(lab=lab, project=project, user=u["bob"], role="contributor")
    members = {
        r["user"].display_name: r["cells"] for r in services.compliance(lab, today=TODAY)["members"]
    }
    assert members["Ann"][str(roles.pk)] and members["Pi"][str(roles.pk)] is None
    assert members["Bob"][str(by_project.pk)] and members["Ann"][str(by_project.pk)] is None


def test_expiring_endpoint(world):
    lab, u = world
    w = req(lab)
    today = datetime.date.today()
    rec(lab, u["ann"], w, today, expires=today + D(days=20))
    rec(lab, u["bob"], w, today, expires=today + D(days=90))
    rec(lab, u["pi"], w, today - D(days=400), expires=today - D(days=2))
    body = api(u["pi"]).get(url(lab, "expiring/?days=60")).json()
    assert [i["status"] for i in body["items"]] == ["expired", "expiring"]
    assert body["count"] == 2 and body["expired_count"] == 1 and body["days"] == 60
    assert api(u["pi"]).get(url(lab, "expiring/?days=0")).status_code == 400
    assert api(u["ann"]).get(url(lab, "expiring/")).status_code == 403


# ---------------------------------------------------------------- privacy


def test_members_cannot_see_each_others_records(world):
    lab, u = world
    w = req(lab)
    mine, theirs = rec(lab, u["ann"], w, TODAY), rec(lab, u["bob"], w, TODAY)
    c = api(u["ann"])
    assert [r["id"] for r in c.get(url(lab, "records/")).json()] == [str(mine.pk)]
    assert c.get(url(lab, f"records/?user={u['bob'].pk}")).json() == []
    path = url(lab, f"records/{theirs.pk}/")
    assert c.get(path).status_code == 404
    assert c.patch(path, {"notes": "x"}, "json").status_code == 404
    assert c.delete(path).status_code == 404
    assert c.get(path + "certificate/").status_code == 404
    assert c.post(path + "certificate/", cert_body()).status_code == 404
    assert c.post(path + "verify/").status_code == 403
    assert c.get(url(lab, "compliance/")).status_code == 403
    assert len(c.get(url(lab, "my/")).json()["members"]) == 1
    # a member cannot file a record in someone else's name
    body = {"requirement": str(w.pk), "completed_on": "2030-01-01", "user": str(u["bob"].pk)}
    assert c.post(url(lab, "records/"), body, "json").status_code == 403


def test_managers_see_and_verify_everyone(world):
    lab, u = world
    w = req(lab)
    r = rec(lab, u["ann"], w, TODAY)
    for who in ("pi", "admin"):
        c = api(u[who])
        assert len(c.get(url(lab, "records/")).json()) == 1
        assert c.get(url(lab, "compliance/")).status_code == 200
    done = api(u["admin"]).post(url(lab, f"records/{r.pk}/verify/"))
    assert done.status_code == 200 and done.json()["verified_by"]["display_name"] == "Admin"
    event = AuditEvent.objects.get(action=AuditAction.TRAINING_RECORD_VERIFIED)
    assert event.actor == u["admin"] and event.target_id == r.pk
    # a manager can file for a member
    body = {"requirement": str(w.pk), "completed_on": "2030-01-01", "user": str(u["bob"].pk)}
    assert api(u["pi"]).post(url(lab, "records/"), body, "json").status_code == 201


def test_edit_clears_verification_and_delete_rules(world):
    lab, u = world
    r = rec(lab, u["ann"], req(lab), TODAY)
    api(u["pi"]).post(url(lab, f"records/{r.pk}/verify/"))
    c = api(u["ann"])
    assert c.patch(url(lab, f"records/{r.pk}/"), {"notes": "n"}, "json").json()["verified_at"]
    out = c.patch(url(lab, f"records/{r.pk}/"), {"expires_on": "2031-01-01"}, "json").json()
    assert out["verified_at"] is None  # the dates changed: the sign-off no longer applies
    api(u["pi"]).post(url(lab, f"records/{r.pk}/verify/"))
    assert c.delete(url(lab, f"records/{r.pk}/")).status_code == 403  # verified: manager only
    assert api(u["pi"]).delete(url(lab, f"records/{r.pk}/")).status_code == 204
    assert AuditEvent.objects.filter(action=AuditAction.TRAINING_RECORD_DELETED).count() == 1
    assert TrainingRecord.objects.for_lab(lab).get(pk=r.pk).deleted_at is not None


def test_requirement_permissions_and_delete_guard(world):
    lab, u = world
    body = {"name": "WHMIS", "category": "safety", "validity_months": 36, "url": "https://x.org/"}
    assert api(u["ann"]).post(url(lab, "requirements/"), body, "json").status_code == 403
    made = api(u["pi"]).post(url(lab, "requirements/"), body, "json")
    assert made.status_code == 201
    assert api(u["pi"]).post(url(lab, "requirements/"), body, "json").status_code == 400  # dup
    assert api(u["vic"]).get(url(lab, "requirements/")).status_code == 200
    bad = {**body, "name": "B", "url": "javascript:alert(1)"}
    assert api(u["pi"]).post(url(lab, "requirements/"), bad, "json").status_code == 400
    roles = {**body, "name": "R", "applies_to": "roles"}
    assert api(u["pi"]).post(url(lab, "requirements/"), roles, "json").status_code == 400
    r = TrainingRequirement.objects.for_lab(lab).get(name="WHMIS")
    rec(lab, u["ann"], r, TODAY)
    assert api(u["pi"]).delete(url(lab, f"requirements/{r.pk}/")).status_code == 409


# ---------------------------------------------------------------- cross-lab


def test_cross_lab_ids_are_unknown(world, make_lab, make_user, join):
    lab, u = world
    other = make_lab("Other")
    boss = make_user()
    join(boss, other, LabRole.PI)
    foreign_req = req(other, "Secret")
    foreign_rec = rec(other, boss, foreign_req, TODAY)
    body = {"requirement": str(foreign_req.pk), "completed_on": "2030-01-01"}
    assert api(u["ann"]).post(url(lab, "records/"), body, "json").status_code == 400
    assert api(u["pi"]).get(url(lab, f"records/{foreign_rec.pk}/")).status_code == 404
    item = {"kind": "new_member", "title": "T", "training_requirement": str(foreign_req.pk)}
    resp = api(u["pi"]).post(f"/api/labs/{lab.pk}/onboarding-items/", item, "json")
    assert resp.status_code == 400
    # The app (or the DB) refuses another lab's training.
    with pytest.raises(Exception):  # noqa: B017
        with transaction.atomic():
            TrainingRecord.objects.create(
                lab=lab, requirement=foreign_req, user=u["ann"], completed_on=TODAY
            )


# ---------------------------------------------------------------- certificates (D175)


def test_certificate_rule_and_access(world, make_project):
    lab, u = world
    r = rec(lab, u["ann"], req(lab), TODAY)
    api(u["pi"]).post(url(lab, f"records/{r.pk}/verify/"))
    c = api(u["ann"])
    up = c.post(url(lab, f"records/{r.pk}/certificate/"), cert_body())
    assert up.status_code == 201
    assert api(u["pi"]).get(url(lab, f"records/{r.pk}/")).json()["verified_at"] is None
    first = Attachment.objects.for_lab(lab).get(training_record=r)
    assert c.get(url(lab, f"records/{r.pk}/certificate/")).status_code == 200
    assert api(u["pi"]).get(url(lab, f"records/{r.pk}/certificate/")).status_code == 200
    assert api(u["bob"]).get(url(lab, f"records/{r.pk}/certificate/")).status_code == 404
    # the generic attachment route never serves it, even to a PI
    generic = f"/api/labs/{lab.pk}/attachments/{first.pk}/download/"
    assert api(u["pi"]).get(generic).status_code == 404
    # replacing keeps the old file, soft-deleted
    c.post(url(lab, f"records/{r.pk}/certificate/"), cert_body("b.pdf"))
    first.refresh_from_db()
    assert first.deleted_at is not None
    assert Attachment.objects.for_lab(lab).filter(training_record=r, deleted_at=None).count() == 1
    assert c.post(url(lab, f"records/{r.pk}/certificate/"), {"file": pdf()}).status_code == 400
    # exactly one owner (D38): a project and a training record together is refused by the DB
    project = make_project(lab)
    common = {
        "lab": lab,
        "original_filename": "f",
        "content_type": "a/b",
        "size_bytes": 1,
        "sha256": "0" * 64,
        "uploaded_by": u["ann"],
        "notice_acknowledged_at": NOW,
    }
    with pytest.raises(IntegrityError), transaction.atomic():
        Attachment.objects.create(storage_key="k", project=project, training_record=r, **common)
    with pytest.raises(IntegrityError), transaction.atomic():
        Attachment.objects.create(storage_key="k2", **common)  # no owner at all


# ---------------------------------------------------------------- reminders (D178)


def run_at(monkeypatch, day, job):
    monkeypatch.setattr("training.jobs.timezone.localdate", lambda: day)
    return job()


@pytest.mark.parametrize(
    ("days", "threshold"),
    [(61, None), (60, 60), (31, 60), (30, 30), (8, 30), (7, 7), (1, 7), (0, 0), (-9, 0)],
)
def test_threshold_for(days, threshold):
    assert jobs.threshold_for(days) == threshold


def test_reminders_dedupe_and_tightest(
    world, monkeypatch, mailoutbox, django_capture_on_commit_callbacks
):
    lab, u = world
    r = rec(lab, u["ann"], req(lab), TODAY - D(days=300), expires=TODAY + D(days=60))
    send = jobs.send_expiry_reminders
    with django_capture_on_commit_callbacks(execute=True):
        assert run_at(monkeypatch, TODAY, send) == 1
        assert run_at(monkeypatch, TODAY, send) == 0  # same day, same key
        assert run_at(monkeypatch, TODAY + D(days=10), send) == 0  # still the 60-day band
        assert run_at(monkeypatch, TODAY + D(days=31), send) == 1  # 29 days left: 30
        # a missed run: only the tightest threshold crossed is sent
        assert run_at(monkeypatch, TODAY + D(days=58), send) == 1  # 2 days left: 7
        assert run_at(monkeypatch, TODAY + D(days=60), send) == 1  # on the day: 0
        assert run_at(monkeypatch, TODAY + D(days=75), send) == 0  # expired: same key
    notes = Notification.objects.for_lab(lab).filter(recipient=u["ann"])
    assert notes.count() == 4
    assert set(notes.values_list("kind", flat=True)) == {NotificationKind.TRAINING_EXPIRY}
    assert set(notes.values_list("target_id", flat=True)) == {r.pk}
    assert len(mailoutbox) == 4 and mailoutbox[0].to == [u["ann"].email]  # D178: emailed
    assert not Notification.objects.for_lab(lab).exclude(recipient=u["ann"]).exists()


def test_no_reminder_for_never_expires_or_superseded(world, monkeypatch):
    lab, u = world
    never = req(lab, "TCPS 2", months=None)
    rec(lab, u["ann"], never, TODAY - D(days=4000), expires=None)
    w = req(lab)
    rec(lab, u["bob"], w, TODAY - D(days=400), expires=TODAY - D(days=35))  # old, then renewed
    rec(lab, u["bob"], w, TODAY - D(days=5), expires=TODAY + D(days=360))
    assert run_at(monkeypatch, TODAY, jobs.send_expiry_reminders) == 0


def test_deactivated_member_gets_nothing(world, monkeypatch):
    lab, u = world
    rec(lab, u["ann"], req(lab), TODAY, expires=TODAY + D(days=5))
    u["ann"].is_active = False
    u["ann"].save()
    assert run_at(monkeypatch, TODAY, jobs.send_expiry_reminders) == 0


def test_weekly_digest(world, monkeypatch, mailoutbox, django_capture_on_commit_callbacks):
    lab, u = world
    rec(lab, u["ann"], req(lab), TODAY - D(days=400), expires=TODAY - D(days=3))
    send = jobs.send_weekly_digest
    with django_capture_on_commit_callbacks(execute=True):
        assert run_at(monkeypatch, TODAY, send) == 2  # pi and lab_admin only
        assert run_at(monkeypatch, TODAY + D(days=1), send) == 0  # same ISO week
        assert run_at(monkeypatch, TODAY + D(days=7), send) == 2  # next week
    note = Notification.objects.for_lab(lab).filter(recipient=u["pi"]).first()
    assert note.kind == NotificationKind.TRAINING_DIGEST
    assert "Ann: WHMIS (expired 2030-06-12)" in note.body and "Bob: WHMIS (missing)" in note.body
    assert not Notification.objects.for_lab(lab).filter(recipient=u["ann"]).exists()
    assert len(mailoutbox) == 4


def test_digest_silent_when_nothing_required(world, monkeypatch):
    lab, _ = world
    assert run_at(monkeypatch, TODAY, jobs.send_weekly_digest) == 0


# ---------------------------------------------------------------- onboarding tie-in (D179)


def test_onboarding_item_reports_training_done(world):
    lab, u = world
    w = req(lab)
    today = datetime.date.today()
    rec(lab, u["ann"], w, today - D(days=5))  # current
    rec(lab, u["bob"], w, today - D(days=500), expires=today - D(days=100))  # expired
    made = api(u["pi"]).post(
        f"/api/labs/{lab.pk}/onboarding-items/",
        {"kind": "new_member", "title": "Do WHMIS", "training_requirement": str(w.pk)},
        "json",
    )
    assert made.status_code == 201
    body = made.json()
    assert body["training_requirement_name"] == "WHMIS"
    assert body["training_done_user_ids"] == [str(u["ann"].pk)]
    assert body["completed_user_ids"] == []  # derived, never written (D179)
    # deleting a training nobody has a record for un-links the item instead of deleting it
    spare = req(lab, "Spare")
    item = OnboardingItem(lab=lab, kind="new_member", title="Spare", training_requirement=spare)
    item.save()
    assert api(u["pi"]).delete(url(lab, f"requirements/{spare.pk}/")).status_code == 204
    item = OnboardingItem.objects.for_lab(lab).get(pk=item.pk)
    assert OnboardingItemSerializer(item).data["training_requirement"] is None
