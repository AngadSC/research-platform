import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.management.commands.seed_pilot import FAKE_COMMIT, LAB_NAME
from labs.models import Lab
from projects.models import Project, ProjectMembership, ProjectRole
from provenance.models import ManuscriptLink


@pytest.fixture
def debug_on(settings):
    settings.DEBUG = True


def test_running_twice_yields_one_lab(debug_on):
    call_command("seed_pilot")
    call_command("seed_pilot")
    assert Lab.objects.filter(name=LAB_NAME).count() == 1


def test_manuscript_to_dataset_chain_has_commit(debug_on):
    call_command("seed_pilot")
    lab = Lab.objects.get(name=LAB_NAME)
    project = Project.objects.for_lab(lab).get(name="Pilot Attention Study (FAKE)")
    manuscript = ManuscriptLink.objects.for_lab(lab).get(project=project)
    result = manuscript.results.get()
    analysis = result.analysis
    assert analysis.code_commit == FAKE_COMMIT
    (dataset,) = analysis.datasets.all()
    assert dataset.version_label == "v2"
    assert dataset.previous_version.version_label == "v1"


def test_student_is_only_lead_of_archived_project(debug_on):
    call_command("seed_pilot")
    lab = Lab.objects.get(name=LAB_NAME)
    archived = Project.objects.for_lab(lab).get(name="Archived Survey (FAKE)")
    leads = ProjectMembership.objects.for_lab(lab).filter(project=archived, role=ProjectRole.LEAD)
    assert [m.user.email for m in leads] == ["student@example.test"]


def test_refuses_without_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_pilot")
