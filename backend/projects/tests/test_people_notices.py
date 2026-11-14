"""Walkthrough fixes: people hear when they join a project, get a task or a project is archived,
and a project lead cannot remove a PI or the last lead."""

import pytest
from rest_framework.test import APIClient

from core.models import Notification, NotificationKind
from core.notifications import notification_url
from labs.models import LabRole
from projects import services
from projects.models import Project, ProjectMembership, ProjectRole, ProjectStatus, Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, join):
    lab = make_lab("Lab")
    pi = make_user(display_name="Pat PI")
    lee, sam = make_user(display_name="Lee"), make_user(display_name="Sam")
    join(pi, lab, LabRole.PI)
    join(lee, lab, LabRole.MEMBER)
    join(sam, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="Study", created_by=pi)
    pi_m = ProjectMembership.objects.create(lab=lab, project=project, user=pi, role="contributor")
    return dict(lab=lab, pi=pi, lee=lee, sam=sam, project=project, pi_m=pi_m)


def notes(w, user, kind=None):
    qs = Notification.objects.for_lab(w["lab"]).filter(recipient=user)
    return list(qs.filter(kind=kind) if kind else qs)


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_added_lead_hears_role_and_tasks(w):
    lab, pi, lee = w["lab"], w["pi"], w["lee"]
    services.add_member(project=w["project"], by=pi, user_id=lee.pk, role=ProjectRole.LEAD)
    (added,) = notes(w, lee, NotificationKind.PROJECT_ROLE)
    assert added.title == "Pat PI added you to Study as Lead"
    assert notification_url(added, lee) == f"/labs/{lab.pk}/projects/{w['project'].pk}"
    for title in ("One", "Two"):
        services.create_task(project=w["project"], by=pi, data={"title": title, "assignee": lee.pk})
    assert len(notes(w, lee, NotificationKind.TASK_ASSIGNED)) == 2
    # assigning yourself tells nobody; reassigning to someone else tells them
    task = services.create_task(
        project=w["project"], by=lee, data={"title": "Mine", "assignee": lee.pk}
    )
    assert len(notes(w, lee, NotificationKind.TASK_ASSIGNED)) == 2
    services.add_member(project=w["project"], by=lee, user_id=w["sam"].pk, role="contributor")
    services.update_task(task=task, by=lee, data={"title": "Renamed"})
    assert notes(w, w["sam"], NotificationKind.TASK_ASSIGNED) == []
    services.update_task(task=task, by=lee, data={"assignee": w["sam"].pk})
    (got,) = notes(w, w["sam"], NotificationKind.TASK_ASSIGNED)
    assert got.title == "Lee assigned you: Renamed"
    assert notification_url(got, w["sam"]).endswith(f"/tasks?task={task.pk}")
    m = ProjectMembership.objects.for_lab(lab).get(user=w["sam"])
    services.change_member_role(membership=m, by=lee, role="viewer")
    (changed,) = [
        n for n in notes(w, w["sam"], NotificationKind.PROJECT_ROLE) if "changed" in n.title
    ]
    assert changed.title == "Lee changed your role on Study to Viewer"


def test_template_tasks_and_self_add_tell_nobody(w):
    pi = w["pi"]
    services.create_project(lab=w["lab"], user=pi, data={"name": "T", "template": "honours_thesis"})
    assert Task.objects.for_lab(w["lab"]).filter(project__name="T").exists()
    assert notes(w, pi) == []


def test_archive_tells_pis_and_leads_but_not_the_archiver(w, make_user, join):
    lab, project = w["lab"], w["project"]
    admin = make_user()
    join(admin, lab, LabRole.LAB_ADMIN)
    services.add_member(project=project, by=w["pi"], user_id=w["lee"].pk, role="lead")
    services.add_member(project=project, by=w["pi"], user_id=w["sam"].pk, role="contributor")
    Notification.objects.for_lab(lab).all().delete()
    services.update_project(project=project, user=w["lee"], data={"status": ProjectStatus.ARCHIVED})
    (note,) = Notification.objects.for_lab(lab).filter(kind=NotificationKind.PROJECT_ARCHIVED)
    assert note.recipient == w["pi"] and note.title == "Lee archived Study"


def test_lead_cannot_remove_or_demote_a_pi_or_the_last_lead(w):
    lab, lee = w["lab"], w["lee"]
    services.add_member(project=w["project"], by=w["pi"], user_id=lee.pk, role="lead")
    lee_m = ProjectMembership.objects.for_lab(lab).get(user=lee)
    url = f"/api/labs/{lab.pk}/project-members/"
    members = api(lee).get(f"/api/labs/{lab.pk}/projects/{w['project'].pk}/members/").json()
    assert {m["user"]["id"]: m["can_change"] for m in members} == {
        str(w["pi"].pk): False,
        str(lee.pk): False,  # the only lead
    }
    for res in (
        api(lee).delete(f"{url}{w['pi_m'].pk}/"),
        api(lee).patch(f"{url}{w['pi_m'].pk}/", {"role": "viewer"}, format="json"),
    ):
        assert res.status_code == 403
        assert "PI" in res.json()["detail"]
    res = api(lee).delete(f"{url}{lee_m.pk}/")
    assert res.status_code == 403 and "needs a lead" in res.json()["detail"]
    assert ProjectMembership.objects.for_lab(lab).filter(project=w["project"]).count() == 2
    # with a second lead, Lee may step down; the PI may always change anyone
    services.add_member(project=w["project"], by=w["pi"], user_id=w["sam"].pk, role="lead")
    assert (
        api(lee).patch(f"{url}{lee_m.pk}/", {"role": "contributor"}, format="json").status_code
        == 200
    )
    sam_m = ProjectMembership.objects.for_lab(lab).get(user=w["sam"])
    assert api(w["pi"]).delete(f"{url}{sam_m.pk}/").status_code == 204
