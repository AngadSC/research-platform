"""Protocols, taking reagents out of stock, the inventory on/off switch and CSV import (D227 to
D229). Who reaches each endpoint is in tests/test_permission_matrix.py."""

import uuid
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditEvent
from labs.admin_services import update_inventory_item
from labs.models import InventoryItem, InventoryUsage, LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Bench Lab")
    pi = make_user()
    join(pi, lab, LabRole.PI)
    member = make_user()
    join(member, lab, LabRole.MEMBER)
    project = make_project(lab, "Assay")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=member, role=ProjectRole.CONTRIBUTOR
    )
    item = InventoryItem.objects.create(
        lab=lab, name="Ethanol", category="reagent", quantity=10, unit="mL"
    )
    return lab, pi, member, project, item


def make_protocol(world, *, unit="mL", amount="2"):
    lab, pi, _, project, item = world
    url = reverse("labs:protocol-list", kwargs={"lab_id": lab.pk, "project_id": project.pk})
    body = {"name": "PCR", "reagents": [{"item": str(item.pk), "amount": amount, "unit": unit}]}
    r = api(pi).post(url, body, "json")
    assert r.status_code == 201, r.content
    return r.json()


def use(world, protocol, user=None, **body):
    lab, pi, *_ = world
    url = reverse("labs:protocol-use", kwargs={"lab_id": lab.pk, "protocol_id": protocol["id"]})
    reagent = body.pop("reagent", protocol["reagents"][0]["id"])
    payload = {"reagent": reagent, "request_id": str(uuid.uuid4()), **body}
    return api(user or pi).post(url, payload, "json")


def stock(world):
    return InventoryItem.objects.for_lab(world[0]).get(pk=world[4].pk).quantity


def test_using_takes_stock_exactly_once_even_when_the_click_repeats(world):
    protocol = make_protocol(world)
    rid = str(uuid.uuid4())
    first = use(world, protocol, request_id=rid)
    assert first.status_code == 201
    again = use(world, protocol, request_id=rid)
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
    assert stock(world) == 8
    assert InventoryUsage.objects.for_lab(world[0]).count() == 1
    assert AuditEvent.objects.filter(action="inventory.used").count() == 1


def test_never_below_zero_and_says_so(world):
    protocol = make_protocol(world)
    r = use(world, protocol, amount="11")
    assert r.status_code == 400
    assert r.json()["amount"].startswith("Only 10 mL of Ethanol is left")
    assert stock(world) == 10
    assert not InventoryUsage.objects.for_lab(world[0]).exists()
    assert use(world, protocol, amount="10").status_code == 201
    assert stock(world) == 0


def test_units_of_another_kind_are_refused_when_writing_and_when_using(world):
    lab, pi, _, project, item = world
    url = reverse("labs:protocol-list", kwargs={"lab_id": lab.pk, "project_id": project.pk})
    body = {"name": "Bad", "reagents": [{"item": str(item.pk), "amount": "1", "unit": "vials"}]}
    r = api(pi).post(url, body, "json")
    assert r.status_code == 400 and "cannot be taken from" in str(r.json()["reagents"])
    protocol = make_protocol(world)
    InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(unit="vials")  # changed afterwards
    r = use(world, protocol)
    assert r.status_code == 400 and "cannot be taken from" in str(r.json()["unit"])
    assert stock(world) == 10


def test_a_protocol_may_use_a_different_unit_of_the_same_kind(world):
    lab, *_ = world
    protocol = make_protocol(world, unit="uL", amount="500")  # 500 uL from a stock of 10 mL
    assert use(world, protocol).status_code == 201
    assert stock(world) == Decimal("9.5")


def _item_use_url(world):
    lab, *_, item = world
    return reverse(
        "labs:inventory-item-usage", kwargs={"lab_id": lab.pk, "inventoryitem_id": item.pk}
    )


def test_ten_ml_comes_off_a_hundred_litres(world):
    lab, pi, member, project, item = world
    InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(
        name="Water", quantity=100, unit="L"
    )
    r = api(member).post(
        _item_use_url(world),
        {"amount": "10", "unit": "mL", "request_id": str(uuid.uuid4())},
        "json",
    )
    assert r.status_code == 201, r.content
    assert stock(world) == Decimal("99.99")
    assert r.json()["unit"] == "mL" and Decimal(r.json()["deducted"]) == Decimal("0.01")
    # The log shows it, and the whole lab can read it.
    log = api(pi).get(_item_use_url(world)).json()
    assert len(log) == 1 and log[0]["used_by"]["id"] == str(member.pk)


def test_a_use_logged_twice_by_one_click_takes_stock_once(world):
    lab, _, member, *_ = world
    body = {"amount": "1", "unit": "mL", "request_id": str(uuid.uuid4())}
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    assert stock(world) == 9


def test_a_use_larger_than_the_stock_is_refused_and_leaves_nothing(world):
    _, _, member, *_ = world
    r = api(member).post(
        _item_use_url(world),
        {"amount": "11", "unit": "mL", "request_id": str(uuid.uuid4())},
        "json",
    )
    assert r.status_code == 400 and "is left" in str(r.json())
    assert stock(world) == 10
    assert InventoryUsage.objects.for_lab(world[0]).count() == 0


def test_a_use_in_the_wrong_kind_of_unit_is_refused(world):
    _, _, member, *_ = world
    r = api(member).post(
        _item_use_url(world),
        {"amount": "1", "unit": "g", "request_id": str(uuid.uuid4())},
        "json",
    )
    assert r.status_code == 400 and "cannot be taken from" in str(r.json())
    assert stock(world) == 10


def test_undoing_a_use_logged_on_an_item_puts_back_what_left(world):
    lab, pi, member, project, item = world
    InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(quantity=100, unit="L")
    usage = (
        api(member)
        .post(
            _item_use_url(world),
            {"amount": "10", "unit": "mL", "request_id": str(uuid.uuid4())},
            "json",
        )
        .json()
    )
    url = reverse(
        "labs:inventory-item-usage-reverse",
        kwargs={"lab_id": lab.pk, "itemusage_id": usage["id"]},
    )
    assert api(pi).post(url).status_code == 200  # an inventory manager may
    assert stock(world) == 100
    assert api(member).post(url).status_code == 400  # already undone


def test_a_use_can_count_towards_a_project_the_person_edits(world):
    lab, _, member, project, item = world
    r = api(member).post(
        _item_use_url(world),
        {"amount": "1", "unit": "mL", "project": str(project.pk), "request_id": str(uuid.uuid4())},
        "json",
    )
    assert r.status_code == 201 and r.json()["project_name"] == project.name
    outsider = api(member).post(
        _item_use_url(world),
        {
            "amount": "1",
            "unit": "mL",
            "project": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
        },
        "json",
    )
    assert outsider.status_code == 400


def test_reverse_puts_stock_back_exactly_once_and_is_audited(world):
    lab, pi, member, *_ = world
    protocol = make_protocol(world)
    usage = use(world, protocol, member).json()
    assert stock(world) == 8
    url = reverse(
        "labs:inventory-usage-reverse", kwargs={"lab_id": lab.pk, "inventoryusage_id": usage["id"]}
    )
    r = api(member).post(url)
    assert r.status_code == 200 and r.json()["reversed_at"] is not None
    assert stock(world) == 10
    assert api(pi).post(url).status_code == 400  # already reversed; stock untouched
    assert stock(world) == 10
    assert AuditEvent.objects.filter(action="inventory.use_reversed").count() == 1


def test_an_item_a_protocol_uses_cannot_be_deleted(world):
    lab, pi, _, _, item = world
    make_protocol(world)
    url = reverse("labs:inventory-detail", kwargs={"lab_id": lab.pk, "inventoryitem_id": item.pk})
    assert api(pi).delete(url).status_code == 409
    assert InventoryItem.objects.for_lab(lab).filter(pk=item.pk).exists()


def test_an_item_whose_uses_were_all_undone_can_be_deleted(world):
    lab, pi, member, _, item = world
    detail = reverse(
        "labs:inventory-detail", kwargs={"lab_id": lab.pk, "inventoryitem_id": item.pk}
    )

    def log_use():
        body = {"amount": "1", "unit": "mL", "request_id": str(uuid.uuid4())}
        return api(member).post(_item_use_url(world), body, "json").json()["id"]

    undone, kept = log_use(), log_use()
    undo = reverse(
        "labs:inventory-item-usage-reverse", kwargs={"lab_id": lab.pk, "itemusage_id": undone}
    )
    assert api(member).post(undo).status_code == 200
    assert api(pi).delete(detail).status_code == 409  # one real use is still on record
    undo_kept = reverse(
        "labs:inventory-item-usage-reverse", kwargs={"lab_id": lab.pk, "itemusage_id": kept}
    )
    assert api(member).post(undo_kept).status_code == 200
    assert api(pi).delete(detail).status_code == 204
    assert not InventoryItem.objects.for_lab(lab).filter(pk=item.pk).exists()
    assert not InventoryUsage.objects.for_lab(lab).exists()
    assert AuditEvent.objects.filter(action="inventory.used").count() == 2  # history stays


def test_turning_inventory_off_blocks_every_inventory_endpoint(world):
    lab, pi, _, project, item = world
    make_protocol(world)
    detail = reverse("labs:lab-detail", kwargs={"lab_id": lab.pk})
    r = api(pi).patch(detail, {"inventory_enabled": False}, "json")
    assert r.status_code == 200 and r.json()["inventory_enabled"] is False
    urls = [
        reverse(n, kwargs={"lab_id": lab.pk})
        for n in ("labs:inventory-list", "labs:inventory-export", "labs:order-list")
    ] + [
        reverse("labs:protocol-list", kwargs={"lab_id": lab.pk, "project_id": project.pk}),
        reverse("labs:inventory-usage", kwargs={"lab_id": lab.pk, "project_id": project.pk}),
    ]
    for url in urls:
        got = api(pi).get(url)
        assert got.status_code == 403 and "turned off" in got.json()["detail"], url
    span = {"from": "2030-01-01", "to": "2030-02-01"}
    cal = api(pi).get(reverse("labs:calendar", kwargs={"lab_id": lab.pk}), span)
    assert cal.status_code == 200


def csv_upload(body, name="stock.csv"):
    return SimpleUploadedFile(name, body if isinstance(body, bytes) else body.encode(), "text/csv")


def post_import(world, body, *, commit=False):
    lab, pi, *_ = world
    url = reverse("labs:inventory-import", kwargs={"lab_id": lab.pk})
    return api(pi).post(url, {"file": csv_upload(body), "commit": commit}, format="multipart")


def test_preview_reports_row_errors_and_writes_nothing(world):
    before = InventoryItem.objects.for_lab(world[0]).count()
    r = post_import(world, "Name,Category,Quantity,Unit\nFlask,equipment,2,\nGel,pets,1,\n")
    assert r.status_code == 200
    body = r.json()
    assert (body["valid"], body["invalid"], body["imported"]) == (1, 1, 0)
    assert body["rows"][1]["row"] == 3 and "category" in body["rows"][1]["errors"]
    assert InventoryItem.objects.for_lab(world[0]).count() == before


def test_editing_an_item_keeps_stock_used_since_it_was_read(world):
    lab, pi, member, project, item = world
    stale = InventoryItem.objects.for_lab(lab).get(pk=item.pk)  # read while quantity is 10
    assert use(world, make_protocol(world, amount="3"), member).status_code == 201
    update_inventory_item(stale, user=pi, data={"notes": "New note"})
    item.refresh_from_db()
    assert (item.quantity, item.notes) == (7, "New note")


def test_a_row_with_no_quantity_says_it_will_be_added_with_one(world):
    body = post_import(world, "Name,Category\nPipette,equipment\n").json()
    assert body["rows"][0]["quantity"] == "1" and "quantity of 1" in body["rows"][0]["warning"]


def test_a_file_with_any_bad_row_imports_nothing(world):
    before = InventoryItem.objects.for_lab(world[0]).count()
    r = post_import(world, "Name,Category\nFlask,equipment\nGel,pets\n", commit=True)
    assert r.status_code == 400 and r.json()["invalid"] == 1
    assert InventoryItem.objects.for_lab(world[0]).count() == before


def test_a_clean_file_imports_every_row_and_warns_about_duplicates(world):
    csv_text = "Name,Category,Quantity,Unit\nFlask,equipment,2,box\nEthanol,reagent,5,mL\n"
    r = post_import(world, csv_text, commit=True)
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2 and "already exists" in body["rows"][1]["warning"]
    assert InventoryItem.objects.for_lab(world[0]).filter(name="Flask").get().quantity == 2
    assert AuditEvent.objects.filter(action="inventory.imported").count() == 1


def test_import_reads_alert_level_and_names_the_valid_categories(world):
    csv_text = "Name,Category,Low stock at\nTips,consumable,20\nGel,pets,1\n"
    body = post_import(world, csv_text).json()
    assert body["ignored_columns"] == [] and body["valid"] == 1
    assert (
        "equipment, reagent, consumable, software_licence, other"
        in body["rows"][1]["errors"]["category"]
    )
    csv_text = "Name,Category,Low_stock_at,Location\nTips,consumable,20,Shelf 2\n"
    post_import(world, csv_text, commit=True)
    tips = InventoryItem.objects.for_lab(world[0]).get(name="Tips")
    assert (tips.low_stock_at, tips.location) == (20, "Shelf 2")
    assert AuditEvent.objects.get(action="inventory.imported").metadata["rows"] == 1


def test_limits_and_unreadable_files(world):
    too_many = "Name,Category\n" + "".join(f"Item {i},other\n" for i in range(1001))
    assert "Too many rows" in str(post_import(world, too_many).json())
    assert "too large" in str(post_import(world, b"x" * (1024 * 1024 + 1)).json())
    assert "Excel" in str(post_import(world, b"PK\x03\x04 not really").json())
    assert "first row" in str(post_import(world, "Colour,Size\nred,big\n").json())


# ---------------------------------------------------------------- low-stock alerts (D331)


def _alerts(lab):
    from core.models import Notification

    return list(Notification.objects.for_lab(lab).filter(kind="low_stock"))


def test_stock_falling_to_the_alert_level_tells_the_pi_and_the_owner_once(world, make_user, join):
    from labs.models import LabRole

    lab, pi, member, project, item = world
    admin = make_user()
    join(admin, lab, LabRole.LAB_ADMIN)
    InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(
        quantity=10, low_stock_at=5, owner=member
    )
    body = {"amount": "4", "unit": "mL", "request_id": str(uuid.uuid4())}
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    assert _alerts(lab) == []  # 6 mL left: still above the level
    body = {"amount": "2", "unit": "mL", "request_id": str(uuid.uuid4())}
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    who = {n.recipient_id for n in _alerts(lab)}
    assert who == {pi.pk, admin.pk, member.pk}  # PIs, admins and the owner
    assert "running low" in _alerts(lab)[0].title and "4 mL left" in _alerts(lab)[0].body
    body = {"amount": "1", "unit": "mL", "request_id": str(uuid.uuid4())}
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    assert len(_alerts(lab)) == 3  # already below: no second alert today


def test_an_item_without_a_level_never_alerts_and_the_level_is_shown(world):
    lab, pi, member, _, item = world
    body = {"amount": "9", "unit": "mL", "request_id": str(uuid.uuid4())}
    assert api(member).post(_item_use_url(world), body, "json").status_code == 201
    assert _alerts(lab) == []
    url = reverse("labs:inventory-detail", kwargs={"lab_id": lab.pk, "inventoryitem_id": item.pk})
    assert api(pi).patch(url, {"low_stock_at": "2"}, "json").json()["low"] is True  # 1 mL left
    assert api(pi).patch(url, {"low_stock_at": None}, "json").json()["low"] is False
