"""Non-human subjects of a project: animals, strains, cell lines, samples (D329). Who reaches each
endpoint is in tests/test_permission_matrix.py."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditEvent
from labs.models import LabRole, Subject
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Mouse Lab")
    member = make_user()
    join(member, lab, LabRole.MEMBER)
    project = make_project(lab, "Cohort study")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=member, role=ProjectRole.CONTRIBUTOR
    )
    return lab, member, project


def _list(world):
    lab, _, project = world
    return reverse("labs:subject-list", kwargs={"lab_id": lab.pk, "project_id": project.pk})


def test_a_project_keeps_animals_strains_and_cell_lines(world):
    _, member, project = world
    for body in (
        {
            "kind": "animal",
            "code": "M-001",
            "species": "Mus musculus",
            "line": "C57BL/6J",
            "sex": "female",
            "count": 8,
            "location": "Rack 2, cage 4",
            "approval": "AUP-2026-14",
        },
        {
            "kind": "microbe",
            "code": "EC-7",
            "species": "E. coli",
            "line": "DH5alpha",
            "passage": "P3",
        },
        {"kind": "cell_line", "code": "HEK-1", "line": "HEK293", "passage": "P12"},
    ):
        r = api(member).post(_list(world), body, "json")
        assert r.status_code == 201, r.content
    rows = api(member).get(_list(world)).json()
    assert [r["code"] for r in rows] == ["EC-7", "HEK-1", "M-001"]
    assert rows[2]["count"] == 8 and rows[2]["status"] == "active"
    assert AuditEvent.objects.filter(action="subject.created").count() == 3


def test_labels_are_unique_in_a_project_and_blank_ones_refused(world):
    _, member, _ = world
    assert (
        api(member).post(_list(world), {"kind": "animal", "code": "M-1"}, "json").status_code == 201
    )
    dupe = api(member).post(_list(world), {"kind": "animal", "code": " M-1 "}, "json")
    assert dupe.status_code == 400 and "already used" in str(dupe.json())
    blank = api(member).post(_list(world), {"kind": "animal", "code": "   "}, "json")
    assert blank.status_code == 400


def test_editing_and_removing_a_subject_is_audited(world):
    lab, member, project = world
    s = Subject.objects.create(
        lab=lab, project=project, kind="animal", code="M-9", created_by=member
    )
    url = reverse("labs:subject-detail", kwargs={"lab_id": lab.pk, "subject_id": s.pk})
    r = api(member).patch(url, {"status": "gone", "notes": "Euthanised at endpoint"}, "json")
    assert r.status_code == 200 and r.json()["status"] == "gone"
    assert api(member).delete(url).status_code == 204
    assert not Subject.objects.for_lab(lab).filter(pk=s.pk).exists()
    assert AuditEvent.objects.filter(action="subject.updated").exists()
    assert AuditEvent.objects.filter(action="subject.deleted").exists()


def test_the_export_is_a_spreadsheet_safe_from_formulas(world):
    lab, member, project = world
    Subject.objects.create(
        lab=lab, project=project, kind="sample", code="=cmd()", created_by=member
    )
    url = reverse("labs:subject-export", kwargs={"lab_id": lab.pk, "project_id": project.pk})
    r = api(member).get(url)
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv")
    body = r.content.decode()
    assert body.splitlines()[0].startswith("kind,code,species") and "'=cmd()" in body


def test_a_project_says_what_it_studies(world):
    lab, member, project = world
    url = reverse("projects:project-detail", kwargs={"lab_id": lab.pk, "project_id": project.pk})
    assert api(member).get(url).json()["study_types"] == ["human"]  # until someone changes it
    ProjectMembership.objects.for_lab(lab).filter(project=project, user=member).update(
        role=ProjectRole.LEAD
    )
    r = api(member).patch(url, {"study_types": ["animal", "cell_line", "animal"]}, "json")
    assert r.status_code == 200 and r.json()["study_types"] == ["animal", "cell_line"]
    assert api(member).patch(url, {"study_types": ["people"]}, "json").status_code == 400
