import pytest
from django.core.management import call_command

from core.management.commands.seed_wetlab_demo import FILES, LAB_NAME
from instruments.models import InstrumentFile
from labs.models import Lab
from monitoring.models import Sensor
from samples.models import Sample

pytestmark = pytest.mark.django_db


def test_runs_twice_and_parses_every_demo_file(settings):
    settings.DEBUG = True
    call_command("seed_wetlab_demo")
    samples = Sample.objects.for_lab(Lab.objects.get(name=LAB_NAME)).count()
    call_command("seed_wetlab_demo")
    (lab,) = Lab.objects.filter(name=LAB_NAME)
    files = InstrumentFile.objects.for_lab(lab)
    assert files.count() == len(FILES)
    assert set(files.values_list("status", flat=True)) == {"ok"}
    assert Sensor.objects.for_lab(lab).count() == 3
    assert Sample.objects.for_lab(lab).count() == samples
    batch = Sample.objects.for_lab(lab).get(name="MBP-CST06 batch 2 (FAKE)")
    assert batch.linked_files.count() == 2
