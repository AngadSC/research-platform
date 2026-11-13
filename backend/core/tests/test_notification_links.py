"""Every notification links to what it is about, quoted messages read as plain text, and expiry
counts are worked out when shown, not when the reminder was made."""

import datetime
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import NotificationKind
from core.notifications import live_title, notify
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab = make_lab("Lab")
    author, member, outsider = (make_user(display_name=n) for n in ("Ann", "Ben", "Cat"))
    for u in (author, member, outsider):
        join(u, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="Alpha", created_by=author)
    for u in (author, member):
        ProjectMembership.objects.create(lab=lab, project=project, user=u, role=ProjectRole.LEAD)
    task = Task.objects.create(lab=lab, project=project, title="Run it", created_by=author)
    return dict(lab=lab, author=author, member=member, outsider=outsider, project=project,
                task=task)  # fmt: skip


def client(user):
    c = APIClient()
    c.force_login(user)
    return c


def inbox(w, user):
    r = client(user).get(f"/api/labs/{w['lab'].pk}/notifications/")
    assert r.status_code == 200
    return r.json()


def tag(user):
    return f"@[{user.display_name}](user:{user.pk})"


def test_mentions_link_to_their_message(w):
    lab, base = w["lab"], f"/labs/{w['lab'].pk}"
    me = client(w["author"])
    body = f"**bold** ~~gone~~ cc {tag(w['member'])}"
    assert me.post(f"/api/labs/{lab.pk}/chat/messages/", {"body": body}, "json").status_code == 201
    project_chat = f"/api/labs/{lab.pk}/projects/{w['project'].pk}/messages/"
    assert me.post(project_chat, {"body": body}, "json").status_code == 201
    task_posts = f"/api/labs/{lab.pk}/tasks/{w['task'].pk}/posts/"
    assert me.post(task_posts, {"body": body}, "json").status_code == 201
    urls = {n["url"] for n in inbox(w, w["member"])}
    assert urls == {
        f"{base}/chat",
        f"{base}/projects/{w['project'].pk}/chat",
        f"{base}/projects/{w['project'].pk}/tasks?task={w['task'].pk}",
    }
    assert {n["body"] for n in inbox(w, w["member"])} == {"bold gone cc @Ben"}


def test_a_task_link_never_names_a_project_the_reader_cannot_see(w):
    notify(
        lab=w["lab"],
        recipient=w["outsider"],
        kind=NotificationKind.TASK_UNASSIGNED,
        title="Task unassigned: Run it",
        target=w["task"],
        dedupe_key="t1",
    )
    [n] = inbox(w, w["outsider"])
    assert n["url"] == f"/labs/{w['lab'].pk}"


def test_expiry_count_is_worked_out_when_shown(w):
    """An old row said "expires in 24 days" when it was made; it now says what is true today."""
    expiry = timezone.localdate() + datetime.timedelta(days=20)
    notify(
        lab=w["lab"],
        recipient=w["member"],
        kind=NotificationKind.TRAINING_EXPIRY,
        title="Safety training expires in 24 days",
        target=w["task"],  # any row: the training page is the link for every training reminder
        dedupe_key=f"training:x:30:{expiry.isoformat()}",
    )
    [n] = inbox(w, w["member"])
    assert n["title"] == "Safety training expires in 20 days"
    assert n["url"] == f"/labs/{w['lab'].pk}/training"
    past = (timezone.localdate() - datetime.timedelta(days=3)).isoformat()
    row = SimpleNamespace(
        kind=NotificationKind.ETHICS_EXPIRY,
        title="Ethics approval A-1 expires today",
        dedupe_key=f"ethics:x:7:{past}",
    )
    assert live_title(row) == "Ethics approval A-1 expired 3 days ago"
