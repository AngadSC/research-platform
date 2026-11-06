import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.management.commands.seed_pilot import FAKE_COMMIT, LAB_NAME
from labs.models import Lab
from projects.models import Project, ProjectMembership, ProjectRole
from provenance.models import ManuscriptLink

pytestmark = pytest.mark.django_db


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


def test_ethics_approval_expires_in_25_days_and_viewer_sees_the_pilot_project(debug_on):
    import datetime

    from django.utils import timezone

    from documents.models import Document
    from ethics.models import EthicsApproval

    call_command("seed_pilot")
    lab = Lab.objects.get(name=LAB_NAME)
    project = Project.objects.for_lab(lab).get(name="Pilot Attention Study (FAKE)")
    approval = EthicsApproval.objects.for_lab(lab).get(approval_number="FAKE-IRB-2026-001")
    assert approval.expiry_date == timezone.localdate() + datetime.timedelta(days=25)
    assert list(approval.projects.all()) == [project]
    viewer = ProjectMembership.objects.for_lab(lab).get(user__email="viewer@example.test")
    assert (viewer.project, viewer.role) == (project, ProjectRole.VIEWER)
    today = timezone.localdate()
    archived = Project.objects.for_lab(lab).get(name="Archived Survey (FAKE)")
    assert archived.retain_until < today
    overdue_docs = Document.objects.for_lab(lab).filter(project=project, retain_until__lt=today)
    assert overdue_docs.count() == 1


def test_drive_seed_is_idempotent_fake_and_has_both_states(debug_on):
    from integrations.models import ConnectedAccount, ExternalLink

    call_command("seed_pilot")
    call_command("seed_pilot")
    lab = Lab.objects.get(name=LAB_NAME)
    accounts = ConnectedAccount.objects.for_lab(lab)
    assert sorted((a.provider, a.user.email) for a in accounts) == [
        ("github", "pi@example.test"),
        ("google_drive", "lead@example.test"),
    ]
    assert not any(a.access_token_ct or a.refresh_token_ct for a in accounts)
    links = ExternalLink.objects.for_lab(lab)
    assert sorted(link.provider for link in links) == [
        "github",
        "google_drive",
        "google_drive",
        "overleaf",
        "zenodo",
        "zotero",
    ]
    drive = links.filter(provider="google_drive")
    assert sorted(link.status for link in drive) == ["changed", "unavailable"]
    assert (
        links.get(provider="zotero").decision.references[0]["url"]
        == links.get(provider="zotero").url
    )
    assert all("example.invalid" in link.url for link in links)


def test_dmp_draft_is_seeded_once(debug_on):
    from provenance.models import DataManagementPlan

    call_command("seed_pilot")
    call_command("seed_pilot")
    plans = DataManagementPlan.objects.for_lab(Lab.objects.get(name=LAB_NAME))
    assert [p.status for p in plans] == ["draft"]
    assert plans[0].revisions.count() == 1
