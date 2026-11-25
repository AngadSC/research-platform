import pytest

from core.seed_full import people, research
from documents.models import Attachment, Document
from labs.models import LabChatMessage
from labs.services import create_lab
from papers.models import Paper
from participants.models import Participant
from projects.models import ChatMessage, Project, Task
from provenance.models import Analysis, DatasetRecord, ManuscriptLink

pytestmark = pytest.mark.django_db


def test_research_seed_fills_the_lab_and_stays_in_it():
    ctx = people.build("x")
    research.seed(ctx)
    lab = ctx.lab
    sleep = ctx.projects["sleep"]
    assert 10 <= Task.objects.for_lab(lab).filter(project=sleep).count() <= 25
    assert Task.objects.for_lab(lab).filter(assignee__isnull=True).exists()
    assert 15 <= ChatMessage.objects.for_lab(lab).filter(project=sleep).count() <= 40
    assert LabChatMessage.objects.for_lab(lab).count() == 30
    assert Document.objects.for_lab(lab).count() >= 30
    assert Attachment.objects.for_lab(lab).exists()
    assert Paper.objects.for_lab(lab).count() == 25
    assert Analysis.objects.for_lab(lab).count() >= 10
    assert ManuscriptLink.objects.for_lab(lab).exists()
    ageing = ctx.projects["ageing"]
    assert Participant.objects.for_lab(lab).filter(project=ageing).count() == 40
    assert DatasetRecord.objects.for_lab(lab).filter(project=ageing, contains_participant_data=True)
    assert Attachment.objects.for_lab(lab).filter(contains_participant_data=True).exists()
    assert not Participant.objects.for_lab(lab).exclude(project=ageing).exists()
    assert Project.objects.for_lab(lab).count() == 9


def test_nothing_leaks_to_another_lab():
    ctx = people.build("x")
    other = create_lab(user=ctx.people["pi"], name="Other Lab (FAKE)")
    research.seed(ctx)
    for model in (
        Task,
        ChatMessage,
        LabChatMessage,
        Document,
        Attachment,
        Paper,
        Participant,
        Analysis,
    ):
        assert not model.objects.for_lab(other).exists(), model
