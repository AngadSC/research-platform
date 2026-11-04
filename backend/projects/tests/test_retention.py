"""Retention review (SPEC phase 5): the daily job only notifies; nothing is ever deleted."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification
from documents.models import Document
from documents.services import create_document, delete_document
from labs.models import LabRole
from projects.jobs import retention_scan
from projects.models import Project, ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def day(n):
    return timezone.localdate() + datetime.timedelta(days=n)


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    lab = make_lab("A")
    u = {name: make_user() for name in ["pi", "admin", "lead", "contrib", "other_pi"]}
    join(u["pi"], lab, LabRole.PI)
    join(u["admin"], lab, LabRole.LAB_ADMIN)
    join(u["lead"], lab, LabRole.MEMBER)
    join(u["contrib"], lab, LabRole.MEMBER)
    join(u["other_pi"], make_lab("B"), LabRole.PI)
    overdue = make_project(lab, "Overdue", retain_until=day(-10), retention_note="keep 7 years")
    future = make_project(lab, "Future", retain_until=day(30))
    unset = make_project(lab, "Unset")
    gone = make_project(lab, "Gone", retain_until=day(-1), deleted_at=timezone.now())
    for name, role in [("lead", ProjectRole.LEAD), ("contrib", ProjectRole.CONTRIBUTOR)]:
        ProjectMembership.objects.create(lab=lab, project=overdue, user=u[name], role=role)
    docs = {}
    for name, project, retain in [
        ("old doc", overdue, day(-5)),
        ("fresh doc", overdue, day(5)),
        ("plain doc", unset, None),
        ("doc in deleted project", gone, day(-2)),
    ]:
        doc = create_document(project=project, user=u["pi"], title=name, content=[])
        Document.objects.for_lab(lab).filter(pk=doc.pk).update(retain_until=retain)
        docs[name] = doc
    soft = create_document(project=unset, user=u["pi"], title="deleted doc", content=[])
    Document.objects.for_lab(lab).filter(pk=soft.pk).update(retain_until=day(-3))
    delete_document(soft, user=u["pi"])
    docs["deleted doc"] = soft
    return lab, u, docs, {"overdue": overdue, "future": future, "gone": gone, "unset": unset}


def snapshot(lab):
    return (
        list(Project.objects.for_lab(lab).order_by("pk").values()),
        list(Document.objects.for_lab(lab).order_by("pk").values()),
    )


def test_scan_notifies_pis_about_the_right_items_and_changes_nothing_else(w):
    lab, u, docs, projects = w
    before = snapshot(lab)
    notifications_before = Notification.objects.for_lab(lab).count()
    created = retention_scan()
    assert snapshot(lab) == before  # not one project or document field changed or went away
    assert Notification.objects.for_lab(lab).count() == notifications_before + created
    per_user = {}
    for n in Notification.objects.for_lab(lab).all():
        per_user.setdefault(n.recipient_id, []).append(n)
    # pi and lab_admin review retention; the project lead and the other lab's PI do not
    assert set(per_user) == {u["pi"].pk, u["admin"].pk}
    expected_ids = {
        projects["overdue"].pk,
        projects["gone"].pk,
        docs["old doc"].pk,
        docs["doc in deleted project"].pk,
        docs["deleted doc"].pk,
    }
    for notes in per_user.values():
        assert {n.target_id for n in notes} == expected_ids
        assert all(n.kind == "retention_due" for n in notes)
    by_target = {n.target_id: n for n in per_user[u["pi"].pk]}
    for flagged in (projects["gone"], docs["deleted doc"], docs["doc in deleted project"]):
        assert "(deleted)" in by_target[flagged.pk].title
    assert "(deleted)" not in by_target[projects["overdue"].pk].title
    assert "keep 7 years" in by_target[projects["overdue"].pk].body


def test_scan_twice_does_not_duplicate_and_a_new_date_renotifies(w):
    lab, u, docs, projects = w
    assert retention_scan() == 10  # five items for each of the pi and the lab_admin
    assert retention_scan() == 0
    Project.objects.for_lab(lab).filter(pk=projects["overdue"].pk).update(retain_until=day(-2))
    assert retention_scan() == 2  # the changed date, for the pi and the lab_admin


def test_scan_with_nothing_overdue_does_nothing(make_lab, make_user, join, make_project):
    lab, pi = make_lab(), make_user()
    join(pi, lab, LabRole.PI)
    make_project(lab, retain_until=day(1))
    assert retention_scan() == 0


def due(client, lab):
    return client.get(reverse("projects:retention-due", kwargs={"lab_id": lab.pk}))


def test_due_endpoint_lists_overdue_items_with_deleted_flags(w):
    lab, u, docs, projects = w
    client = APIClient()
    client.force_login(u["pi"])
    rows = due(client, lab).json()
    got = {(r["kind"], r["name"]): r["deleted_at"] is not None for r in rows}
    assert got == {
        ("project", "Overdue"): False,
        ("project", "Gone"): True,
        ("document", "old doc"): False,
        ("document", "doc in deleted project"): False,
        ("document", "deleted doc"): True,
    }
    assert [r["retain_until"] for r in rows] == sorted(r["retain_until"] for r in rows)
    assert next(r for r in rows if r["name"] == "Overdue")["retention_note"] == "keep 7 years"
    client.force_login(u["lead"])
    assert due(client, lab).status_code == 403
    client.force_login(u["other_pi"])
    assert due(client, lab).status_code == 404


def test_document_retention_is_exposed_and_only_view_retention_can_set_it(w):
    lab, u, docs, projects = w
    doc = docs["old doc"]  # in the "Overdue" project: lead and contrib are on it
    detail = reverse("documents:document-detail", kwargs={"lab_id": lab.pk, "document_id": doc.pk})
    put = {"title": "t", "content": [], "base_version": doc.version}
    retention = {"retain_until": str(day(400)), "retention_note": "keep"}
    contrib = APIClient()
    contrib.force_login(u["contrib"])
    assert contrib.put(detail, {**put, **retention}, format="json").status_code == 403
    assert contrib.put(detail, put, format="json").status_code == 200  # content is fine
    lead = APIClient()
    lead.force_login(u["lead"])
    # D55: a project lead without view_retention is refused too
    assert (
        lead.put(
            detail, {**put, "base_version": doc.version + 1, **retention}, format="json"
        ).status_code
        == 403
    )
    lead.force_login(u["pi"])  # a pi holds view_retention
    resp = lead.put(detail, {**put, "base_version": doc.version + 1, **retention}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["retain_until"] == str(day(400)) and resp.json()["retention_note"] == "keep"
    assert lead.get(detail).json()["retain_until"] == str(day(400))
    # a later content-only save leaves retention alone
    assert contrib.put(detail, {**put, "base_version": doc.version + 2}, "json").status_code == 200
    assert Document.objects.for_lab(lab).get(pk=doc.pk).retention_note == "keep"
