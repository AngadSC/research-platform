"""VISION A3: AI tools (in-app assistant and MCP server alike) never see an item marked "Contains
participant data". Lists and search skip it; asking for it by id gets a plain refusal. Every
flagged name carries PARTICIPANT so one string check covers every tool's output."""

import json

import pytest

from assistant import privacy, tools
from documents import services as document_services
from documents.models import Folder
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db
MARK = "PARTICIPANT"
BLOCKS = [{"type": "paragraph", "content": [{"type": "text", "text": "Text PARTICIPANT"}]}]


@pytest.fixture
def flagged(world):
    """In P1: a flagged document linked to the open task; an unflagged document moved into a
    flagged folder; a flagged dataset used by the open analysis and set as the open dataset's
    previous version. All created by the pi, so their handover list would name them."""
    lab, p1, pi = world.lab_a, world.p1, world.u.pi
    own = document_services.create_document(
        project=p1, user=pi, title=f"Doc {MARK} own", content=BLOCKS, contains_participant_data=True
    )
    world.a1.task.documents.add(own)
    box = Folder.objects.create(
        lab=lab, project=p1, name=f"Folder {MARK}", created_by=pi, contains_participant_data=True
    )
    inside = document_services.create_document(
        project=p1, user=pi, title=f"Doc {MARK} in folder", content=BLOCKS
    )
    document_services.move_to_folder(inside, box)  # its own box stays clear
    ds = DatasetRecord.objects.create(
        lab=lab,
        project=p1,
        name=f"Data {MARK}",
        version_label="v0",
        controlled_by=pi,
        created_by=pi,
        contains_participant_data=True,
    )
    world.a1.an.datasets.add(ds)
    world.a1.ds.previous_version = ds
    world.a1.ds.save()
    return {"own": own, "inside": inside, "ds": ds}


def run(c, name, **args):
    return json.dumps(tools.call(c, name, args))


def test_every_read_tool_leaves_flagged_items_out(world, ctx, flagged):
    a = str(world.lab_a.pk)
    c = ctx(world.u.pi, world.lab_a)
    calls = [
        ("list_projects", {"lab_id": a}),
        ("project_overview", {"lab_id": a, "project_id": str(world.p1.pk)}),
        ("search", {"lab_id": a, "query": MARK}),
        ("search", {"lab_id": a, "query": "Doc"}),
        ("search", {"lab_id": a, "query": "Data"}),
        ("list_tasks", {"lab_id": a}),
        ("get_task", {"lab_id": a, "task_id": str(world.a1.task.pk)}),
        ("get_document", {"lab_id": a, "document_id": str(world.a1.doc.pk)}),
        ("handover_report", {"lab_id": a, "person": "me"}),
        ("handover_report", {"lab_id": a, "person": "me", "project_id": str(world.p1.pk)}),
    ] + [
        ("lineage_trace", {"lab_id": a, "item_type": kind, "item_id": str(obj.pk)})
        for kind, obj in (
            ("manuscript", world.a1.ms),
            ("result", world.a1.res),
            ("analysis", world.a1.an),
            ("dataset", world.a1.ds),
        )
    ]
    for name, args in calls:
        out = run(c, name, **args)
        assert MARK not in out, (name, out)
    assert set(tools.TOOLS) >= {name for name, _ in calls}

    overview = json.loads(run(c, "project_overview", lab_id=a, project_id=str(world.p1.pk)))
    assert overview["counts"]["documents"] == 1 and overview["counts"]["datasets"] == 1
    # the unflagged items still come back, so the tools are not simply empty
    assert "Doc open" in run(c, "search", lab_id=a, query="Doc")
    assert "Data open" in run(c, "search", lab_id=a, query="Data")


@pytest.mark.parametrize(
    ("name", "key", "args"),
    [
        ("get_document", "own", {}),
        ("get_document", "inside", {}),
        ("lineage_trace", "ds", {"item_type": "dataset"}),
    ],
)
def test_asking_for_a_flagged_item_by_id_is_refused(world, ctx, flagged, name, key, args):
    c = ctx(world.u.pi, world.lab_a)
    id_arg = "document_id" if name == "get_document" else "item_id"
    with pytest.raises(tools.ToolError) as exc:
        tools.call(c, name, {"lab_id": str(world.lab_a.pk), id_arg: str(flagged[key].pk), **args})
    assert str(exc.value) == privacy.REFUSAL


def test_privacy_helpers(world, flagged):
    from documents.models import Document

    docs = privacy.ai_visible(Document.objects.for_lab(world.lab_a).filter(project=world.p1))
    assert list(docs) == [world.a1.doc]  # a document with no folder is still visible
    assert privacy.is_flagged(flagged["inside"]) and not privacy.is_flagged(world.a1.doc)
    assert not privacy.is_flagged(world.p1)  # a kind that cannot carry the flag
    sub = Folder.objects.create(
        lab=world.lab_a,
        project=world.p1,
        name="Sub",
        created_by=world.u.pi,
        parent=flagged["inside"].folder,
    )
    assert privacy.is_flagged(sub)
    assert list(privacy.ai_visible(Folder.objects.for_lab(world.lab_a))) == []
