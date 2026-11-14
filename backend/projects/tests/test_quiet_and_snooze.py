"""Quiet hours and snoozing a task (D299)."""

import datetime
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.cache import cache

from core.models import Notification, NotificationKind
from core.notifications import notify
from core.quiet import in_quiet_hours, quiet_release
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db

UTC = datetime.UTC


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Lab")
    student = make_user(email="sam@example.com")
    join(student, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="Paper 2", created_by=student)
    ProjectMembership.objects.create(project=project, user=student, role=ProjectRole.CONTRIBUTOR)
    return lab, student, project


def task(project, user, title, due, **kw):
    return Task.objects.create(
        project=project, title=title, assignee=user, due_date=due, created_by=user, **kw
    )


def test_quiet_hours_cross_midnight_and_hold_until_they_end(make_user):
    user = make_user()
    user.preferences = {
        "quiet": "on",
        "quiet_start": "22",
        "quiet_end": "7",
        "time_zone": "America/Toronto",
    }
    zone = ZoneInfo("America/Toronto")
    late = datetime.datetime(2027, 3, 3, 23, 30, tzinfo=zone)
    early = datetime.datetime(2027, 3, 4, 6, 0, tzinfo=zone)
    midday = datetime.datetime(2027, 3, 4, 12, 0, tzinfo=zone)
    assert in_quiet_hours(user, late) and in_quiet_hours(user, early)
    assert not in_quiet_hours(user, midday)
    assert quiet_release(user, late) == datetime.datetime(2027, 3, 4, 7, 0, tzinfo=zone)
    assert quiet_release(user, early) == datetime.datetime(2027, 3, 4, 7, 0, tzinfo=zone)
    assert quiet_release(user, midday) is None


def test_an_emailed_notice_is_held_in_quiet_hours_but_still_shows_in_the_app(
    world, monkeypatch, django_capture_on_commit_callbacks
):
    lab, student, _ = world
    student.preferences = {"quiet": "on", "quiet_start": "0", "quiet_end": "23"}  # always quiet
    student.save()
    held = []
    from core import email

    monkeypatch.setattr(
        email.send_email_task, "apply_async", lambda **kw: held.append(kw["eta"]), raising=False
    )
    with django_capture_on_commit_callbacks(execute=True):
        notify(
            lab=lab,
            recipient=student,
            kind=NotificationKind.ETHICS_EXPIRY,
            title="Ethics expiring",
            dedupe_key="quiet-test",
        )
    assert (
        Notification.objects.for_lab(lab)
        .filter(recipient=student, dedupe_key="quiet-test")
        .exists()
    )
    assert len(held) == 1 and held[0] is not None
    assert mail.outbox == []


def test_snooze_is_a_task_field_you_can_set(world):
    from rest_framework.test import APIClient

    lab, student, project = world
    t = task(project, student, "Email Dr. B", datetime.date(2027, 3, 3))
    client = APIClient()
    client.force_authenticate(student)
    resp = client.patch(
        f"/api/labs/{lab.pk}/tasks/{t.pk}/", {"snoozed_until": "2027-03-08"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.json()["snoozed_until"] == "2027-03-08"
    mine = client.get(f"/api/labs/{lab.pk}/my-tasks/").json()
    assert mine[0]["snoozed_until"] == "2027-03-08"
    assert mine[0]["project_color"]
