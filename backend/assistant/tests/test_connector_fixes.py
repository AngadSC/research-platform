"""Connector fixes from the 12 Nov 2026 review: files in search, honest descriptions, counts of
what was left out (never titles), the document-id hint, friendly file kinds."""

import datetime
import json
import uuid

import pytest

from assistant import mcp, privacy, tools
from documents import services as document_services
from documents.models import Attachment
from papers import citation
from papers import services as paper_services
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db
MARK = "PARTICIPANT"


def call(c, name, **args):
    return tools.call(c, name, args)


def refused(c, name, **args):
    with pytest.raises(tools.ToolError) as exc:
        tools.call(c, name, args)
    return str(exc.value)


def attach(world, project, name, **kw):
    kw.setdefault("content_type", "text/csv")
    return Attachment.objects.create(
        lab=project.lab,
        project=project,
        storage_key=f"k/{uuid.uuid4()}",
        original_filename=name,
        size_bytes=1,
        sha256="",
        uploaded_by=world.u.pi,
        **kw,
    )


@pytest.fixture
def hidden(world):
    """In P1, made by the pi: one flagged document, one flagged dataset, one flagged file."""
    lab, p1, pi = world.lab_a, world.p1, world.u.pi
    doc = document_services.create_document(
        project=p1, user=pi, title=f"Doc {MARK}", content=[], contains_participant_data=True
    )
    ds = DatasetRecord.objects.create(
        lab=lab,
        project=p1,
        name=f"Data {MARK}",
        version_label="v1",
        controlled_by=pi,
        created_by=pi,
        contains_participant_data=True,
    )
    f = attach(world, p1, f"Tester doc {MARK}.csv", contains_participant_data=True)
    return {"doc": doc, "ds": ds, "file": f}


def test_search_finds_files_by_name_but_never_identifying_ones(world, ctx, hidden):
    attach(world, world.p1, "Tester doc.docx")
    attach(world, world.p1, "Tester doc", drive_file_id="d1", content_type="text/plain")
    attach(world, world.p1, "Tester doc grant.pdf", pi_only=True)
    attach(world, world.p2, "Tester doc SECRET.pdf")
    a = str(world.lab_a.pk)
    out = call(ctx(world.u.contrib, world.lab_a), "search", lab_id=a, query="tester doc")
    assert sorted(h["title"] for h in out["results"]) == ["Tester doc", "Tester doc.docx"]
    assert all(h["type"] == "file" for h in out["results"])
    assert out["results"][0]["url"].endswith(f"/projects/{world.p1.pk}/documents")
    pi = json.dumps(call(ctx(world.u.pi, world.lab_a), "search", lab_id=a, query="tester doc"))
    assert "grant.pdf" in pi and "SECRET" in pi and MARK not in pi
    enum = tools.TOOLS["search"].params["types"]["items"]["enum"]
    assert "file" in enum and "meeting" not in enum
    pi = ctx(world.u.pi, world.lab_a)
    msg = refused(pi, "search", lab_id=a, query="x y", types=["meeting"])
    assert msg == "types has an invalid item."


def test_overview_and_handover_count_what_was_left_out_without_titles(world, ctx, hidden):
    a, c = str(world.lab_a.pk), ctx(world.u.pi, world.lab_a)
    overview = call(c, "project_overview", lab_id=a, project_id=str(world.p1.pk))
    assert overview["counts"]["documents"] == 1 and overview["counts"]["datasets"] == 1
    assert overview["hidden_identifying_items"] == 2
    assert "Open" in overview["hidden_note"]
    report = call(c, "handover_report", lab_id=a, person="me")
    assert report["hidden_identifying_items"] == 2
    assert MARK not in json.dumps(overview) + json.dumps(report)
    # nothing hidden: no extra keys
    p2 = call(c, "project_overview", lab_id=a, project_id=str(world.p2.pk))
    assert "hidden_identifying_items" not in p2


def test_read_file_hints_at_a_document_only_when_you_can_see_it(world, ctx):
    a = str(world.lab_a.pk)
    contrib = ctx(world.u.contrib, world.lab_a)
    msg = refused(contrib, "read_file", lab_id=a, file_id=str(world.a1.doc.pk))
    assert msg == "That id is a document; use get_document."
    # a document in a project they are not on reads like any unknown id
    msg = refused(contrib, "read_file", lab_id=a, file_id=str(world.a2.doc.pk))
    assert msg == refused(contrib, "read_file", lab_id=a, file_id=str(uuid.uuid4()))
    assert "document" not in msg


def test_refusal_uses_the_new_wording(world, ctx, hidden):
    a = str(world.lab_a.pk)
    msg = refused(
        ctx(world.u.pi, world.lab_a), "read_file", lab_id=a, file_id=str(hidden["file"].pk)
    )
    assert msg == privacy.REFUSAL
    assert msg == "This item is marked as identifying participants, so AI tools cannot open it."


def test_organisation_author_marker_is_not_shown_but_is_kept(world, ctx):
    paper = paper_services.create_paper(
        world.lab_a,
        user=world.u.pi,
        data={"title": "Atlas", "authors": ["Example Lab,", "Doe, Jane"], "year": 2030},
    )
    out = call(ctx(world.u.pi, world.lab_a), "get_paper", lab_id=str(world.lab_a.pk),
               paper_id=str(paper.pk))  # fmt: skip
    assert out["authors"] == ["Example Lab", "Doe, Jane"]
    paper.refresh_from_db()
    assert paper.authors[0] == "Example Lab,"
    assert "Example Lab" in citation.cite(paper, "apa")


def test_list_files_adds_a_friendly_kind(world, ctx):
    attach(world, world.p1, "Notes.docx", content_type="application/octet-stream")
    attach(world, world.p1, "Plan", drive_file_id="d2",
           content_type="application/vnd.google-apps.document")  # fmt: skip
    attach(world, world.p1, "rt.csv")
    attach(world, world.p1, "scan.tiff", content_type="image/tiff")
    out = call(ctx(world.u.pi, world.lab_a), "list_files", lab_id=str(world.lab_a.pk),
               project_id=str(world.p1.pk))  # fmt: skip
    kinds = {f["name"]: (f["kind"], f["type"]) for f in out["files"]}
    assert kinds["Notes.docx"] == ("Word", "application/octet-stream")
    assert kinds["Plan"][0] == "Google Docs"
    assert kinds["rt.csv"][0] == "CSV" and kinds["scan.tiff"][0] == "Image"


def test_instructions_name_only_the_write_tools_offered(world):
    text = mcp.instructions()  # the runner is off in tests
    assert "run_code" not in text
    for name in ("create_task", "get_file_link", "create_upload_link"):
        assert name in text
    assert "approves each link" not in tools.TOOLS["get_file_link"].description
    assert "finalise" not in tools.TOOLS["create_decision_draft"].description


def test_decision_draft_takes_the_persons_local_date(world, ctx):
    c = ctx(world.u.pi, world.lab_a, write=True)
    out = call(c, "create_decision_draft", lab_id=str(world.lab_a.pk),
               project_id=str(world.p1.pk), title="Use the mixed model",
               decided_on="2026-11-12")  # fmt: skip
    assert out["created"]["title"] == "Draft: Use the mixed model"
    assert out["created"]["decided_on"] == "2026-11-12"
    assert "decided_on must be a date" in refused(
        c, "create_decision_draft", lab_id=str(world.lab_a.pk), project_id=str(world.p1.pk),
        title="x", decided_on="12/11/2026",
    )  # fmt: skip
    assert datetime.date.fromisoformat(out["created"]["decided_on"])
