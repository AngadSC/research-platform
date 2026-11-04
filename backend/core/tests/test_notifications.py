"""D30: notifications are lab-scoped and visible only to their recipient."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import Notification, NotificationKind
from core.notifications import notify
from labs.models import LabRole

pytestmark = pytest.mark.django_db


def notify_one(lab, user, title):
    notify(
        lab=lab,
        recipient=user,
        kind=NotificationKind.TASK_ASSIGNED,
        title=title,
        dedupe_key=f"test:{title}",
    )
    return Notification.objects.for_lab(lab).get(recipient=user, title=title)


@pytest.fixture
def w(make_lab, make_user, join):
    lab, other = make_lab("A"), make_lab("B")
    alice, bob, eve = make_user(), make_user(), make_user()
    join(alice, lab, LabRole.MEMBER)
    join(bob, lab, LabRole.MEMBER)
    join(eve, other, LabRole.PI)
    mine = notify_one(lab, alice, "mine")
    notify_one(lab, alice, "mine too")
    theirs = notify_one(lab, bob, "theirs")
    return lab, alice, bob, eve, mine, theirs


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def url(name, lab, **kw):
    return reverse(f"core:{name}", kwargs={"lab_id": lab.pk, **kw})


def test_list_shows_only_own_notifications(w):
    lab, alice, bob, *_ = w
    titles = [n["title"] for n in api(alice).get(url("notification-list", lab)).json()]
    assert sorted(titles) == ["mine", "mine too"]
    assert [n["title"] for n in api(bob).get(url("notification-list", lab)).json()] == ["theirs"]


def test_another_users_notification_is_404_and_untouched(w):
    lab, alice, bob, eve, mine, theirs = w
    read = url("notification-read", lab, notification_id=theirs.pk)
    assert api(alice).post(read).status_code == 404
    theirs.refresh_from_db()
    assert theirs.read_at is None
    # a member of another lab gets 404 on the lab itself
    assert api(eve).post(url("notification-read", lab, notification_id=mine.pk)).status_code == 404
    assert api(eve).get(url("notification-list", lab)).status_code == 404


def test_mark_read_and_unread_filter_and_read_all(w):
    lab, alice, bob, _, mine, theirs = w
    resp = api(alice).post(url("notification-read", lab, notification_id=mine.pk))
    assert resp.status_code == 200 and resp.json()["read_at"]
    unread = api(alice).get(url("notification-list", lab) + "?unread=true").json()
    assert [n["title"] for n in unread] == ["mine too"]
    assert api(alice).post(url("notification-read-all", lab)).json() == {"updated": 1}
    assert api(alice).post(url("notification-read-all", lab)).json() == {"updated": 0}
    theirs.refresh_from_db()
    assert theirs.read_at is None  # read-all never touches other people's rows


def test_notify_dedupes_per_recipient_and_key(w):
    lab, alice, bob, *_ = w
    kw = {"lab": lab, "kind": NotificationKind.RETENTION_DUE, "title": "t", "dedupe_key": "k"}
    assert notify(recipient=alice, **kw)
    assert not notify(recipient=alice, **kw)
    assert notify(recipient=bob, **kw)
