"""D255: @mentions in chat messages and task updates tell the people who may read them."""

import pytest
from rest_framework.test import APIClient

from core.models import Notification, NotificationKind
from core.notifications import MAX_MENTIONS, visible_notifications
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab, other = make_lab("Lab"), make_lab("Other Lab")
    author, member, nonmember, stranger = (make_user(display_name=n) for n in "ABCD")
    for u in (author, member, nonmember):
        join(u, lab, LabRole.MEMBER)
    join(stranger, other, LabRole.PI)
    project = Project.objects.create(lab=lab, name="Alpha", created_by=author)
    for u in (author, member):
        ProjectMembership.objects.create(lab=lab, project=project, user=u, role=ProjectRole.LEAD)
    task = Task.objects.create(lab=lab, project=project, title="Run it", created_by=author)
    return dict(lab=lab, author=author, member=member, nonmember=nonmember,
                stranger=stranger, project=project, task=task)  # fmt: skip


def say(user, path, body):
    c = APIClient()
    c.force_login(user)
    return c.post(path, {"body": body}, "json")


def tag(user):
    return f"@[{user.display_name}](user:{user.pk})"


def mentions(w, user):
    """Mentions land in the lab of the conversation, so a lab-scoped read sees them all."""
    qs = Notification.objects.for_lab(w["lab"])
    return list(qs.filter(recipient=user, kind=NotificationKind.MENTION))


def project_chat(w):
    return f"/api/labs/{w['lab'].pk}/projects/{w['project'].pk}/messages/"


def test_project_chat_mention_notifies_a_member(w):
    r = say(w["author"], project_chat(w), f"hi {tag(w['member'])}, look")
    assert r.status_code == 201
    [n] = mentions(w, w["member"])
    assert n.title == "A mentioned you in the chat of Alpha"
    assert n.body == "hi @B, look"
    assert n.target_id == w["project"].pk


def test_task_update_mention_notifies_and_editing_does_not_repeat(w):
    path = f"/api/labs/{w['lab'].pk}/tasks/{w['task'].pk}/posts/"
    r = say(w["author"], path, f"{tag(w['member'])} please check")
    assert r.status_code == 201
    [n] = mentions(w, w["member"])
    assert n.title == "A mentioned you in the task: Run it"
    assert n.target_id == w["task"].pk
    c = APIClient()
    c.force_login(w["author"])
    edit = c.patch(f"/api/labs/{w['lab'].pk}/task-posts/{r.json()['id']}/",
                   {"body": f"{tag(w['member'])} again"}, "json")  # fmt: skip
    assert edit.status_code == 200
    assert len(mentions(w, w["member"])) == 1


def test_lab_chat_mention_notifies_any_lab_member(w):
    path = f"/api/labs/{w['lab'].pk}/chat/messages/"
    assert say(w["author"], path, f"{tag(w['nonmember'])}").status_code == 201
    [n] = mentions(w, w["nonmember"])
    assert n.title == "A mentioned you in the lab chat"


def test_a_project_mention_of_a_non_member_is_ignored(w):
    assert say(w["author"], project_chat(w), tag(w["nonmember"])).status_code == 201
    assert mentions(w, w["nonmember"]) == []


def test_a_mention_from_another_lab_is_ignored(w):
    path = f"/api/labs/{w['lab'].pk}/chat/messages/"
    assert say(w["author"], path, tag(w["stranger"])).status_code == 201
    assert say(w["author"], project_chat(w), tag(w["stranger"])).status_code == 201
    assert mentions(w, w["stranger"]) == []


def test_nobody_is_told_about_their_own_mention_and_junk_tokens_are_ignored(w):
    body = f"{tag(w['author'])} @[x](user:not-a-uuid) @[y](user:{'0' * 36})"
    assert say(w["author"], project_chat(w), body).status_code == 201
    assert Notification.objects.for_lab(w["lab"]).filter(kind=NotificationKind.MENTION).count() == 0


def test_at_most_twenty_people_are_told(w, make_user, join):
    crowd = [make_user(display_name=f"U{i}") for i in range(MAX_MENTIONS + 3)]
    for u in crowd:
        join(u, w["lab"], LabRole.MEMBER)
    say(w["author"], f"/api/labs/{w['lab'].pk}/chat/messages/", " ".join(tag(u) for u in crowd))
    assert (
        Notification.objects.for_lab(w["lab"]).filter(kind=NotificationKind.MENTION).count()
        == MAX_MENTIONS
    )


def test_a_mention_stops_showing_once_the_reader_loses_the_project(w):
    say(w["author"], project_chat(w), tag(w["member"]))
    qs = Notification.objects.for_lab(w["lab"]).filter(recipient=w["member"])
    assert len(visible_notifications(w["member"], w["lab"], qs)) == 1
    ProjectMembership.objects.for_lab(w["lab"]).filter(user=w["member"]).delete()
    assert visible_notifications(w["member"], w["lab"], qs) == []
