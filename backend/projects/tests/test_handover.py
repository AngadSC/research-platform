"""Handover report (Phase 6), run against the seed scenario: the student is a contributor on the
pilot project, has open tasks, ran the analysis, and is the only lead of the archived project."""

import datetime

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.management.commands.seed_pilot import LAB_NAME
from core.models import User
from ethics.models import EthicsApproval
from labs.models import Lab, LabMembership
from projects import handover
from projects.models import Project

PILOT = "Pilot Attention Study (FAKE)"
ARCHIVED = "Archived Survey (FAKE)"


@pytest.fixture
def seeded(settings):
    settings.DEBUG = True
    call_command("seed_pilot")
    return Lab.objects.get(name=LAB_NAME)


def _get(lab, who, target="student", project=None):
    """Request a handover as `who`; returns the response."""
    client = APIClient()
    client.force_login(User.objects.get(email=f"{who}@example.test"))
    target_user = User.objects.get(email=f"{target}@example.test")
    if project is None:
        m = LabMembership.objects.for_lab(lab).get(user=target_user)
        url = reverse("projects:member-handover", args=[lab.pk, m.pk])
        return client.get(url)
    url = reverse("projects:project-handover", args=[lab.pk, project.pk])
    return client.get(url, {"user": str(target_user.pk)})


def _titles(body, key):
    (section,) = [s for s in body["sections"] if s["key"] == key]
    return [i["title"] for i in section["items"]]


@pytest.mark.django_db
def test_student_report_lists_tasks_analysis_result_and_archived_project(seeded):
    res = _get(seeded, "pi")
    assert res.status_code == 200
    body = res.json()
    assert body["person"]["email"] == "student@example.test"
    assert sorted(_titles(body, "open_tasks")) == [
        "Clean RT export (FAKE)",
        "Fit primary RT model (FAKE)",
        "Recruit 12 participants (FAKE)",
    ]
    assert "Primary RT model (FAKE)" in _titles(body, "analyses")
    assert _titles(body, "results")  # results of the student's analysis
    assert ARCHIVED in _titles(body, "projects_led")
    orphans = {i["title"]: i for i in body["no_other_owner"]}
    assert ARCHIVED in orphans
    assert orphans[ARCHIVED]["kind"] == "project"
    assert orphans[ARCHIVED]["project"]["name"] == ARCHIVED
    assert orphans[ARCHIVED]["href"].endswith("/overview")
    assert orphans[ARCHIVED]["reason"]
    assert "Survey items (FAKE)" in orphans  # a document they created


@pytest.mark.django_db
def test_project_handover_is_limited_to_that_project(seeded):
    pilot = Project.objects.for_lab(seeded).get(name=PILOT)
    res = _get(seeded, "lead", project=pilot)
    assert res.status_code == 200
    body = res.json()
    assert body["project"]["name"] == PILOT
    assert "Primary RT model (FAKE)" in _titles(body, "analyses")
    assert _titles(body, "projects_led") == []  # the student is a contributor here
    names = {i["project"]["name"] for s in body["sections"] for i in s["items"] if i["project"]}
    assert names == {PILOT}
    assert ARCHIVED not in str(body)


@pytest.mark.django_db
def test_member_reads_own_report_but_not_someone_elses(seeded):
    assert _get(seeded, "student", target="student").status_code == 200
    assert _get(seeded, "student", target="lead").status_code == 403
    assert _get(seeded, "viewer", target="viewer").status_code == 200  # own report, any role
    assert _get(seeded, "viewer", target="student").status_code == 403


@pytest.mark.django_db
def test_lab_admin_can_generate_any_members_report(seeded):
    for target in ("student", "lead", "pi"):
        assert _get(seeded, "admin", target=target).status_code == 200


@pytest.mark.django_db
def test_project_handover_needs_manage_project_members(seeded):
    pilot = Project.objects.for_lab(seeded).get(name=PILOT)
    assert _get(seeded, "student", project=pilot).status_code == 403
    assert _get(seeded, "viewer", project=pilot).status_code == 403
    assert _get(seeded, "lead", project=pilot).status_code == 200


@pytest.mark.django_db
def test_requester_gets_no_items_from_a_project_they_cannot_see(seeded):
    lead = User.objects.get(email="lead@example.test")  # not on the archived project
    student = LabMembership.objects.for_lab(seeded).get(user__email="student@example.test")
    report = handover.build_report(requester=lead, lab=seeded, membership=student)
    everything = str(report)
    assert ARCHIVED not in everything and "Survey items" not in everything
    assert {i["project"]["name"] for i in report["no_other_owner"]} <= {PILOT}
    assert "Primary RT model (FAKE)" in str(report["sections"])  # the pilot project is visible


@pytest.mark.django_db
def test_restricted_approval_is_hidden_from_requesters_who_cannot_see_its_projects(seeded):
    archived = Project.objects.for_lab(seeded).get(name=ARCHIVED)
    student = User.objects.get(email="student@example.test")
    approval = EthicsApproval.objects.create(
        lab=seeded,
        approval_number="R-1",
        board="Board",
        title="Restricted (FAKE)",
        approval_date=datetime.date(2030, 1, 1),
        expiry_date=datetime.date(2031, 1, 1),
        created_by=student,
        restricted=True,
    )
    approval.projects.add(archived)
    membership = LabMembership.objects.for_lab(seeded).get(user=student)
    lead = User.objects.get(email="lead@example.test")  # member, not on the archived project
    pi = User.objects.get(email="pi@example.test")
    hidden = handover.build_report(requester=lead, lab=seeded, membership=membership)
    shown = handover.build_report(requester=pi, lab=seeded, membership=membership)
    assert "Restricted (FAKE)" not in str(hidden)
    assert "R-1: Restricted (FAKE)" in str(shown["sections"])


@pytest.mark.django_db
def test_generating_is_audited_and_query_count_is_constant(seeded, django_assert_max_num_queries):
    client = APIClient()
    client.force_login(User.objects.get(email="pi@example.test"))
    student = LabMembership.objects.for_lab(seeded).get(user__email="student@example.test")
    url = reverse("projects:member-handover", args=[seeded.pk, student.pk])
    with django_assert_max_num_queries(40):
        assert client.get(url).status_code == 200
    event = AuditEvent.objects.get(action=AuditAction.HANDOVER_GENERATED)
    assert event.metadata["person"] == str(student.user_id)
    assert event.metadata["counts"]["no_other_owner"] >= 2

    # More data must not add queries.
    from projects import services

    pilot = Project.objects.for_lab(seeded).get(name=PILOT)
    for i in range(5):
        services.create_task(
            project=pilot,
            by=student.user,
            data={"title": f"Extra {i}", "assignee": student.user_id},
        )
    with django_assert_max_num_queries(40):
        assert client.get(url).status_code == 200
