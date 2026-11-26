import pytest
from django.core.management import call_command

from core.management.commands.seed_wetlab_demo import FILES, LAB_NAME
from instruments.models import InstrumentFile
from labs.models import Lab
from monitoring.models import Sensor

pytestmark = pytest.mark.django_db


def test_runs_twice_and_parses_every_demo_file(settings):
    settings.DEBUG = True
    call_command("seed_wetlab_demo")
    call_command("seed_wetlab_demo")
    (lab,) = Lab.objects.filter(name=LAB_NAME)
    files = InstrumentFile.objects.for_lab(lab)
    assert files.count() == len(FILES)
    assert set(files.values_list("status", flat=True)) == {"ok"}
    assert Sensor.objects.for_lab(lab).count() == 3
