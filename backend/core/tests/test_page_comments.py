"""The floating comment button: a comment on any page, with @mentions and page tags."""

import pytest
from rest_framework.test import APIClient

from core.models import Notification, NotificationKind, PageComment
from labs.models import LabRole
from projects.models import Project, ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab, other = make_lab("Lab"), make_lab("Other Lab")
    author, member, outsider, stranger = (make_user(display_name=n) for n in "ABCD")
    for u in (author, member, outsider):
        join(u, lab, LabRole.MEMBER)
    join(stranger, other, LabRole.PI)
    project = Project.objects.create(lab=lab, name="Alpha", created_by=author)
    for u in (author, member):
        ProjectMembership.objects.create(lab=lab, project=project, user=u, role=ProjectRole.LEAD)
    return dict(lab=lab, author=author, member=member, outsider=outsider,
                stranger=stranger, project=project)  # fmt: skip


def client(user):
    c = APIClient()
    c.force_login(user)
    return c


def url(w):
    return f"/api/labs/{w['lab'].pk}/page-comments/"


def project_path(w):
    return f"/labs/{w['lab'].pk}/projects/{w['project'].pk}/tasks"


def post(w, user, path, body, **extra):
    return client(user).post(
        url(w), {"path": path, "body": body, "page_label": "Alpha", **extra}, "json"
    )


def test_comment_on_a_project_page_is_seen_by_project_members_only(w):
    assert post(w, w["author"], project_path(w), "hello", quote="a line").status_code == 201
    mine = client(w["member"]).get(url(w), {"path": project_path(w)})
    assert [c["body"] for c in mine.data] == ["hello"]
    assert mine.data[0]["quote"] == "a line"
    assert client(w["outsider"]).get(url(w), {"path": project_path(w)}).status_code == 404
    assert post(w, w["outsider"], project_path(w), "sneaky").status_code == 404


def test_other_labs_and_foreign_paths_are_refused(w):
    assert client(w["stranger"]).get(url(w), {"path": project_path(w)}).status_code == 404
    r = post(w, w["author"], "/labs/00000000-0000-0000-0000-000000000000/x", "no")
    assert r.status_code == 400


def test_lab_page_comment_is_seen_by_the_whole_lab(w):
    path = f"/labs/{w['lab'].pk}/calendar"
    assert post(w, w["author"], path, "for everyone").status_code == 201
    assert len(client(w["outsider"]).get(url(w), {"path": path}).data) == 1


def test_mention_notifies_only_people_who_can_see_the_page(w):
    tag = lambda u: f"@[{u.display_name}](user:{u.pk})"  # noqa: E731
    body = f"{tag(w['member'])} {tag(w['outsider'])} see #[Tasks](page:{project_path(w)})"
    assert post(w, w["author"], project_path(w), body).status_code == 201
    got = Notification.objects.for_lab(w["lab"]).filter(kind=NotificationKind.MENTION)
    assert [n.recipient_id for n in got] == [w["member"].pk]


def test_lab_page_mention_notifies_a_lab_member(w):
    path = f"/labs/{w['lab'].pk}/calendar"
    body = f"@[C](user:{w['outsider'].pk}) hi"
    assert post(w, w["author"], path, body).status_code == 201
    assert Notification.objects.for_lab(w["lab"]).filter(recipient=w["outsider"]).count() == 1


def test_only_the_author_or_a_lab_manager_deletes(w):
    cid = post(w, w["author"], project_path(w), "x").data["id"]
    d = f"{url(w)}{cid}/"
    assert client(w["member"]).delete(d).status_code == 403
    assert client(w["author"]).delete(d).status_code == 204
    assert PageComment.objects.for_lab(w["lab"]).count() == 0


def test_a_mention_in_a_page_comment_opens_that_page(w):
    """It used to link to the lab home (a lab-wide page) or the project chat, never the page."""
    tag = f"@[B](user:{w['member'].pk})"
    lab_path = f"/labs/{w['lab'].pk}/papers"
    for path in (lab_path, project_path(w)):
        assert post(w, w["author"], path, f"look {tag}").status_code == 201
    got = client(w["member"]).get(f"/api/labs/{w['lab'].pk}/notifications/").json()
    assert {n["url"] for n in got} == {lab_path, project_path(w)}
