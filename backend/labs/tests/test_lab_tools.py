"""Lab chat, the calendar and inventory orders. Who reaches each endpoint is in
tests/test_permission_matrix.py; this covers what the matrix can't: what the rows contain,
validation, and adding a received order to stock exactly once."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from ethics.models import EthicsApproval
from labs import admin_services as svc
from labs.models import InventoryItem, InventoryOrder, LabChatMessage, LabEvent, LabRole
from projects.models import ProjectDeadline, ProjectMembership, ProjectRole, Task
from provenance.models import FundingRecord

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Tools Lab")
    users = {}
    for name, role in [("pi", LabRole.PI), ("member", LabRole.MEMBER), ("viewer", LabRole.VIEWER)]:
        users[name] = make_user()
        join(users[name], lab, role)
    project = make_project(lab, "Visible", color="teal")
    hidden = make_project(lab, "Hidden Project")
    for name in ("member", "viewer"):
        ProjectMembership.objects.create(
            lab=lab, project=project, user=users[name], role=ProjectRole.CONTRIBUTOR
        )
    return lab, users, project, hidden


def url(lab, tail):
    return f"/api/labs/{lab.pk}/{tail}"


# ---------------------------------------------------------------- lab chat


def unread(user, lab):
    return {r["project"]: r["count"] for r in api(user).get(url(lab, "chat/unread/")).json()}


def test_every_member_reads_and_posts_including_viewers(world):
    lab, u, *_ = world
    assert (
        api(u["viewer"]).post(url(lab, "chat/messages/"), {"body": "Hi"}, "json").status_code == 201
    )
    rows = api(u["member"]).get(url(lab, "chat/messages/")).json()
    assert [r["body"] for r in rows] == ["Hi"]
    assert rows[0]["author"]["id"] == str(u["viewer"].pk)


def test_lab_chat_unread_uses_server_read_state_and_a_null_project_row(world):
    lab, u, project, _ = world
    message = LabChatMessage.objects.create(lab=lab, author=u["member"], body="hi")
    assert unread(u["viewer"], lab) == {None: 1}
    assert unread(u["member"], lab) == {}  # your own never count
    body = {"last_read_at": message.created_at.isoformat()}
    assert api(u["viewer"]).post(url(lab, "chat/messages/read/"), body, "json").status_code == 204
    assert unread(u["viewer"], lab) == {}
    old = {"last_read_at": (timezone.now() - datetime.timedelta(days=1)).isoformat()}
    api(u["viewer"]).post(url(lab, "chat/messages/read/"), old, "json")  # only moves forward
    assert unread(u["viewer"], lab) == {}
    LabChatMessage.objects.create(lab=lab, author=u["member"], body="again")
    assert unread(u["viewer"], lab) == {None: 1}


def test_lab_chat_delete_rules_and_audit_keeps_no_text(world):
    lab, u, *_ = world
    message = LabChatMessage.objects.create(lab=lab, author=u["member"], body="secret text")
    target = url(lab, f"chat/messages/{message.pk}/")
    assert api(u["viewer"]).delete(target).status_code == 403
    assert api(u["pi"]).delete(target).status_code == 204  # manage_lab moderates
    assert not LabChatMessage.objects.for_lab(lab).filter(pk=message.pk).exists()
    event = AuditEvent.objects.get(action=AuditAction.CHAT_MESSAGE_DELETED)
    assert "secret text" not in str(event.metadata)


# ---------------------------------------------------------------- calendar


def calendar(user, lab, start="2030-06-01", end="2030-06-30"):
    return api(user).get(url(lab, "calendar/"), {"from": start, "to": end})


@pytest.fixture
def dated(world, make_user):
    """One of each kind on 2030-06-15, in the visible project and the hidden one."""
    lab, u, project, hidden = world
    date = "2030-06-15"
    for p, tag in ((project, "seen"), (hidden, "HIDDEN")):
        ProjectDeadline.objects.create(lab=lab, project=p, title=f"Deadline {tag}", due_date=date)
        Task.objects.create(
            lab=lab, project=p, title=f"Task {tag}", due_date=date, created_by=u["pi"]
        )
        FundingRecord.objects.create(
            lab=lab,
            project=p,
            funder=f"Funder {tag}",
            end_date=date,
            status="active",
            created_by=u["pi"],
        )
    InventoryItem.objects.create(lab=lab, name="Balance", category="equipment", due_date=date)
    LabEvent.objects.create(lab=lab, title="Retreat", date=date, created_by=u["pi"])
    open_approval = EthicsApproval.objects.create(
        lab=lab,
        approval_number="E1",
        board="B",
        title="Open approval",
        approval_date="2029-01-01",
        expiry_date=date,
        created_by=u["pi"],
    )
    EthicsApproval.objects.create(
        lab=lab,
        approval_number="E2",
        board="B",
        title="Restricted HIDDEN",
        approval_date="2029-01-01",
        expiry_date=date,
        restricted=True,
        created_by=u["pi"],
    ).projects.add(hidden)
    return open_approval


def test_calendar_merges_every_source_and_carries_project_colour(world, dated):
    lab, u, project, _ = world
    rows = calendar(u["pi"], lab).json()
    assert {r["kind"] for r in rows} == {
        "event",
        "deadline",
        "task",
        "inventory",
        "ethics",
        "funding",
    }
    deadline = next(r for r in rows if r["title"] == "Deadline seen")
    assert (deadline["project_id"], deadline["project_color"]) == (str(project.pk), "teal")
    assert next(r for r in rows if r["kind"] == "event")["project_id"] is None


def test_calendar_never_shows_a_hidden_projects_items_or_restricted_ethics(world, dated):
    lab, u, _, hidden = world
    response = calendar(u["member"], lab)
    assert response.status_code == 200
    body = response.content.decode()
    for leak in ("HIDDEN", "Hidden Project", str(hidden.pk)):
        assert leak not in body, leak
    assert {r["title"] for r in response.json() if r["kind"] == "ethics"} == {
        "Open approval (ethics expires)"
    }
    assert "Deadline HIDDEN" in calendar(u["pi"], lab).content.decode()  # a PI sees everything


def test_calendar_drops_a_soft_deleted_project(world, dated):
    lab, u, project, _ = world
    project.deleted_at = timezone.now()
    project.save()
    assert "Deadline seen" not in calendar(u["member"], lab).content.decode()


def test_calendar_is_scoped_to_the_lab(world, dated, make_lab, make_user, join):
    other = make_lab("Other Lab")
    stranger = make_user()
    join(stranger, other, LabRole.PI)
    assert calendar(stranger, other).json() == []


def test_calendar_range_bounds_events_that_overlap(world):
    lab, u, *_ = world
    LabEvent.objects.create(
        lab=lab, title="Conference", date="2030-05-30", end_date="2030-06-02", created_by=u["pi"]
    )
    LabEvent.objects.create(lab=lab, title="Before", date="2030-05-01", created_by=u["pi"])
    LabEvent.objects.create(lab=lab, title="After", date="2030-07-01", created_by=u["pi"])
    assert [r["title"] for r in calendar(u["pi"], lab).json()] == ["Conference"]


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"from": "2030-06-01"},
        {"from": "soon", "to": "2030-06-30"},
        {"from": "2030-06-30", "to": "2030-06-01"},
        {"from": "2030-01-01", "to": "2030-12-31"},  # longer than the bound
    ],
)
def test_calendar_range_is_validated(world, query):
    lab, u, *_ = world
    assert api(u["pi"]).get(url(lab, "calendar/"), query).status_code == 400


def test_event_end_before_start_is_rejected_on_create_and_on_a_partial_edit(world):
    lab, u, *_ = world
    client = api(u["member"])
    bad = {"title": "X", "date": "2030-06-10", "end_date": "2030-06-09"}
    assert client.post(url(lab, "calendar/events/"), bad, "json").status_code == 400
    event = LabEvent.objects.create(
        lab=lab, title="Y", date="2030-06-10", end_date="2030-06-12", created_by=u["pi"]
    )
    target = url(lab, f"calendar/events/{event.pk}/")
    assert client.patch(target, {"date": "2030-06-20"}, "json").status_code == 400


# ---------------------------------------------------------------- inventory orders


@pytest.fixture
def stocked(world):
    lab, *_ = world
    return InventoryItem.objects.create(lab=lab, name="Tips", category="consumable", quantity=5)


def quantity(item):
    return InventoryItem.objects.for_lab(item.lab_id).get(pk=item.pk).quantity


def order_of(lab, user, item=None, **kw):
    return InventoryOrder.objects.create(
        lab=lab, item=item, name="Tips", quantity=3, requested_by=user, **kw
    )


def test_marking_received_adds_to_stock_exactly_once(world, stocked):
    lab, u, *_ = world
    order = order_of(lab, u["member"], stocked)
    target = url(lab, f"inventory/orders/{order.pk}/")
    client = api(u["member"])
    assert client.patch(target, {"status": "ordered"}, "json").status_code == 200
    assert quantity(stocked) == 5  # only the move into received counts
    assert client.patch(target, {"status": "received"}, "json").status_code == 200
    assert quantity(stocked) == 8
    assert client.patch(target, {"status": "received"}, "json").status_code == 200  # a double click
    assert quantity(stocked) == 8
    assert AuditEvent.objects.filter(action=AuditAction.INVENTORY_ITEM_UPDATED).count() == 1


def test_a_stale_copy_of_the_order_cannot_add_stock_twice(world, stocked):
    """Stands in for two requests racing: the service must re-read under its lock."""
    lab, u, *_ = world
    order = order_of(lab, u["member"], stocked)
    first, second = (
        InventoryOrder.objects.for_lab(lab).get(pk=order.pk),
        InventoryOrder.objects.for_lab(lab).get(pk=order.pk),
    )
    svc.update_inventory_order(first, user=u["member"], data={"status": "received"})
    svc.update_inventory_order(second, user=u["member"], data={"status": "received"})
    assert quantity(stocked) == 8


def test_a_received_order_is_frozen_except_notes(world, stocked):
    lab, u, *_ = world
    order = order_of(lab, u["member"], stocked, status="received")
    target = url(lab, f"inventory/orders/{order.pk}/")
    client = api(u["member"])
    assert client.patch(target, {"status": "ordered"}, "json").status_code == 400
    assert client.patch(target, {"quantity": "9"}, "json").status_code == 400
    assert client.patch(target, {"notes": "Arrived damp"}, "json").status_code == 200


def test_creating_an_order_as_received_adds_to_stock(world, stocked):
    lab, u, *_ = world
    body = {"name": "Tips", "quantity": "2", "status": "received", "item": str(stocked.pk)}
    assert api(u["pi"]).post(url(lab, "inventory/orders/"), body, "json").status_code == 201
    assert quantity(stocked) == 7


def test_receiving_without_an_item_changes_nothing(world):
    lab, u, *_ = world
    order = order_of(lab, u["member"])
    target = url(lab, f"inventory/orders/{order.pk}/")
    assert api(u["member"]).patch(target, {"status": "received"}, "json").status_code == 200


def test_an_overflowing_receipt_is_a_400_and_leaves_the_order_open(world, stocked):
    lab, u, *_ = world
    InventoryItem.objects.for_lab(lab).filter(pk=stocked.pk).update(
        quantity=Decimal("9999999999.99")
    )
    order = order_of(lab, u["member"], stocked)
    target = url(lab, f"inventory/orders/{order.pk}/")
    assert api(u["member"]).patch(target, {"status": "received"}, "json").status_code == 400
    assert InventoryOrder.objects.for_lab(lab).get(pk=order.pk).status == "requested"


def test_another_labs_item_reads_as_unknown(world, make_lab):
    lab, u, *_ = world
    foreign = InventoryItem.objects.create(lab=make_lab("Other"), name="Theirs", category="other")
    body = {"name": "Mine", "item": str(foreign.pk)}
    response = api(u["pi"]).post(url(lab, "inventory/orders/"), body, "json")
    assert response.status_code == 400 and "item" in response.json()


@pytest.mark.parametrize(
    "bad",
    [
        "http://vendor.example/x",
        "javascript:alert(1)",
        "https://user:pw@vendor.example/x",
        "https://",
        "ftp://vendor.example/x",
    ],
)
def test_order_links_must_be_https(world, bad):
    lab, u, *_ = world
    body = {"name": "Thing", "url": bad}
    response = api(u["member"]).post(url(lab, "inventory/orders/"), body, "json")
    assert response.status_code == 400 and "url" in response.json()


def test_order_quantity_must_be_positive(world):
    lab, u, *_ = world
    body = {"name": "Thing", "quantity": "0"}
    assert api(u["member"]).post(url(lab, "inventory/orders/"), body, "json").status_code == 400


def test_orders_are_audited_and_exported_safely(world):
    lab, u, *_ = world
    body = {"name": "=SUM(A1)", "url": "https://vendor.example/x"}
    client = api(u["member"])
    assert client.post(url(lab, "inventory/orders/"), body, "json").status_code == 201
    assert AuditEvent.objects.filter(action=AuditAction.INVENTORY_ORDER_CREATED).count() == 1
    export = client.get(url(lab, "inventory/orders/export/"))
    assert export.status_code == 200 and "'=SUM(A1)" in export.content.decode()
    event = AuditEvent.objects.get(action=AuditAction.INVENTORY_EXPORTED)
    assert event.metadata == {"rows": 1, "kind": "orders"}


def test_orders_list_is_scoped_to_the_lab(world, make_lab):
    lab, u, *_ = world
    other = make_lab("Other")
    InventoryOrder.objects.create(lab=other, name="Theirs", requested_by=u["pi"])
    order_of(lab, u["pi"])
    assert [o["name"] for o in api(u["viewer"]).get(url(lab, "inventory/orders/")).json()] == [
        "Tips"
    ]
