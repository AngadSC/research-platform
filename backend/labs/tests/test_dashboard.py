"""PI dashboard (Run 5, D170-D174): access, cross-lab isolation, each attention rule, queries."""

from datetime import date, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction
from audit.services import record
from ethics.models import EthicsApproval
from integrations.models import ConnectedAccount
from labs.models import LabRole
from projects.models import (
    Project,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    Task,
    TaskStatus,
)
from provenance.models import DataManagementPlan, FundingRecord

pytestmark = pytest.mark.django_db
TODAY = date.today()
days = lambda n: TODAY + timedelta(days=n)  # noqa: E731


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


def get(w, user=None):
    resp = api(user or w["pi"]).get(f"/api/labs/{w['lab'].pk}/dashboard/")
    assert resp.status_code == 200, resp.content
    return resp.json()


def task(w, **kw):
    kw.setdefault("title", "T")
    return Task.objects.create(lab=w["lab"], project=w["project"], created_by=w["pi"], **kw)


def test_only_pi_and_admin(world, make_user, join):
    admin, viewer = make_user(), make_user()
    join(admin, world["lab"], LabRole.LAB_ADMIN)
    join(viewer, world["lab"], LabRole.VIEWER)
    url = f"/api/labs/{world['lab'].pk}/dashboard/"
    assert api(admin).get(url).status_code == 200
    assert api(world["member"]).get(url).status_code == 403  # even a project lead
    assert api(viewer).get(url).status_code == 403
    assert APIClient().get(url).status_code == 401


def test_other_lab_is_404_and_data_never_leaks(world, make_lab, make_user, join):
    lab_b = make_lab("B")
    pi_b = make_user()
    join(pi_b, lab_b, LabRole.PI)
    other = Project.objects.create(lab=lab_b, name="Secret B", created_by=pi_b)
    Task.objects.create(
        lab=lab_b, project=other, created_by=pi_b, title="B late", due_date=days(-3)
    )
    assert api(pi_b).get(f"/api/labs/{world['lab'].pk}/dashboard/").status_code == 404
    data = get(world)
    assert [p["name"] for p in data["projects"]] == ["P1"]
    assert data["summary"]["overdue_tasks"] == 0
    assert [p["name"] for p in get({**world, "lab": lab_b}, pi_b)["projects"]] == ["Secret B"]


def test_project_row_counts_leads_deadline_funding(world):
    task(world, status=TaskStatus.TODO, due_date=days(-2))
    task(world, status=TaskStatus.IN_PROGRESS)
    task(world, status=TaskStatus.DONE, due_date=days(-9))
    ProjectDeadline.objects.create(
        lab=world["lab"], project=world["project"], title="Later", due_date=days(40)
    )
    ProjectDeadline.objects.create(
        lab=world["lab"], project=world["project"], title="Soon", due_date=days(5), priority="high"
    )
    FundingRecord.objects.create(
        lab=world["lab"],
        project=world["project"],
        funder="NSERC",
        status="active",
        end_date=days(200),
        created_by=world["pi"],
    )
    (row,) = get(world)["projects"]
    assert (row["open_tasks"], row["overdue_tasks"], row["in_progress_tasks"]) == (2, 1, 1)
    assert [x["id"] for x in row["leads"]] == [str(world["member"].pk)]
    assert row["next_deadline"]["title"] == "Soon" and row["next_deadline"]["priority"] == "high"
    assert row["funding_end_date"] == days(200).isoformat() and row["funding_status"] == "active"
    assert row["health"] == "red" and "1 overdue task" in row["health_reasons"]


def test_overdue_top_20_with_total(world):
    for i in range(25):
        task(world, title=f"late {i}", due_date=days(-1 - i))
    task(world, title="done late", due_date=days(-5), status=TaskStatus.DONE)
    task(world, title="future", due_date=days(3))
    block = get(world)["attention"]["overdue_tasks"]
    assert block["total"] == 25 and len(block["items"]) == 20
    assert block["items"][0]["title"] == "late 24"  # most overdue first


def test_ethics_window_and_restricted(world):
    mk = lambda n, d, **kw: EthicsApproval.objects.create(  # noqa: E731
        lab=world["lab"],
        approval_number=n,
        board="REB",
        title=n,
        approval_date=days(-400),
        expiry_date=d,
        created_by=world["pi"],
        **kw,
    )
    mk("expired", days(-3))
    mk("soon", days(59))
    mk("far", days(61))
    mk("withdrawn", days(10), status="withdrawn")
    mk("restricted", days(20), restricted=True)  # the PI still sees it (D56)
    gone = mk("deleted", days(5))
    gone.deleted_at = timezone.now()
    gone.save()
    items = get(world)["attention"]["ethics"]["items"]
    assert [i["title"] for i in items] == ["expired", "restricted", "soon"]
    assert items[0]["expired"] is True and items[1]["expired"] is False


def test_restricted_ethics_hidden_from_non_leads_by_rule(world):
    # the endpoint is closed to members, so the rule is checked on the query it relies on
    from ethics.models import EthicsApproval as E

    E.objects.create(
        lab=world["lab"],
        approval_number="r",
        board="REB",
        title="r",
        approval_date=days(-9),
        expiry_date=days(9),
        restricted=True,
        created_by=world["pi"],
    )
    stranger_ok = E.objects.visible_to(world["member"], world["lab"]).count()
    assert stranger_ok == 0
    assert E.objects.visible_to(world["pi"], world["lab"]).count() == 1


def test_funding_ending_within_90_days(world):
    mk = lambda funder, end, status="active": FundingRecord.objects.create(  # noqa: E731
        lab=world["lab"],
        project=world["project"],
        funder=funder,
        status=status,
        end_date=end,
        created_by=world["pi"],
    )
    mk("ended", days(-2))
    mk("soon", days(90))
    mk("later", days(91))
    mk("closed", days(10), "closed")
    mk("applied", days(10), "applied")
    items = get(world)["attention"]["funding"]["items"]
    assert [i["funder"] for i in items] == ["ended", "soon"]
    assert items[0]["days_left"] == -2


def test_deadlines_within_14_days_by_priority(world):
    mk = lambda t, d, pr="medium", done=False: ProjectDeadline.objects.create(  # noqa: E731
        lab=world["lab"],
        project=world["project"],
        title=t,
        due_date=d,
        priority=pr,
        done=done,
    )
    mk("low-early", days(1), "low")
    mk("high-late", days(13), "high")
    mk("med", days(2))
    mk("too far", days(15), "high")
    mk("done", days(1), "high", True)
    mk("overdue", days(-1), "medium")
    titles = [d["title"] for d in get(world)["attention"]["deadlines"]["items"]]
    assert titles == ["high-late", "overdue", "med", "low-early"]


def test_stalled_projects(world):
    fresh = Project.objects.create(
        lab=world["lab"], name="Fresh", created_by=world["pi"], status="active"
    )
    Project.objects.for_lab(world["lab"]).filter(pk=world["project"].pk).update(
        last_activity_at=timezone.now() - timedelta(days=31)
    )
    Project.objects.for_lab(world["lab"]).filter(pk=fresh.pk).update(
        last_activity_at=timezone.now() - timedelta(days=5)
    )
    done = Project.objects.create(
        lab=world["lab"], name="Done", created_by=world["pi"], status="completed"
    )
    Project.objects.for_lab(world["lab"]).filter(pk=done.pk).update(
        last_activity_at=timezone.now() - timedelta(days=99)
    )
    block = get(world)["attention"]["stalled"]
    assert [s["project_name"] for s in block["items"]] == ["P1"]
    assert block["items"][0]["days_idle"] == 31


def test_unassigned_after_access_change(world):
    lost = task(world, title="lost", assignee=None)
    task(world, title="never assigned")  # no audit event: not an access change
    done = task(world, title="finished", status=TaskStatus.DONE)
    for t in (lost, done):
        record(
            AuditAction.TASK_UNASSIGNED,
            actor=None,
            actor_label="system",
            lab=world["lab"],
            target=t,
        )
    items = get(world)["attention"]["unassigned"]["items"]
    assert [i["title"] for i in items] == ["lost"]


def test_integrations_in_error_or_expired(world):
    def mk(status, user, ext):
        return ConnectedAccount.objects.create(
            lab=world["lab"],
            user=user,
            provider="zotero",
            external_account_id=ext,
            status=status,
            connected_at=timezone.now(),
        )

    mk("expired", world["member"], "1")
    mk("error", world["pi"], "2")
    mk("active", world["pi"], "3")
    mk("revoked", world["member"], "4")
    items = get(world)["attention"]["integrations"]["items"]
    assert sorted(i["status"] for i in items) == ["error", "expired"]


def test_people_counts_not_timelines(world):
    task(world, assignee=world["member"], due_date=days(-1))
    task(world, assignee=world["member"])
    task(world, assignee=world["member"], status=TaskStatus.DONE)
    old = task(world, assignee=world["member"], status=TaskStatus.DONE)
    Task.objects.for_lab(world["lab"]).filter(pk=old.pk).update(
        updated_at=timezone.now() - timedelta(days=40)
    )
    people = {p["user_id"]: p for p in get(world)["people"]}
    m = people[str(world["member"].pk)]
    assert (m["open_tasks"], m["overdue_tasks"], m["done_last_30_days"]) == (2, 1, 1)
    assert set(m) == {
        "user_id", "name", "role", "open_tasks", "overdue_tasks", "done_last_30_days",
        "last_active_at",
    }  # fmt: skip
    assert people[str(world["pi"].pk)]["open_tasks"] == 0


def test_projects_without_an_approved_dmp(world):
    lab, pi = world["lab"], world["pi"]
    done = Project.objects.create(lab=lab, name="Done", created_by=pi, status="completed")
    draft = Project.objects.create(lab=lab, name="Drafty", created_by=pi, status="planning")
    ok = Project.objects.create(lab=lab, name="Approved", created_by=pi, status="active")
    DataManagementPlan.objects.create(lab=lab, project=draft, updated_by=pi)
    DataManagementPlan.objects.create(lab=lab, project=ok, status="approved", updated_by=pi)
    data = get(world)
    got = {i["project_name"]: i["dmp_status"] for i in data["attention"]["dmp"]["items"]}
    assert got == {"P1": "none", "Drafty": "draft"}  # completed and approved ones are not listed
    assert data["attention"]["dmp"]["total"] == 2 == data["summary"]["projects_without_dmp"]
    assert done.name not in got


def test_query_count_is_flat(world, make_user, join):
    def populate(n):
        for i in range(n):
            u = make_user()
            join(u, world["lab"], LabRole.MEMBER)
            p = Project.objects.create(lab=world["lab"], name=f"X{n}-{i}", created_by=world["pi"])
            ProjectMembership.objects.create(lab=world["lab"], project=p, user=u, role="lead")
            t = Task.objects.create(
                lab=world["lab"], project=p, created_by=world["pi"], title="t",
                assignee=u, due_date=days(-1),
            )  # fmt: skip
            ProjectDeadline.objects.create(lab=world["lab"], project=p, title="d", due_date=days(3))
            FundingRecord.objects.create(
                lab=world["lab"], project=p, funder="f", status="active", end_date=days(5),
                created_by=world["pi"],
            )  # fmt: skip
            record(
                AuditAction.TASK_UNASSIGNED, actor=None, actor_label="s", lab=world["lab"], target=t
            )

    def count():
        client = api(world["pi"])
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(f"/api/labs/{world['lab'].pk}/dashboard/").status_code == 200
        return len(ctx)

    populate(1)
    small = count()
    populate(8)
    assert count() == small
    assert small <= 25
