"""Pin for everyone (D351). Who may reach each route is also in the permission matrix; this
covers lab documents, ordering, visibility and the audit trail."""

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents import services
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def world(make_lab, make_user, join, make_project):
    lab = make_lab("Lab")
    people = {n: make_user() for n in ("pi", "member", "lead", "contrib", "outsider")}
    join(people["pi"], lab, LabRole.PI)
    for n in ("member", "lead", "contrib"):
        join(people[n], lab, LabRole.MEMBER)
    other = make_lab("Other lab")
    join(people["outsider"], other, LabRole.PI)
    project = make_project(lab)
    ProjectMembership.objects.create(
        lab=lab, project=project, user=people["lead"], role=ProjectRole.LEAD
    )
    ProjectMembership.objects.create(
        lab=lab, project=project, user=people["contrib"], role=ProjectRole.CONTRIBUTOR
    )
    sop = services.create_document(lab=lab, user=people["pi"], title="SOP", content=[])
    manual = services.create_document(lab=lab, user=people["pi"], title="Manual", content=[])
    notes = services.create_document(
        project=project, user=people["lead"], title="Notes", content=[]
    )
    return lab, people, sop, manual, notes


def pin_url(lab, doc):
    return f"/api/labs/{lab.pk}/documents/{doc.pk}/pin/"


def start_here(lab, user):
    return [r["title"] for r in client(user).get(f"/api/labs/{lab.pk}/start-here/").json()]


def test_only_lab_managers_pin_a_lab_document(world):
    lab, people, sop, *_ = world
    for who in ("member", "lead", "contrib"):
        assert client(people[who]).post(pin_url(lab, sop)).status_code == 403
    assert client(people["outsider"]).post(pin_url(lab, sop)).status_code == 404
    assert client(people["pi"]).post(pin_url(lab, sop)).status_code == 204
    assert start_here(lab, people["member"]) == ["SOP"]


def test_only_the_lead_pins_a_project_document_and_only_its_members_see_it(world):
    lab, people, _, _, notes = world
    assert client(people["contrib"]).post(pin_url(lab, notes)).status_code == 403
    assert client(people["member"]).post(pin_url(lab, notes)).status_code == 404
    assert client(people["lead"]).post(pin_url(lab, notes)).status_code == 204
    assert start_here(lab, people["contrib"]) == ["Notes"]
    assert start_here(lab, people["member"]) == []  # not on the project
    assert start_here(lab, people["pi"]) == ["Notes"]


def test_unpin_audits_and_is_manager_only(world):
    lab, people, sop, *_ = world
    client(people["pi"]).post(pin_url(lab, sop))
    client(people["pi"]).post(pin_url(lab, sop))  # pinning twice changes nothing
    assert client(people["member"]).delete(pin_url(lab, sop)).status_code == 403
    assert client(people["pi"]).delete(pin_url(lab, sop)).status_code == 204
    assert start_here(lab, people["member"]) == []
    kinds = list(AuditEvent.objects.filter(target_id=sop.pk).values_list("action", flat=True))
    assert kinds.count(AuditAction.DOCUMENT_PINNED) == 1
    assert kinds.count(AuditAction.DOCUMENT_UNPINNED) == 1


def test_reorder_swaps_within_lab_documents_only(world):
    lab, people, sop, manual, notes = world
    pi = client(people["pi"])
    for d in (sop, manual, notes):
        pi.post(pin_url(lab, d))
    assert start_here(lab, people["pi"]) == ["SOP", "Manual", "Notes"]
    assert pi.patch(pin_url(lab, manual), {"direction": "up"}, format="json").status_code == 204
    assert start_here(lab, people["pi"]) == ["Manual", "SOP", "Notes"]
    pi.patch(pin_url(lab, notes), {"direction": "up"}, format="json")  # first of its project
    assert start_here(lab, people["pi"]) == ["Manual", "SOP", "Notes"]
    assert (
        client(people["member"]).patch(pin_url(lab, sop), {"direction": "up"}, format="json")
    ).status_code == 403


def test_a_deleted_document_drops_off_the_list(world):
    lab, people, sop, *_ = world
    client(people["pi"]).post(pin_url(lab, sop))
    assert client(people["pi"]).delete(f"/api/labs/{lab.pk}/documents/{sop.pk}/").status_code == 204
    assert start_here(lab, people["member"]) == []
