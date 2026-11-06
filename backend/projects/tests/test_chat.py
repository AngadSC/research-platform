"""Project group chat (D206). Who can reach each endpoint is in the permission matrix; this covers
what the matrix can't: paging, validation, separation between projects, and delete rules."""

import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from labs.models import LabRole
from projects.models import ChatMessage, ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def room(make_lab, make_project, make_user, join):
    lab = make_lab()
    project = make_project(lab)
    people = {}
    for name, role in [("a", ProjectRole.CONTRIBUTOR), ("b", ProjectRole.CONTRIBUTOR)]:
        people[name] = make_user()
        join(people[name], lab, LabRole.MEMBER)
        ProjectMembership.objects.create(lab=lab, project=project, user=people[name], role=role)
    url = f"/api/labs/{lab.pk}/projects/{project.pk}/messages/"
    return lab, project, people["a"], people["b"], url


def say(lab, project, author, body="hi", minutes_ago=0):
    message = ChatMessage.objects.create(lab=lab, project=project, author=author, body=body)
    if minutes_ago:
        at = timezone.now() - datetime.timedelta(minutes=minutes_ago)
        ChatMessage.objects.for_lab(lab).filter(pk=message.pk).update(created_at=at)
    return message


def test_a_posted_message_reaches_the_other_member(room):
    _, _, a, b, url = room
    posted = api(a).post(url, {"body": "  Line one\nLine two  "}, "json")
    assert posted.status_code == 201, posted.content
    rows = api(b).get(url).json()
    assert [r["body"] for r in rows] == ["Line one\nLine two"]
    assert rows[0]["author"]["id"] == str(a.pk)


def test_author_comes_from_the_session_not_the_request(room):
    _, _, a, b, url = room
    api(a).post(url, {"body": "x", "author": str(b.pk)}, "json")
    assert api(b).get(url).json()[0]["author"]["id"] == str(a.pk)


@pytest.mark.parametrize("body", ["", "   \n ", "x" * 4001])
def test_blank_and_oversized_messages_are_rejected(room, body):
    *_, a, _, url = room
    assert api(a).post(url, {"body": body}, "json").status_code == 400


def test_chat_stays_inside_its_project(room, make_project):
    lab, project, a, _, url = room
    other = make_project(lab, "Other")
    say(lab, project, a, "here")
    say(lab, other, a, "elsewhere")
    assert [r["body"] for r in api(a).get(url).json()] == ["here"]


def test_list_is_the_newest_page_oldest_first_and_before_pages_back(room):
    lab, project, a, _, url = room
    for i in range(105):
        say(lab, project, a, f"m{i}", minutes_ago=200 - i)
    client = api(a)
    newest = client.get(url).json()
    assert len(newest) == 100
    assert (newest[0]["body"], newest[-1]["body"]) == ("m5", "m104")
    older = client.get(url, {"before": newest[0]["created_at"]}).json()
    assert [r["body"] for r in older] == ["m0", "m1", "m2", "m3", "m4"]


def test_bad_before_is_a_field_error(room):
    *_, a, _, url = room
    assert api(a).get(url, {"before": "yesterday"}).status_code == 400


def test_polling_is_not_throttled_but_sending_is(room, settings):
    from rest_framework.throttling import ScopedRateThrottle

    *_, a, _, url = room
    original = ScopedRateThrottle.THROTTLE_RATES
    ScopedRateThrottle.THROTTLE_RATES = {**original, "chat": "2/minute"}
    try:
        client = api(a)
        codes = [client.post(url, {"body": "x"}, "json").status_code for _ in range(3)]
        assert codes == [201, 201, 429]
        assert client.get(url).status_code == 200
    finally:
        ScopedRateThrottle.THROTTLE_RATES = original


def test_authors_delete_their_own_message_and_it_is_really_gone(room):
    lab, project, a, _, url = room
    message = say(lab, project, a, "oops")
    assert api(a).delete(f"/api/labs/{lab.pk}/messages/{message.pk}/").status_code == 204
    assert not ChatMessage.objects.for_lab(lab).filter(pk=message.pk).exists()
    assert api(a).get(url).json() == []


def test_a_contributor_cannot_delete_someone_elses_message(room):
    lab, project, a, b, _ = room
    message = say(lab, project, a)
    assert api(b).delete(f"/api/labs/{lab.pk}/messages/{message.pk}/").status_code == 403
    assert ChatMessage.objects.for_lab(lab).filter(pk=message.pk).exists()


def test_someone_removed_from_the_project_loses_the_chat(room):
    lab, project, a, _, url = room
    say(lab, project, a)
    ProjectMembership.objects.for_lab(lab).filter(project=project, user=a).delete()
    assert api(a).get(url).status_code == 404
    assert api(a).post(url, {"body": "x"}, "json").status_code == 404


def test_a_deleted_project_hides_its_chat(room):
    lab, project, a, _, url = room
    project.deleted_at = timezone.now()
    project.save()
    assert api(a).get(url).status_code == 404


# ---------------------------------------------------------------- unread counts (D207)


def unread(user, lab):
    return {
        r["project"]: r["count"] for r in api(user).get(f"/api/labs/{lab.pk}/chat/unread/").json()
    }


def read_url(lab, project):
    return f"/api/labs/{lab.pk}/projects/{project.pk}/messages/read/"


def test_other_peoples_messages_count_as_unread_but_your_own_do_not(room):
    lab, project, a, b, _ = room
    say(lab, project, a)
    say(lab, project, a)
    say(lab, project, b)
    assert unread(b, lab) == {str(project.pk): 2}
    assert unread(a, lab) == {str(project.pk): 1}


def test_reading_clears_the_count_and_later_messages_count_again(room):
    lab, project, a, b, _ = room
    seen = say(lab, project, a, minutes_ago=5)
    seen.refresh_from_db()
    body = {"last_read_at": seen.created_at.isoformat()}
    assert api(b).post(read_url(lab, project), body, "json").status_code == 204
    assert unread(b, lab) == {}
    say(lab, project, a)
    assert unread(b, lab) == {str(project.pk): 1}


def test_a_message_newer_than_what_you_saw_stays_unread(room):
    lab, project, a, b, _ = room
    seen = say(lab, project, a, minutes_ago=5)
    seen.refresh_from_db()
    say(lab, project, a)  # arrived after the screen last updated
    api(b).post(read_url(lab, project), {"last_read_at": seen.created_at.isoformat()}, "json")
    assert unread(b, lab) == {str(project.pk): 1}


def test_read_position_never_moves_backward_or_past_now(room):
    lab, project, a, b, _ = room
    say(lab, project, a, minutes_ago=5)
    client = api(b)
    future = timezone.now() + datetime.timedelta(days=1)
    client.post(read_url(lab, project), {"last_read_at": future.isoformat()}, "json")
    assert unread(b, lab) == {}
    say(lab, project, a)  # a future position must not hide this
    assert unread(b, lab) == {str(project.pk): 1}
    old = timezone.now() - datetime.timedelta(days=30)
    client.post(read_url(lab, project), {"last_read_at": old.isoformat()}, "json")
    assert unread(b, lab) == {str(project.pk): 1}  # still only the new one, not both


def test_reading_is_per_person(room):
    lab, project, a, b, _ = room
    third = say(lab, project, a, minutes_ago=1)
    third.refresh_from_db()
    api(b).post(read_url(lab, project), {"last_read_at": timezone.now().isoformat()}, "json")
    say(lab, project, b)
    assert unread(a, lab) == {str(project.pk): 1}
    assert unread(b, lab) == {}


def test_counts_leave_out_projects_you_cannot_see(room, make_project):
    lab, project, a, b, _ = room
    hidden = make_project(lab, "Hidden")
    say(lab, hidden, a)
    say(lab, project, a)
    assert unread(b, lab) == {str(project.pk): 1}


def test_a_deleted_message_stops_counting(room):
    lab, project, a, b, _ = room
    message = say(lab, project, a)
    assert unread(b, lab) == {str(project.pk): 1}
    api(a).delete(f"/api/labs/{lab.pk}/messages/{message.pk}/")
    assert unread(b, lab) == {}


def test_a_bad_read_position_is_a_field_error(room):
    lab, project, _, b, _ = room
    assert api(b).post(read_url(lab, project), {"last_read_at": "soon"}, "json").status_code == 400
