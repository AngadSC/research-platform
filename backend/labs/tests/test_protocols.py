"""Protocols, taking reagents out of stock, the inventory on/off switch and CSV import (D227 to
D229). Who reaches each endpoint is in tests/test_permission_matrix.py."""

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditEvent
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


def test_units_must_match_when_writing_and_when_using(world):
    lab, pi, _, project, item = world
    url = reverse("labs:protocol-list", kwargs={"lab_id": lab.pk, "project_id": project.pk})
    body = {"name": "Bad", "reagents": [{"item": str(item.pk), "amount": "1", "unit": "L"}]}
    r = api(pi).post(url, body, "json")
    assert r.status_code == 400 and "We do not convert units" in str(r.json()["reagents"])
    protocol = make_protocol(world)  # "mL" matches "ml"-style case differences too
    InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(unit="uL")  # changed afterwards
    r = use(world, protocol)
    assert r.status_code == 400 and "We do not convert units" in str(r.json()["amount"])
    assert stock(world) == 10


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


def test_limits_and_unreadable_files(world):
    too_many = "Name,Category\n" + "".join(f"Item {i},other\n" for i in range(1001))
    assert "Too many rows" in str(post_import(world, too_many).json())
    assert "too large" in str(post_import(world, b"x" * (1024 * 1024 + 1)).json())
    assert "Excel" in str(post_import(world, b"PK\x03\x04 not really").json())
    assert "first row" in str(post_import(world, "Colour,Size\nred,big\n").json())
