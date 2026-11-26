"""The notification list re-checks every row (D54) with a flat number of queries."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification, NotificationKind
from core.notifications import notification_url, notify, visible_notifications
from documents import services as doc_services
from ethics.models import EthicsApproval
from labs.models import LabRole, Meeting
from projects.models import Project, ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab = make_lab()
    pi, sam = make_user(), make_user()
    join(pi, lab, LabRole.PI)
    join(sam, lab, LabRole.MEMBER)
    return lab, pi, sam


def _project(lab, pi, sam, name):
    project = Project.objects.create(lab=lab, name=name, created_by=pi)
    ProjectMembership.objects.create(lab=lab, project=project, user=sam, role=ProjectRole.LEAD)
    return project


def _add(lab, pi, sam, start, count):
    """`count` notices for sam, each on a new target in its own project, of five kinds."""
    for i in range(start, start + count):
        project = _project(lab, pi, sam, f"P{i}")
        if i % 5 == 0:
            kind, target = NotificationKind.PROJECT_ROLE, project
        elif i % 5 == 1:
            kind = NotificationKind.TASK_ASSIGNED
            target = Task.objects.create(lab=lab, project=project, title=f"T{i}", created_by=pi)
        elif i % 5 == 2:
            kind = NotificationKind.DOCUMENT_COMMENT
            target = doc_services.create_document(
                project=project, user=pi, title=f"D{i}", content=[]
            )
        elif i % 5 == 3:
            kind, target = NotificationKind.MEETING_INVITE, _meeting(lab, pi, sam, i)
        else:
            kind, target = NotificationKind.ETHICS_EXPIRY, _approval(lab, pi, project, i)
        notify(lab=lab, recipient=sam, kind=kind, title=f"N{i}", target=target, dedupe_key=f"q:{i}")


def _meeting(lab, pi, sam, i):
    meeting = Meeting.objects.create(
        lab=lab,
        created_by=pi,
        title=f"M{i}",
        starts_at="2030-01-01T14:00:00Z",
        ends_at="2030-01-01T15:00:00Z",
    )
    meeting.attendees.set([pi, sam])
    return meeting


def _approval(lab, pi, project, i):
    approval = EthicsApproval.objects.create(
        lab=lab,
        approval_number=f"E{i}",
        board="B",
        title=f"A{i}",
        approval_date="2025-01-01",
        expiry_date="2030-01-01",
        restricted=i == 4,  # restricted ones cost a query each for non-leads (_sees_restricted)
        created_by=pi,
    )
    approval.projects.add(project)
    return approval


def _list_queries(lab, sam):
    client = APIClient()
    client.force_login(sam)
    url = reverse("core:notification-list", kwargs={"lab_id": lab.pk})
    client.get(url)  # warm up the session and login
    with CaptureQueriesContext(connection) as ctx:
        rows = client.get(url).json()
    return len(ctx), len(rows)


def test_list_query_count_is_flat(w):
    lab, pi, sam = w
    _add(lab, pi, sam, 0, 5)
    few, shown = _list_queries(lab, sam)
    assert shown == 5
    _add(lab, pi, sam, 5, 45)
    many, shown = _list_queries(lab, sam)
    assert shown == 50
    assert many == few


def test_visibility_deleted_lost_and_normal(w):
    lab, pi, sam = w
    kept, lost, gone_doc, gone_task = (_project(lab, pi, sam, n) for n in "KLDT")
    task = Task.objects.create(lab=lab, project=kept, title="ok", created_by=pi)
    lost_task = Task.objects.create(lab=lab, project=lost, title="lost", created_by=pi)
    doc = doc_services.create_document(project=gone_doc, user=pi, title="D", content=[])
    dead = Task.objects.create(lab=lab, project=gone_task, title="dead", created_by=pi)
    for key, target in [("ok", task), ("lost", lost_task), ("doc", doc), ("dead", dead)]:
        notify(
            lab=lab,
            recipient=sam,
            kind=NotificationKind.TASK_ASSIGNED,
            title=key,
            target=target,
            dedupe_key=key,
        )
    qs = Notification.objects.for_lab(lab).filter(recipient=sam).order_by("title")
    assert [n.title for n in visible_notifications(sam, lab, qs)] == ["dead", "doc", "lost", "ok"]

    ProjectMembership.objects.for_lab(lab).filter(project=lost, user=sam).delete()
    doc.deleted_at = timezone.now()
    doc.save(update_fields=["deleted_at"])
    dead.delete()
    shown = visible_notifications(sam, lab, qs)
    assert [n.title for n in shown] == ["ok"]
    assert (
        notification_url(shown[0], sam) == f"/labs/{lab.pk}/projects/{kept.pk}/tasks?task={task.pk}"
    )
    # a page smaller than the rows still finds the visible ones further down
    assert [n.title for n in visible_notifications(sam, lab, qs, limit=1)] == ["ok"]
