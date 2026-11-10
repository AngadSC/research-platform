"""Project page batch: Workflow progress, External records, adding a full set of results."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditEvent
from documents.models import Attachment
from ethics.models import EthicsApproval
from provenance.models import ExternalOutput, ManuscriptLink, Result
from provenance.tests.test_provenance import World

pytestmark = pytest.mark.django_db


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    return World(make_lab, make_user, make_project, join)


def progress_url(w):
    return reverse(
        "provenance:workflow-progress", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk}
    )


def set_url(w):
    return reverse("provenance:result-set", kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk})


def next_stage(w):
    return w.client().get(progress_url(w)).json()["next"]


def attachment(w, project):
    return Attachment.objects.create(
        lab=w.lab,
        project=project,
        storage_key=f"k/{project.pk}",
        original_filename="poster.pdf",
        content_type="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
        uploaded_by=w.pi,
        notice_acknowledged_at="2030-01-01T00:00:00Z",
    )


def analysis(w):
    return w.make(
        "analysis-list", {"title": "A", "code_repo_url": "https://g.io/r", "code_commit": "abc1234"}
    )


def test_progress_walks_the_stages_in_order(w):
    assert next_stage(w) == "funding"

    # Applying for money is not having it.
    funding = w.make("funding-list", {"funder": "NSERC", "status": "applied"})
    assert next_stage(w) == "funding"
    w.client().patch(
        w.url("funding-detail", fundingrecord_id=funding), {"status": "awarded"}, format="json"
    )
    assert next_stage(w) == "ethics"

    # An expired approval does not count; a valid one does.
    today = timezone.localdate()
    approval = EthicsApproval.objects.create(
        lab=w.lab,
        approval_number="E-1",
        board="REB",
        title="T",
        approval_date=today - timedelta(days=30),
        expiry_date=today - timedelta(days=1),
        created_by=w.pi,
    )
    approval.projects.add(w.project)
    assert next_stage(w) == "ethics"
    approval.expiry_date = today + timedelta(days=30)
    approval.save()
    assert next_stage(w) == "participants"

    # The enrolment target has to be reached.
    w.client().patch(
        reverse(
            "provenance:recruitment-plan",
            kwargs={"lab_id": w.lab.pk, "project_id": w.project.pk},
        ),
        {"target_enrolment": 5},
        format="json",
    )
    body = {"entry_date": "2030-01-01", "status": "enrolled", "count": 4}
    w.make("recruitment-list", body)
    assert next_stage(w) == "participants"
    w.make("recruitment-list", {**body, "count": 1})
    assert next_stage(w) == "data"

    w.make("dataset-list", {"name": "D", "version_label": "v1"})
    assert next_stage(w) == "analysis"

    # An analysis with no result yet is not finished.
    a = analysis(w)
    assert next_stage(w) == "analysis"
    result = w.make("result-list", {"title": "R", "analysis": a})
    assert next_stage(w) == "manuscript"

    # A draft does not count; a submitted manuscript does.
    m = w.make("manuscript-list", {"title": "M", "url": "https://o.io/p", "results": [result]})
    assert next_stage(w) == "manuscript"
    ManuscriptLink.objects.for_lab(w.lab).filter(pk=m).update(status="submitted")
    assert next_stage(w) == "review"

    # Every review item must be approved, and there must be at least one.
    first = w.make("review-list", {"title": "One", "status": "approved"})
    w.make("review-list", {"title": "Two", "status": "requested"})
    assert first and next_stage(w) == "review"
    for row in w.client().get(w.url("review-list")).json():
        w.client().patch(
            w.url("review-detail", reviewitem_id=row["id"]), {"status": "approved"}, format="json"
        )
    assert next_stage(w) is None


def test_a_stage_can_be_marked_done_and_undone(w):
    client = w.client()
    resp = client.patch(progress_url(w), {"stage": "funding", "done": True}, format="json")
    assert resp.status_code == 200
    assert resp.json()["next"] == "ethics"
    assert resp.json()["stages"][0] == {"key": "funding", "done": True, "marked": True}
    assert AuditEvent.objects.filter(action="funding.updated", target_id=w.project.pk).exists()

    resp = client.patch(progress_url(w), {"stage": "funding", "done": False}, format="json")
    assert resp.json()["next"] == "funding"
    assert (
        client.patch(progress_url(w), {"stage": "nope", "done": True}, format="json").status_code
        == 400
    )


def external_body(**extra):
    return {"title": "Poster", "type": "poster", "date": "2030-05-01", **extra}


def test_external_records_are_audited_and_keep_the_file_in_the_project(w):
    mine = attachment(w, w.project)
    made = w.post("external-list", external_body(attachment=str(mine.pk), place="Halifax"))
    assert made.status_code == 201
    assert made.json()["attachment"]["id"] == str(mine.pk)
    item = w.url("external-detail", externaloutput_id=made.json()["id"])

    assert w.client().patch(item, {"place": "Toronto"}, format="json").json()["place"] == "Toronto"
    assert w.client().delete(item).status_code == 204
    assert list(
        AuditEvent.objects.filter(action__startswith="external_output.")
        .order_by("occurred_at", "id")
        .values_list("action", flat=True)
    ) == ["external_output.created", "external_output.updated", "external_output.deleted"]

    # A file from another project cannot be attached.
    theirs = attachment(w, w.other)
    assert w.post("external-list", external_body(attachment=str(theirs.pk))).status_code == 400


def test_external_stops_offering_a_deleted_file(w):
    mine = attachment(w, w.project)
    pk = w.make("external-list", external_body(attachment=str(mine.pk)))
    Attachment.objects.for_lab(w.lab).filter(pk=mine.pk).update(deleted_at=timezone.now())
    item = w.url("external-detail", externaloutput_id=pk)
    assert w.client().get(item).json()["attachment"] is None


def test_external_rejects_a_script_link_and_a_bad_type(w):
    assert w.post("external-list", external_body(url="javascript:alert(1)")).status_code == 400
    assert w.post("external-list", external_body(type="blog")).status_code == 400


def test_external_from_another_lab_is_a_404(w):
    pk = w.make("external-list", external_body())
    url = reverse(
        "provenance:external-detail", kwargs={"lab_id": w.lab_b.pk, "externaloutput_id": pk}
    )
    assert w.client(w.pi_b).get(url).status_code == 404
    assert ExternalOutput.objects.for_lab(w.lab).filter(pk=pk).exists()


def test_result_set_saves_every_item_and_audits_each(w):
    a = analysis(w)
    fig = attachment(w, w.project)
    resp = w.client().post(
        set_url(w),
        {
            "analysis": a,
            "items": [{"title": "Figure 1", "attachments": [str(fig.pk)]}, {"title": "Figure 2"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert sorted(r["title"] for r in resp.json()) == ["Figure 1", "Figure 2"]
    assert {r["analysis"]["id"] for r in resp.json()} == {a}
    assert AuditEvent.objects.filter(action="result.created").count() == 2


def test_result_set_is_all_or_nothing(w):
    a = analysis(w)
    theirs = attachment(w, w.other)
    resp = w.client().post(
        set_url(w),
        {
            "analysis": a,
            "items": [{"title": "Good"}, {"title": "Bad", "attachments": [str(theirs.pk)]}],
        },
        format="json",
    )
    assert resp.status_code == 400
    assert not Result.objects.for_lab(w.lab).exists()
    assert not AuditEvent.objects.filter(action="result.created").exists()


def test_result_set_needs_at_least_one_item(w):
    resp = w.client().post(set_url(w), {"analysis": analysis(w), "items": []}, format="json")
    assert resp.status_code == 400
