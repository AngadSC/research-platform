"""Google verification acceptance for VISION A3: a Drive-linked file or folder marked "Contains
participant data" is refused before any Google call, by every route AI has to a file: the in-app
read_file tool, the MCP read_file tool and code execution (load_files_for_analysis). A file that is
not marked is read with the asking person's own Google token.

The in-app refusal of a directly marked Drive file already has a test
(test_drive_read.py::test_a_flagged_drive_file_is_refused_before_any_google_call); these add the
other ways a file counts as marked (a marked folder, a copy of a marked file) and the other two
routes. Every Google call goes through the patched HTTP layer; nothing leaves the process."""

import json

import pytest
from django.core.cache import cache

from assistant import privacy, tools
from assistant.models import AIProviderKey
from assistant.tests import test_code_exec as cx
from assistant.tests.fakes import CANARY_KEY, claude_message, patch_claude, text
from assistant.tests.test_drive_read import BASE, DOC, google, linked, meta, raw
from assistant.tests.test_mcp import pat, rpc
from documents.models import Folder
from integrations import http
from integrations.tests.fake import FakeTransport

pytestmark = pytest.mark.django_db

FILE_ID = "1AbC-dEf_9"


@pytest.fixture
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(http, "_session", fake)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(http, "_resolve", lambda host: ["93.184.216.34"])
    return fake


@pytest.fixture
def signed_in(world):
    """The contributor has connected Google here (so a read would go through), and has an AI key
    for the code route."""
    cache.clear()
    google(world.u.contrib, world.lab_a, "contrib-token")
    row = AIProviderKey(user=world.u.contrib, provider="anthropic")
    row.set_key(CANARY_KEY)
    row.save()


def marked_drive_file(world, shape):
    """A Drive-linked file AI must not open, marked in one of the ways that count."""
    if shape == "file":
        return linked(world, DOC, flag=True)
    if shape == "in_marked_folder":
        box = Folder.objects.create(
            lab=world.lab_a,
            project=world.p1,
            name="Participants",
            created_by=world.u.pi,
            contains_participant_data=True,
        )
        att = linked(world, DOC)
        att.folder = box
        att.save()
        return att
    original = linked(world, DOC, name="Original", flag=True, file_id="2OrIg")
    copy = linked(world, DOC, name="Copy")
    copy.copied_from = original
    copy.save()
    return copy


SHAPES = ["file", "in_marked_folder", "copy_of_marked_file"]


def mcp_read(world, att):
    token = pat(world.u.contrib, world.lab_a)
    args = {"lab_id": str(world.lab_a.pk), "file_id": str(att.pk)}
    resp = rpc(token, "tools/call", {"name": "read_file", "arguments": args})
    assert resp.status_code == 200, resp.content
    return resp.json()["result"]


def in_app_read(world, att):
    c = tools.Context(
        user=world.u.contrib, lab_ids=frozenset({str(world.lab_a.pk)}), can_write=False
    )
    return tools.call(c, "read_file", {"lab_id": str(world.lab_a.pk), "file_id": str(att.pk)})


# ------------------------------------------------ refused before any Google call


@pytest.mark.parametrize("shape", SHAPES)
def test_in_app_read_file_refuses_a_marked_drive_file_before_any_google_call(
    world, transport, signed_in, shape
):
    att = marked_drive_file(world, shape)
    with pytest.raises(tools.ToolError) as exc:
        in_app_read(world, att)
    assert str(exc.value) == privacy.REFUSAL
    assert transport.calls == []


@pytest.mark.parametrize("shape", SHAPES)
def test_mcp_read_file_refuses_a_marked_drive_file_before_any_google_call(
    world, transport, signed_in, shape
):
    att = marked_drive_file(world, shape)
    result = mcp_read(world, att)
    assert result["isError"] is True
    assert result["content"][0]["text"] == privacy.REFUSAL
    assert transport.calls == []


@pytest.mark.parametrize("shape", SHAPES)
def test_code_execution_refuses_a_marked_drive_file_before_any_google_call(
    world, transport, signed_in, monkeypatch, shape
):
    att = marked_drive_file(world, shape)
    fake = patch_claude(
        monkeypatch,
        claude_message([cx.load_call(world.lab_a, att)], stop="tool_use"),
        claude_message([text("I can't.")]),
    )
    c = cx.api(world.u.contrib)
    cx.send(c, world.lab_a, cx.new_conv(c, world.lab_a))
    result = cx.last_result(fake.calls[1])
    assert result["is_error"] and result["content"] == privacy.REFUSAL
    assert transport.calls == []  # nothing read from Drive
    assert fake.files.uploaded == {} and len(fake.calls) == 2  # nothing sent to Anthropic


def test_one_marked_file_among_several_stops_code_loading_before_any_google_call(
    world, transport, signed_in, monkeypatch
):
    fine = linked(world, DOC, name="Fine")
    marked = marked_drive_file(world, "copy_of_marked_file")
    fake = patch_claude(
        monkeypatch,
        claude_message([cx.load_call(world.lab_a, fine, marked)], stop="tool_use"),
        claude_message([text("No.")]),
    )
    c = cx.api(world.u.contrib)
    cx.send(c, world.lab_a, cx.new_conv(c, world.lab_a))
    assert cx.last_result(fake.calls[1])["content"] == privacy.REFUSAL
    assert transport.calls == [] and fake.files.uploaded == {}


# ------------------------------------------------ positive controls: an unmarked file is read


def drive_doc(transport, body=b"Methods. Hello"):
    meta(transport, DOC)
    transport.on("GET", f"{BASE}{FILE_ID}/export?mimeType=text%2Fplain", raw(body))


def test_in_app_read_file_reads_an_unmarked_drive_file_with_the_askers_token(
    world, transport, signed_in
):
    google(world.u.pi, world.lab_a, "pi-token")  # another member's connection is never used
    drive_doc(transport)
    out = in_app_read(world, linked(world, DOC))
    assert out["text"]["untrusted_content"] == "Methods. Hello"
    assert {kw["headers"]["Authorization"] for _, _, kw in transport.calls} == {
        "Bearer contrib-token"
    }


def test_mcp_read_file_reads_an_unmarked_drive_file_with_the_askers_token(
    world, transport, signed_in
):
    google(world.u.pi, world.lab_a, "pi-token")
    drive_doc(transport)
    result = mcp_read(world, linked(world, DOC))
    assert result["isError"] is False, result
    assert json.loads(result["content"][0]["text"])["text"]["untrusted_content"] == "Methods. Hello"
    assert transport.calls and {kw["headers"]["Authorization"] for _, _, kw in transport.calls} == {
        "Bearer contrib-token"
    }


def test_code_execution_loads_an_unmarked_drive_file_with_the_askers_token(
    world, transport, signed_in, monkeypatch
):
    google(world.u.pi, world.lab_a, "pi-token")
    drive_doc(transport)
    att = linked(world, DOC, name="Notes")
    fake = patch_claude(
        monkeypatch,
        claude_message([cx.load_call(world.lab_a, att)], stop="tool_use"),
        claude_message([text("/files/Notes.txt")], container=cx.CONTAINER),
        claude_message([text("Done.")]),
    )
    c = cx.api(world.u.contrib)
    cx.send(c, world.lab_a, cx.new_conv(c, world.lab_a))
    assert list(fake.files.uploaded.values()) == [("Notes.txt", b"Methods. Hello")]
    assert transport.calls
    assert {kw["headers"]["Authorization"] for _, _, kw in transport.calls} == {
        "Bearer contrib-token"
    }
