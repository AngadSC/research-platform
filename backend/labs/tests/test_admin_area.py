"""Admin area (D146-D151): validation, audit, institution starters, inventory rules.
Permissions and cross-lab ids are in tests/test_permission_matrix.py."""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.institution_starters import STARTER_RESOURCES, UALBERTA
from labs.models import InstitutionResource, InventoryItem, LabRole, OnboardingCompletion

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Admin Lab")
    users = {}
    for name, role in [("pi", LabRole.PI), ("member", LabRole.MEMBER), ("viewer", LabRole.VIEWER)]:
        users[name] = make_user()
        join(users[name], lab, role)
    return lab, users


def api(user):
    c = APIClient()
    c.force_login(user)
    return c


def url(lab, tail):
    return f"/api/labs/{lab.pk}/{tail}"


def actions():
    return list(AuditEvent.objects.values_list("action", flat=True))


# ---------------------------------------------------------------- lab details


def test_lab_details_edit_is_audited(world):
    lab, u = world
    body = {
        "name": "Renamed",
        "department": "Psychology",
        "description": "We study attention.",
        "address": "1 Main St",
        "contact_email": "lab@example.edu",
        "website": "https://lab.example.edu",
    }
    r = api(u["pi"]).patch(url(lab, ""), body, "json")
    assert r.status_code == 200 and r.json()["website"] == "https://lab.example.edu"
    event = AuditEvent.objects.get(action=AuditAction.LAB_UPDATED)
    assert set(event.metadata["changed"]) == set(body)


@pytest.mark.parametrize(
    "body", [{"website": "javascript:alert(1)"}, {"contact_email": "nope"}, {"name": ""}]
)
def test_lab_details_validation(world, body):
    lab, u = world
    assert api(u["pi"]).patch(url(lab, ""), body, "json").status_code == 400


def test_picking_ualberta_loads_starters_once(world):
    lab, u = world
    c = api(u["pi"])
    assert (
        c.patch(url(lab, ""), {"institution_name": "university of alberta"}, "json").status_code
        == 200
    )
    lab.refresh_from_db()
    assert lab.institution.name == UALBERTA
    expected = len(STARTER_RESOURCES[UALBERTA])
    assert InstitutionResource.objects.for_lab(lab).count() == expected
    call_command("load_institution_resources")
    call_command("load_institution_resources")
    assert InstitutionResource.objects.for_lab(lab).count() == expected


def test_other_institution_gets_no_starters(world):
    lab, u = world
    api(u["pi"]).patch(url(lab, ""), {"institution_name": "Elsewhere University"}, "json")
    assert InstitutionResource.objects.for_lab(lab).count() == 0


# ---------------------------------------------------------------- resources


@pytest.mark.parametrize(
    "bad",
    [
        "http://example.edu/x",
        "javascript:alert(1)",
        "ftp://example.edu/x",
        "https://user:pw@example.edu/x",
        "example.edu",
    ],
)
def test_resource_urls_must_be_https(world, bad):
    lab, u = world
    r = api(u["pi"]).post(
        url(lab, "institution-resources/"), {"category": "ethics", "title": "T", "url": bad}, "json"
    )
    assert r.status_code == 400 and "url" in r.json()


def test_resource_crud_audited_filtered_and_unique(world):
    lab, u = world
    c = api(u["pi"])
    body = {"category": "funding", "title": "Grants", "url": "https://example.edu/g"}
    created = c.post(url(lab, "institution-resources/"), body, "json")
    assert created.status_code == 201
    assert c.post(url(lab, "institution-resources/"), body, "json").status_code == 400  # dup url
    c.post(
        url(lab, "institution-resources/"),
        {**body, "category": "ethics", "url": "https://example.edu/e"},
        "json",
    )
    listed = api(u["viewer"]).get(url(lab, "institution-resources/?category=ethics")).json()
    assert [r["title"] for r in listed] == ["Grants"] and listed[0]["category"] == "ethics"
    rid = created.json()["id"]
    assert (
        c.patch(url(lab, f"institution-resources/{rid}/"), {"order": 3}, "json").status_code == 200
    )
    assert c.delete(url(lab, f"institution-resources/{rid}/")).status_code == 204
    assert {
        AuditAction.INSTITUTION_RESOURCE_CREATED,
        AuditAction.INSTITUTION_RESOURCE_UPDATED,
        AuditAction.INSTITUTION_RESOURCE_DELETED,
    } <= set(actions())


# ---------------------------------------------------------------- onboarding


def test_onboarding_items_and_completion(world):
    lab, u = world
    c = api(u["pi"])
    r = c.post(
        url(lab, "onboarding-items/"),
        {"kind": "new_member", "title": "Sign the data policy", "url": "https://example.edu/p"},
        "json",
    )
    assert r.status_code == 201 and r.json()["required"] is True
    iid = r.json()["id"]
    bad = c.post(
        url(lab, "onboarding-items/"),
        {"kind": "new_member", "title": "x", "url": "http://a.b"},
        "json",
    )
    assert bad.status_code == 400
    done = {"user": str(u["member"].pk), "done": True}
    r = c.post(url(lab, f"onboarding-items/{iid}/completions/"), done, "json")
    assert r.json()["completed_user_ids"] == [str(u["member"].pk)]
    c.post(url(lab, f"onboarding-items/{iid}/completions/"), done, "json")  # idempotent
    assert OnboardingCompletion.objects.for_lab(lab).count() == 1
    r = c.post(url(lab, f"onboarding-items/{iid}/completions/"), {**done, "done": False}, "json")
    assert r.json()["completed_user_ids"] == []
    assert actions().count(AuditAction.ONBOARDING_COMPLETION_CHANGED) == 2
    assert c.delete(url(lab, f"onboarding-items/{iid}/")).status_code == 204


def test_completion_for_a_non_member_is_rejected(world, make_user):
    lab, u = world
    c = api(u["pi"])
    iid = c.post(url(lab, "onboarding-items/"), {"kind": "departing", "title": "x"}, "json").json()[
        "id"
    ]
    stranger = make_user()
    r = c.post(
        url(lab, f"onboarding-items/{iid}/completions/"),
        {"user": str(stranger.pk), "done": True},
        "json",
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- inventory


def test_inventory_member_edits_viewer_reads(world):
    lab, u = world
    body = {"name": "Centrifuge", "category": "equipment", "quantity": "2", "location": "B12"}
    assert api(u["viewer"]).post(url(lab, "inventory/"), body, "json").status_code == 403
    r = api(u["member"]).post(url(lab, "inventory/"), body, "json")
    assert r.status_code == 201
    iid = r.json()["id"]
    assert api(u["viewer"]).get(url(lab, f"inventory/{iid}/")).status_code == 200
    assert (
        api(u["viewer"]).patch(url(lab, f"inventory/{iid}/"), {"notes": "x"}, "json").status_code
        == 403
    )
    assert (
        api(u["member"])
        .patch(url(lab, f"inventory/{iid}/"), {"status": "in_repair"}, "json")
        .status_code
        == 200
    )
    assert api(u["member"]).delete(url(lab, f"inventory/{iid}/")).status_code == 204
    assert [a for a in actions() if a.startswith("inventory_item.")] == [
        "inventory_item.created",
        "inventory_item.updated",
        "inventory_item.deleted",
    ]


@pytest.mark.parametrize(
    "extra", [{"quantity": "-1"}, {"category": "pets"}, {"purchase_date": "not-a-date"}]
)
def test_inventory_validation(world, extra):
    lab, u = world
    body = {"name": "X", "category": "other", **extra}
    assert api(u["pi"]).post(url(lab, "inventory/"), body, "json").status_code == 400


def test_inventory_owner_must_be_a_lab_member(world, make_user):
    lab, u = world
    body = {"name": "X", "category": "other"}
    stranger = make_user()
    r = api(u["pi"]).post(url(lab, "inventory/"), {**body, "owner": str(stranger.pk)}, "json")
    assert r.status_code == 400 and "owner" in r.json()
    r = api(u["pi"]).post(url(lab, "inventory/"), {**body, "owner": str(u["member"].pk)}, "json")
    assert r.status_code == 201 and r.json()["owner"]["id"] == str(u["member"].pk)


def test_inventory_search_sort_and_csv_export(world):
    lab, u = world
    for name, cat in [
        ("Pipette", "equipment"),
        ("=cmd|' /C calc'!A0", "other"),
        ("Agar", "reagent"),
    ]:
        InventoryItem.objects.create(lab=lab, name=name, category=cat, location="Room 1")
    c = api(u["viewer"])
    names = [i["name"] for i in c.get(url(lab, "inventory/?q=agar")).json()]
    assert names == ["Agar"]
    desc = [i["name"] for i in c.get(url(lab, "inventory/?ordering=-name")).json()]
    assert desc[0] == "Pipette" and len(desc) == 3
    assert len(c.get(url(lab, "inventory/?ordering=;drop")).json()) == 3  # unknown ordering ignored
    r = c.get(url(lab, "inventory/export/?category=other"))
    assert r["Content-Type"].startswith("text/csv")
    text = r.content.decode()
    assert text.startswith("Name,Category") and "'=cmd" in text and "Pipette" not in text
    assert AuditAction.INVENTORY_EXPORTED in actions()
