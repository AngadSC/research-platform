"""Contribution graph on the PI dashboard: access, counting, per-person filter, isolation."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import DocumentRevision
from documents.services import create_document
from labs.contributions import WEEKS, grid_start
from labs.models import LabRole
from projects.models import ChatMessage, Project, ProjectMembership, ProjectRole, Task, TaskPost

pytestmark = pytest.mark.django_db


def api(user):
    c = APIClient()
    c.force_login(user)
    return c


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("A")
    pi, member = make_user(), make_user()
    join(pi, lab, LabRole.PI)
    join(member, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="P1", created_by=pi, status="active")
    ProjectMembership.objects.create(lab=lab, project=project, user=member, role=ProjectRole.LEAD)
    return dict(lab=lab, pi=pi, member=member, project=project)


def url(w, user=None):
    base = f"/api/labs/{w['lab'].pk}/contributions/"
    return f"{base}?user={user.pk}" if user else base


def get(w, user=None, as_user=None):
    resp = api(as_user or w["pi"]).get(url(w, user))
    assert resp.status_code == 200, resp.content
    return resp.json()


def task(w, by, **kw):
    return Task.objects.create(lab=w["lab"], project=w["project"], created_by=by, title="T", **kw)


def test_only_pi_and_admin(world, make_user, join):
    admin = make_user()
    join(admin, world["lab"], LabRole.LAB_ADMIN)
    assert api(admin).get(url(world)).status_code == 200
    assert api(world["member"]).get(url(world)).status_code == 403
    outsider = make_user()
    assert api(outsider).get(url(world)).status_code == 404
    assert APIClient().get(url(world)).status_code in (401, 403)


def test_grid_is_53_weeks_starting_on_a_sunday(world):
    data = get(world)
    today = timezone.localdate()
    start = grid_start(today)
    assert data["start"] == start.isoformat()
    assert data["end"] == today.isoformat()
    assert start.weekday() == 6  # Sunday
    assert (today - start).days < WEEKS * 7
    assert (today - start).days >= (WEEKS - 1) * 7


def test_counts_each_kind_for_the_lab_and_per_person(world):
    w = world
    t = task(w, w["member"])
    task(w, w["pi"])
    TaskPost.objects.create(lab=w["lab"], task=t, author=w["member"], body="update")
    ChatMessage.objects.create(lab=w["lab"], project=w["project"], author=w["member"], body="hi")
    doc = create_document(project=w["project"], user=w["member"], title="Notes", content=[])
    for v in (2, 3, 4):  # three saves of one document on one day count once
        DocumentRevision.objects.create(
            lab=w["lab"], document=doc, version=v, title="Notes", content=[], created_by=w["member"]
        )

    everyone = get(w)
    assert everyone["user_id"] is None
    # tasks: 2, task update: 1, chat: 1, documents: 1, records: the project itself (by the PI)
    assert everyone["by_kind"] == {
        "documents": 1,
        "files": 0,
        "tasks": 2,
        "task_updates": 1,
        "chat": 1,
        "records": 1,
    }
    assert everyone["total"] == 6
    assert len(everyone["days"]) == 1
    assert everyone["days"][0]["date"] == timezone.localdate().isoformat()
    assert everyone["days"][0]["count"] == 6

    member = get(w, w["member"])
    assert member["user_id"] == str(w["member"].pk)
    assert member["total"] == 4
    assert member["by_kind"]["tasks"] == 1
    assert member["by_kind"]["records"] == 0

    pi = get(w, w["pi"])
    assert pi["total"] == 2  # one task and the project


def test_days_are_split_and_old_activity_is_left_out(world):
    w = world
    too_old, last_week = task(w, w["member"]), task(w, w["member"])
    task(w, w["member"])  # today
    now = timezone.now()
    Task.objects.for_lab(w["lab"]).filter(pk=last_week.pk).update(
        created_at=now - timedelta(days=7)
    )
    Task.objects.for_lab(w["lab"]).filter(pk=too_old.pk).update(
        created_at=now - timedelta(days=WEEKS * 7 + 10)
    )
    data = get(w, w["member"])
    assert data["total"] == 2
    assert [d["date"] for d in data["days"]] == [
        (timezone.localdate() - timedelta(days=7)).isoformat(),
        timezone.localdate().isoformat(),
    ]


def test_other_labs_are_not_counted(world, make_lab, join):
    w = world
    other = make_lab("B")
    join(w["member"], other, LabRole.MEMBER)
    p2 = Project.objects.create(lab=other, name="P2", created_by=w["member"], status="active")
    Task.objects.create(lab=other, project=p2, created_by=w["member"], title="elsewhere")
    assert get(w, w["member"])["total"] == 0


def test_user_must_be_a_member(world, make_user):
    resp = api(world["pi"]).get(url(world, make_user()))
    assert resp.status_code == 400
    resp = api(world["pi"]).get(url(world) + "?user=not-an-id")
    assert resp.status_code == 400


def test_query_count_does_not_grow(world):
    w = world

    def count():
        with CaptureQueriesContext(connection) as ctx:
            get(w)
        return len(ctx.captured_queries)

    before = count()
    for _ in range(5):
        p = Project.objects.create(lab=w["lab"], name="More", created_by=w["pi"], status="active")
        Task.objects.create(lab=w["lab"], project=p, created_by=w["member"], title="x")
    assert count() == before
