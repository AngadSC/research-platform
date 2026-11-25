import pytest
from django.core.management import call_command

from core.seed_full import people
from labs.models import Lab, LabMembership
from projects.models import Project


@pytest.fixture
def full_lab(settings, monkeypatch):
    settings.DEBUG = True
    call_command("seed_full_lab", stdout=open("/dev/null", "w"))  # noqa: SIM115
    return Lab.objects.get(name=people.LAB_NAME)


@pytest.mark.django_db
def test_seed_full_lab_makes_people_and_projects(full_lab):
    assert LabMembership.objects.for_lab(full_lab).count() == len(people.PEOPLE)
    statuses = set(Project.objects.for_lab(full_lab).values_list("status", flat=True))
    assert statuses == {"active", "planning", "paused", "completed", "archived"}
    # a rerun changes nothing
    call_command("seed_full_lab", stdout=open("/dev/null", "w"))  # noqa: SIM115
    assert Lab.objects.filter(name=people.LAB_NAME).count() == 1
