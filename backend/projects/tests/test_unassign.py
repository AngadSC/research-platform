"""Losing access unassigns a person's open tasks (Run 2)."""

import pytest
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction, AuditEvent
from core.models import Notification, NotificationKind
from labs import services as lab_services
from labs.models import LabMembership, LabRole
from projects import handover, services
from projects.models import Project, ProjectMembership, ProjectRole, Task, TaskStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Lab")
    pi, lead, worker = make_user(), make_user(), make_user()
    join(pi, lab, LabRole.PI)
    join(lead, lab, LabRole.MEMBER)
    join(worker, lab, LabRole.MEMBER)
    project = Project.objects.create(lab=lab, name="P", created_by=pi)
    ProjectMembership.objects.create(lab=lab, project=project, user=lead, role=ProjectRole.LEAD)
    pm = ProjectMembership.objects.create(
        lab=lab, project=project, user=worker, role=ProjectRole.CONTRIBUTOR
    )
    mk = lambda title, status: Task.objects.create(  # noqa: E731
        lab=lab, project=project, title=title, assignee=worker, created_by=pi, status=status
    )
    open_t, done_t = mk("open", TaskStatus.TODO), mk("done", TaskStatus.DONE)
    return dict(
        lab=lab, pi=pi, lead=lead, worker=worker, project=project, pm=pm, open=open_t, done=done_t
    )


def _check(w, reason, actor):
    w["open"].refresh_from_db()
    w["done"].refresh_from_db()
    assert w["open"].assignee is None
    assert w["done"].assignee == w["worker"]
    (ev,) = AuditEvent.objects.filter(action=AuditAction.TASK_UNASSIGNED)
    assert ev.target_id == w["open"].pk and ev.actor == actor
    assert ev.metadata == {"previous_assignee_id": str(w["worker"].pk), "reason": reason}
    got = Notification.objects.for_lab(w["lab"]).filter(kind=NotificationKind.TASK_UNASSIGNED)
    assert {n.recipient for n in got} == {w["pi"], w["lead"]}  # leads, never the worker
    assert got.count() == 2


def test_removed_from_project(world):
    services.remove_member(membership=world["pm"], by=world["lead"])
    _check(world, "removed_from_project", world["lead"])


def test_project_role_to_viewer(world):
    services.change_member_role(membership=world["pm"], by=world["lead"], role=ProjectRole.VIEWER)
    _check(world, "project_role_changed", world["lead"])


def test_contributor_keeps_tasks_on_lead_change(world):
    services.change_member_role(membership=world["pm"], by=world["lead"], role=ProjectRole.LEAD)
    world["open"].refresh_from_db()
    assert world["open"].assignee == world["worker"]


def test_removed_from_lab(world):
    m = LabMembership.objects.for_lab(world["lab"]).get(user=world["worker"], lab=world["lab"])
    lab_services.remove_member(membership=m, by=world["pi"])
    _check(world, "removed_from_lab", world["pi"])


def test_lab_role_to_viewer(world):
    m = LabMembership.objects.for_lab(world["lab"]).get(user=world["worker"], lab=world["lab"])
    lab_services.change_role(membership=m, by=world["pi"], role=LabRole.VIEWER)
    _check(world, "lab_role_changed", world["pi"])


def test_demoted_admin_without_membership(world, make_user, join):
    admin = make_user()
    join(admin, world["lab"], LabRole.LAB_ADMIN)
    t = Task.objects.create(
        lab=world["lab"], project=world["project"], title="x", assignee=admin, created_by=admin
    )
    lab_services.change_role(
        membership=LabMembership.objects.for_lab(world["lab"]).get(user=admin, lab=world["lab"]),
        by=world["pi"],
        role=LabRole.MEMBER,
    )
    t.refresh_from_db()
    assert t.assignee is None


def test_deactivation(world):
    world["worker"].is_active = False
    world["worker"].save()
    world["open"].refresh_from_db()
    assert world["open"].assignee is None
    (ev,) = AuditEvent.objects.filter(action=AuditAction.TASK_UNASSIGNED)
    assert ev.actor is None and ev.actor_label == "system"
    assert ev.metadata["reason"] == "user_deactivated"
    assert (
        Notification.objects.for_lab(world["lab"])
        .filter(kind=NotificationKind.TASK_UNASSIGNED)
        .count()
        == 2
    )


def test_cannot_assign_viewer(world):
    world["pm"].role = ProjectRole.VIEWER
    world["pm"].save()
    with pytest.raises(ValidationError):
        services.update_task(task=world["open"], data={"assignee": world["worker"].pk})


def test_handover_lists_still_unassigned_only(world):
    services.remove_member(membership=world["pm"], by=world["lead"])
    m = LabMembership.objects.for_lab(world["lab"]).get(user=world["worker"], lab=world["lab"])

    def titles():
        r = handover.build_report(requester=world["pi"], lab=world["lab"], membership=m)
        (s,) = [s for s in r["sections"] if s["key"] == "unassigned_tasks"]
        return [i["title"] for i in s["items"]]

    assert titles() == ["open"]
    world["open"].assignee = world["lead"]
    world["open"].save()
    assert titles() == []
