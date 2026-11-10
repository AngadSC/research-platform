"""The getting-started checklist (D234): it ticks from real data, one row at a time."""

import datetime

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from ethics.models import EthicsApproval
from integrations.models import AccountStatus, ConnectedAccount
from labs.models import Invite, LabRole
from projects.models import Project
from training.models import TrainingRequirement

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def drive_configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "fake", "client_secret": "fake"},
    }


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab("Lab")
    pi, viewer = make_user(), make_user()
    join(pi, lab, LabRole.PI)
    return lab, pi, viewer


def get(user, lab):
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(f"/api/labs/{lab.pk}/getting-started/")
    assert response.status_code == 200
    body = response.json()
    return body, {s["key"]: s["done"] for s in body["steps"]}


def test_each_step_ticks_from_its_own_data(world):
    lab, pi, _ = world
    assert get(pi, lab)[1] == {
        "members": False,
        "project": False,
        "ethics": False,
        "drive": False,
        "training": False,
    }

    Invite.objects.create(
        lab=lab,
        email="new@example.com",
        role=LabRole.MEMBER,
        token_hash="x" * 64,
        invited_by=pi,
        expires_at=timezone.now() + datetime.timedelta(days=7),
    )
    assert get(pi, lab)[1]["members"] is True

    project = Project.objects.create(lab=lab, name="P", created_by=pi)
    assert get(pi, lab)[1]["project"] is True

    approval = EthicsApproval.objects.create(
        lab=lab,
        approval_number="1",
        board="B",
        title="T",
        approval_date="2026-01-01",
        expiry_date="2030-01-01",
        created_by=pi,
    )
    assert get(pi, lab)[1]["ethics"] is False  # not linked to a project yet
    approval.projects.add(project)
    assert get(pi, lab)[1]["ethics"] is True

    ConnectedAccount.objects.create(
        lab=lab,
        user=pi,
        provider="google_drive",
        external_account_id="a",
        status=AccountStatus.ACTIVE,
        connected_at=timezone.now(),
    )
    assert get(pi, lab)[1]["drive"] is True

    TrainingRequirement.objects.create(lab=lab, name="Safety", category="other")
    assert all(get(pi, lab)[1].values())


def test_a_step_undoes_itself_when_the_data_goes(world):
    lab, pi, _ = world
    project = Project.objects.create(lab=lab, name="P", created_by=pi)
    assert get(pi, lab)[1]["project"] is True
    project.deleted_at = timezone.now()
    project.save()
    assert get(pi, lab)[1]["project"] is False


def test_can_act_follows_the_persons_role(world, join):
    lab, pi, viewer = world
    join(viewer, lab, LabRole.VIEWER)
    can_act = {s["key"]: s["can_act"] for s in get(viewer, lab)[0]["steps"]}
    assert can_act == {
        "members": False,
        "project": False,
        "ethics": False,
        "drive": True,
        "training": False,
    }
    assert all(s["can_act"] for s in get(pi, lab)[0]["steps"])


def test_drive_step_is_hidden_until_drive_is_set_up(world, settings):
    lab, pi, _ = world
    settings.INTEGRATION_CLIENTS = {}
    assert "drive" not in get(pi, lab)[1]


def test_dismiss_is_per_person_and_per_lab(world, join, make_lab):
    lab, pi, viewer = world
    join(viewer, lab, LabRole.VIEWER)
    other = make_lab("Other")
    join(pi, other, LabRole.PI)
    client = APIClient()
    client.force_authenticate(pi)
    url = f"/api/labs/{lab.pk}/getting-started/"
    assert client.post(url, {"dismissed": True}, format="json").json()["dismissed"] is True
    assert get(pi, lab)[0]["dismissed"] is True
    assert get(pi, other)[0]["dismissed"] is False
    assert get(viewer, lab)[0]["dismissed"] is False
    assert client.post(url, {"dismissed": False}, format="json").json()["dismissed"] is False
    assert get(pi, lab)[0]["dismissed"] is False
