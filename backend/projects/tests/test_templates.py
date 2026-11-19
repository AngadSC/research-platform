"""Project templates (D235)."""

import datetime

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from labs.models import LabRole
from projects.models import Project, ProjectDeadline, ProjectMembership, Task
from projects.templates import TEMPLATES
from provenance.models import WORKFLOW_STAGES, ReviewItem

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Lab")
    member = make_user()
    join(member, lab, LabRole.MEMBER)
    client = APIClient()
    client.force_authenticate(member)
    return lab, client


def create(lab, client, **body):
    return client.post(f"/api/labs/{lab.pk}/projects/", {"name": "New", **body}, format="json")


def test_every_template_only_names_real_workflow_stages():
    for plan in TEMPLATES.values():
        assert set(plan["not_needed"]) <= set(WORKFLOW_STAGES)
        assert "funding" not in plan["not_needed"]  # D226: only a PI may mark funding


def test_template_fills_in_tasks_deadlines_and_workflow(world):
    lab, client = world
    response = create(lab, client, template="secondary_data_analysis", start_date="2027-01-01")
    assert response.status_code == 201
    project = Project.objects.for_lab(lab).get()
    plan = TEMPLATES["secondary_data_analysis"]
    tasks = Task.objects.for_lab(lab).filter(project=project).order_by("position")
    assert [t.title for t in tasks] == [t for t, _ in plan["tasks"]]
    assert tasks[0].due_date == datetime.date(2027, 1, 1) + datetime.timedelta(
        days=plan["tasks"][0][1]
    )
    assert ProjectDeadline.objects.for_lab(lab).filter(project=project).count() == len(
        plan["deadlines"]
    )
    assert ReviewItem.objects.for_lab(lab).filter(project=project).count() == 1
    project.refresh_from_db()
    assert project.workflow_marked_done == ["participants"]
    event = AuditEvent.objects.get(action=AuditAction.PROJECT_CREATED)
    assert event.metadata == {"template": "secondary_data_analysis"}


def test_no_template_adds_nothing(world):
    lab, client = world
    assert create(lab, client).status_code == 201
    assert not Task.objects.for_lab(lab).exists()
    assert not ProjectDeadline.objects.for_lab(lab).exists()


def test_unknown_template_is_refused(world):
    lab, client = world
    assert create(lab, client, template="nope").status_code == 400
    assert not Project.objects.for_lab(lab).exists()


def test_update_ignores_template(world):
    lab, client = world
    pid = create(lab, client).json()["id"]
    url = f"/api/labs/{lab.pk}/projects/{pid}/"
    assert client.patch(url, {"template": "survey_study"}, format="json").status_code == 200
    assert not Task.objects.for_lab(lab).exists()


def test_new_templates_make_folders_and_tasks(world):
    from documents.models import Folder

    lab, client = world
    for name in ("thesis_chapter", "ra_onboarding", "conference_poster"):
        assert create(lab, client, template=name, name=name).status_code == 201
        project = Project.objects.for_lab(lab).get(name=name)
        plan = TEMPLATES[name]
        assert Task.objects.for_lab(lab).filter(project=project).count() == len(plan["tasks"])
        folders = Folder.objects.for_lab(lab).filter(project=project)
        assert sorted(f.name for f in folders) == sorted(plan["folders"])


# The New project dialog says "N tasks will be created" from this table (ProjectFormDialog.tsx).
DIALOG_TASK_COUNTS = {
    "honours_thesis": 9,
    "survey_study": 9,
    "secondary_data_analysis": 8,
    "experiment": 9,
    "thesis_chapter": 7,
    "ra_onboarding": 8,
    "conference_poster": 8,
}


def test_dialog_task_counts_match_the_templates():
    assert DIALOG_TASK_COUNTS == {k: len(v["tasks"]) for k, v in TEMPLATES.items()}


def test_lead_and_members_join_and_template_tasks_stay_unassigned(world, make_user, join):
    lab, client = world
    student, other = make_user(), make_user()
    join(student, lab, LabRole.MEMBER)
    join(other, lab, LabRole.MEMBER)
    r = create(
        lab,
        client,
        template="honours_thesis",
        lead=str(student.pk),
        members=[str(other.pk), str(student.pk)],
    )
    assert r.status_code == 201, r.content
    project = Project.objects.for_lab(lab).get()
    roles = {
        m.user_id: m.role for m in ProjectMembership.objects.for_lab(lab).filter(project=project)
    }
    assert roles[student.pk] == "lead" and roles[other.pk] == "contributor"
    assert len(roles) == 3  # the creator, the lead and one member: no duplicates
    assert not Task.objects.for_lab(lab).filter(project=project, assignee__isnull=False).exists()


def test_someone_outside_the_lab_cannot_be_added_at_creation(world, make_user):
    lab, client = world
    stranger = make_user()
    r = create(lab, client, members=[str(stranger.pk)])
    assert r.status_code == 400
    assert not Project.objects.for_lab(lab).exists()  # nothing half-made
