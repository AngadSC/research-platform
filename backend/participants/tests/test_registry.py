import pytest

from audit.models import AuditAction, AuditEvent
from labs.models import LabRole
from participants.models import Component, Participant, ParticipantEvent
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


def cell_url(w, participant, component):
    return f"{w.base}/participants/{participant['id']}/cells/{component['id']}/"


def test_create_edit_archive_a_participant(w):
    (p,) = w.add("P-017", group="Punjabi")
    assert p["code"] == "P-017" and p["group"] == "Punjabi"
    r = w.client().patch(f"{w.base}/participants/{p['id']}/", {"cohort": "Fall"}, "json")
    assert r.status_code == 200 and r.json()["cohort"] == "Fall"
    assert w.client().post(f"{w.base}/participants/{p['id']}/archive/").status_code == 200
    assert w.client().get(f"{w.base}/participants/").json() == []
    archived = w.client().get(f"{w.base}/participants/?archived=1").json()
    assert [x["code"] for x in archived] == ["P-017"]
    w.client().post(f"{w.base}/participants/{p['id']}/restore/")
    assert Participant.objects.for_lab(w.lab).get().archived_at is None
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {
        AuditAction.PARTICIPANT_CREATED,
        AuditAction.PARTICIPANT_UPDATED,
        AuditAction.PARTICIPANT_ARCHIVED,
        AuditAction.PARTICIPANT_RESTORED,
    } <= actions


def test_codes_are_unique_per_project_and_a_repeat_is_a_conflict(w):
    w.add("P-001")
    r = w.client().post(f"{w.base}/participants/", {"codes": ["P-001", "P-002"]}, "json")
    assert r.status_code == 409
    assert Participant.objects.for_lab(w.lab).count() == 1  # nothing half-added
    dup = w.client().post(f"{w.base}/participants/", {"codes": ["P-005", "P-005"]}, "json")
    assert dup.status_code == 400
    other = f"/api/labs/{w.lab.pk}/projects/{w.other.pk}/participants/"
    assert w.client().post(other, {"codes": ["P-001"]}, "json").status_code == 201


@pytest.mark.parametrize(
    "bad",
    ["Jane Doe", "jane", "jane@example.com", "416-555-0199", "2015-03-04", "P 017", "<b>1</b>"],
)
def test_a_name_like_code_is_refused_and_not_logged(w, bad):
    r = w.client().post(f"{w.base}/participants/", {"codes": [bad]}, "json")
    assert r.status_code == 400
    assert bad not in r.content.decode()
    assert not Participant.objects.for_lab(w.lab).exists()
    event = AuditEvent.objects.get(action=AuditAction.PARTICIPANT_IDENTIFIER_BLOCKED)
    assert bad not in str(event.metadata) and event.metadata == {"fields": ["code"]}


@pytest.mark.parametrize(
    "text",
    [
        "call 604 555 0123",
        "email me@example.com",
        "born 2014-05-06",
        "dob 5/6/2014",
        "on May 6, 2014",
    ],
)
def test_free_text_with_an_identifier_is_refused_everywhere(w, text):
    (p,) = w.add("P-001")
    comp = w.column()
    cases = [
        ("post", f"{w.base}/participants/", {"codes": ["P-002"], "group": text}),
        ("patch", f"{w.base}/participants/{p['id']}/", {"notes": text}),
        ("patch", f"{w.base}/participants/{p['id']}/", {"cohort": text}),
        ("post", f"{w.base}/participant-components/", {"name": text}),
        ("patch", cell_url(w, p, comp), {"note": text}),
        ("post", f"/api/labs/{w.lab.pk}/participant-reasons/", {"label": text, "kind": "missing"}),
    ]
    for verb, url, body in cases:
        r = getattr(w.client(), verb)(url, body, "json")
        assert r.status_code == 400, (url, r.content)
        assert text not in r.content.decode()
    for e in AuditEvent.objects.filter(action=AuditAction.PARTICIPANT_IDENTIFIER_BLOCKED):
        assert text not in str(e.metadata)


def test_the_file_link_title_is_checked_too(w):
    (p,) = w.add("P-001")
    comp = w.column()
    cell = w.client().patch(cell_url(w, p, comp), {"status": "in_progress"}, "json").json()
    r = w.client().post(
        f"{w.base}/participant-cells/{cell['id']}/files/",
        {
            "url": "https://docs.google.com/document/d/abcdefghij12345/edit",
            "title": "jane@example.com",
        },
        "json",
    )
    assert r.status_code == 400


def test_there_is_no_field_for_a_name_or_contact_detail():
    from participants.models import Participant

    names = {f.name for f in Participant._meta.get_fields()}
    forbidden = {"name", "first_name", "last_name", "email", "phone", "address", "birthdate", "dob"}
    assert not names & forbidden


def test_missing_needs_a_reason_that_fits(w):
    (p,) = w.add("P-001")
    comp = w.column()
    url = cell_url(w, p, comp)
    r = w.client().patch(url, {"status": "missing"}, "json")
    assert r.status_code == 400 and "reason" in r.json()
    wrong = w.reason("excluded", "Withdrew")
    assert w.client().patch(url, {"status": "missing", "reason": wrong}, "json").status_code == 400
    ok = w.client().patch(url, {"status": "missing", "reason": w.reason()}, "json")
    assert ok.status_code == 200 and ok.json()["status"] == "missing"
    done = w.client().patch(url, {"status": "complete"}, "json").json()
    assert done["reason"] is None  # leaving Missing clears the explanation
    assert (
        w.client().patch(url, {"status": "complete", "reason": w.reason()}, "json").status_code
        == 400
    )


def test_a_link_suggests_in_progress_but_never_changes_status(w):
    (p,) = w.add("P-001")
    comp = w.column()
    cell = w.client().patch(cell_url(w, p, comp), {"due_date": "2026-12-01"}, "json").json()
    assert cell["status"] == "not_started" and cell["suggested_status"] is None
    r = w.client().post(
        f"{w.base}/participant-cells/{cell['id']}/files/",
        {"url": "https://docs.google.com/document/d/abcdefghij12345/edit", "role": "transcript"},
        "json",
    )
    assert r.status_code == 201
    assert r.json()["provider"] == "google_drive"
    cells = w.client().get(f"{w.base}/participant-cells/").json()
    assert cells[0]["status"] == "not_started"
    assert cells[0]["suggested_status"] == "in_progress"
    assert len(cells[0]["files"]) == 1


def test_only_web_addresses_can_be_linked(w):
    (p,) = w.add("P-001")
    cell = w.client().patch(cell_url(w, p, w.column()), {"status": "in_progress"}, "json").json()
    for url in ("javascript:alert(1)", "file:///etc/passwd", "ftp://example.com/x"):
        r = w.client().post(f"{w.base}/participant-cells/{cell['id']}/files/", {"url": url}, "json")
        assert r.status_code == 400, url


def test_status_changes_are_audited_without_content(w):
    (p,) = w.add("P-001")
    comp = w.column()
    w.client().patch(cell_url(w, p, comp), {"status": "in_progress", "note": "check tone"}, "json")
    event = AuditEvent.objects.get(action=AuditAction.PARTICIPANT_CELL_CHANGED)
    assert event.metadata["to"] == "in_progress" and "check tone" not in str(event.metadata)
    history = ParticipantEvent.objects.for_lab(w.lab).filter(participant_id=p["id"])
    assert history.filter(action="status", to_value="in_progress").exists()
    r = w.client().get(f"{w.base}/participants/{p['id']}/events/")
    assert r.status_code == 200 and r.json()


def test_the_owner_must_be_able_to_see_the_project(w):
    (p,) = w.add("P-001")
    comp = w.column()
    outsider = w.make_user()
    r = w.client().patch(cell_url(w, p, comp), {"owner": str(outsider.pk)}, "json")
    assert r.status_code == 400
    insider = w.member(ProjectRole.CONTRIBUTOR)
    r = w.client().patch(cell_url(w, p, comp), {"owner": str(insider.pk)}, "json")
    assert r.status_code == 200 and r.json()["owner"] == str(insider.pk)


def test_deleting_a_column_reports_the_cells_it_removed(w):
    a, b = w.add("P-001", "P-002")
    comp = w.column()
    for p in (a, b):
        w.client().patch(cell_url(w, p, comp), {"status": "in_progress"}, "json")
    r = w.client().delete(f"{w.base}/participant-components/{comp['id']}/")
    assert r.status_code == 200 and r.json() == {"cells_removed": 2}
    assert AuditEvent.objects.get(action=AuditAction.PARTICIPANT_COMPONENT_DELETED).metadata == {
        "cells": 2
    }


def test_roles(w):
    viewer = w.member(ProjectRole.VIEWER)
    contributor = w.member(ProjectRole.CONTRIBUTOR)
    (p,) = w.add("P-001")
    comp = w.column()
    v, c = w.client(viewer), w.client(contributor)
    assert v.get(f"{w.base}/participants/").status_code == 200
    assert v.post(f"{w.base}/participants/", {"codes": ["P-009"]}, "json").status_code == 403
    assert v.patch(cell_url(w, p, comp), {"status": "in_progress"}, "json").status_code == 403
    assert c.patch(cell_url(w, p, comp), {"status": "in_progress"}, "json").status_code == 200
    assert c.post(f"{w.base}/participant-components/", {"name": "X"}, "json").status_code == 403
    assert c.delete(f"{w.base}/participant-components/{comp['id']}/").status_code == 403
    assert (
        c.post(
            f"/api/labs/{w.lab.pk}/participant-reasons/", {"label": "x1", "kind": "missing"}, "json"
        ).status_code
        == 403
    )


def test_another_lab_and_another_project_cannot_reach_it(w, make_project):
    (p,) = w.add("P-001")
    comp = w.column()
    outsider = w.client(w.pi_b)
    assert outsider.get(f"{w.base}/participants/").status_code == 404
    assert outsider.get(f"{w.base}/participant-cells/").status_code == 404
    stranger = w.make_user()  # in the lab but not on the project
    w.join(stranger, w.lab, LabRole.MEMBER)
    assert w.client(stranger).get(f"{w.base}/participants/").status_code == 404
    # a participant id from another project in the same lab is not found under this one
    other = f"/api/labs/{w.lab.pk}/projects/{w.other.pk}"
    assert w.client().get(f"{other}/participants/{p['id']}/").status_code == 404
    assert (
        w.client()
        .patch(f"{other}/participants/{p['id']}/cells/{comp['id']}/", {}, "json")
        .status_code
        == 404
    )


def test_reasons_are_seeded_and_a_lead_can_add_one(w):
    r = w.client().get(f"/api/labs/{w.lab.pk}/participant-reasons/")
    labels = {x["label"] for x in r.json()}
    assert {
        "Did not attend",
        "Recording failure",
        "Translator pending",
        "Consent not on file",
    } <= labels
    made = w.client().post(
        f"/api/labs/{w.lab.pk}/participant-reasons/",
        {"label": "Interpreter unavailable", "kind": "missing"},
        "json",
    )
    assert made.status_code == 201
    dup = w.client().post(
        f"/api/labs/{w.lab.pk}/participant-reasons/",
        {"label": "Interpreter unavailable", "kind": "missing"},
        "json",
    )
    assert dup.status_code == 400


def test_a_new_study_of_people_starts_with_a_consent_column_contributors_fill(w):
    from projects.services import create_project

    people = create_project(lab=w.lab, user=w.pi, data={"name": "Consent (FAKE)"})
    mice = create_project(
        lab=w.lab, user=w.pi, data={"name": "Mice (FAKE)", "study_types": ["animal"]}
    )
    assert list(Component.objects.for_lab(w.lab).filter(project=mice)) == []
    (consent,) = Component.objects.for_lab(w.lab).filter(project=people)
    assert (consent.name, consent.category) == ("Consent form", "consent")
    # a contributor (not a lead) records consent, and it shows in the participant's history
    contributor = w.make_user()
    w.join(contributor, w.lab, LabRole.MEMBER)
    ProjectMembership.objects.create(
        lab=w.lab, project=people, user=contributor, role=ProjectRole.CONTRIBUTOR
    )
    base = f"/api/labs/{w.lab.pk}/projects/{people.pk}"
    c = w.client(contributor)
    (p,) = c.post(f"{base}/participants/", {"codes": ["P101"]}, "json").json()
    url = f"{base}/participants/{p['id']}/cells/{consent.pk}/"
    r = c.patch(url, {"status": "complete"}, "json")
    assert r.status_code == 200 and r.json()["status"] == "complete"
    assert (
        ParticipantEvent.objects.for_lab(w.lab)
        .filter(participant_id=p["id"], component=consent, to_value="complete")
        .exists()
    )


def test_existing_studies_with_participants_but_no_columns_get_the_consent_column(w):
    from importlib import import_module

    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    w.column()  # P1's lead set columns up already: left alone
    mice = w.other.__class__.objects.create(
        lab=w.lab, name="Mice (FAKE)", created_by=w.pi, study_types=["animal"]
    )
    # older projects all default to a study of people: only ones with participants get the column
    untracked = w.other.__class__.objects.create(
        lab=w.lab, name="Survey (FAKE)", created_by=w.pi, study_types=["human"]
    )
    Participant.objects.create(lab=w.lab, project=w.other, code="P900", created_by=w.pi)
    apps = MigrationLoader(connection).project_state().apps
    import_module("participants.migrations.0005_default_consent_column").add_consent_column(
        apps, None
    )
    names = lambda project: list(  # noqa: E731
        Component.objects.for_lab(w.lab).filter(project=project).values_list("name", flat=True)
    )
    assert names(w.project) == ["Transcript"]
    assert names(w.other) == ["Consent form"]
    assert names(mice) == []
    assert names(untracked) == []
