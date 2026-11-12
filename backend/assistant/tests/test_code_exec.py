"""VISION C1: Claude runs Python with Anthropic's code execution tool on chosen, unflagged project
files and saves what it made back as an Analysis. The Anthropic client (Messages and Files API) is
the fake in fakes.py; nothing reaches the network."""

import json
from decimal import Decimal

import anthropic
import httpx2 as httpx
import pytest
from django.conf import settings as django_settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from assistant import code_exec, privacy, tools
from assistant.models import AIProviderKey, Conversation, LabAIKey, LabAIUsage
from assistant.tests.fakes import (
    CANARY_KEY,
    LAB_CANARY,
    claude_message,
    patch_claude,
    text,
    tool_use,
)
from audit.models import AuditAction, AuditEvent
from documents import services as document_services
from documents.models import Folder
from provenance.models import Analysis, Result

pytestmark = pytest.mark.django_db
CONTAINER = {"id": "container_1", "expires_at": "2030-01-01T00:00:00Z"}
PNG = b"\x89PNG fake figure"


@pytest.fixture(autouse=True)
def _setup(settings, tmp_path, world):
    cache.clear()
    settings.STORAGES = {
        **django_settings.STORAGES,
        "lab_files": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    for user in (world.u.contrib, world.u.viewer):
        row = AIProviderKey(user=user, provider="anthropic")
        row.set_key(CANARY_KEY)
        row.save()


def put(project, user, name, data=b"x,y\n1,2\n", **kw):
    return document_services.upload_attachment(
        user=user, project=project, file=SimpleUploadedFile(name, data), **kw
    )


def api(user):
    c = Client()
    c.force_login(user)
    return c


def url(lab, *parts):
    return f"/api/labs/{lab.pk}/assistant/" + "/".join(str(p) for p in parts) + "/"


def new_conv(c, lab, provider="anthropic"):
    r = c.post(url(lab, "conversations"), {"provider": provider}, "application/json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def stream(resp):
    assert resp.status_code == 200, resp.content
    body = b"".join(resp.streaming_content).decode()
    out = []
    for chunk in body.split("\n\n"):
        lines = [x for x in chunk.split("\n") if x and not x.startswith(":")]
        if lines:
            out.append((lines[0].removeprefix("event: "), json.loads(lines[1][6:])))
    return out


def send(c, lab, conv, message="Analyse it"):
    return stream(
        c.post(url(lab, "conversations", conv, "messages"), {"text": message}, "application/json")
    )


def load_call(lab, *files):
    return tool_use(
        "toolu_l1",
        code_exec.LOAD,
        {"lab_id": str(lab.pk), "file_ids": [str(f.pk) for f in files]},
    )


def ran(id_, command, outputs=()):
    return [
        {
            "type": "server_tool_use",
            "id": id_,
            "name": "bash_code_execution",
            "input": {"command": command},
        },
        {
            "type": "bash_code_execution_tool_result",
            "tool_use_id": id_,
            "content": {
                "type": "bash_code_execution_result",
                "stdout": "mean 1.5",
                "stderr": "",
                "return_code": 0,
                "content": [{"type": "bash_code_execution_output", "file_id": f} for f in outputs],
            },
        },
    ]


def last_result(call):
    return call["messages"][-1]["content"][0]


def test_load_uploads_places_in_the_container_and_deletes_the_uploads(world, monkeypatch):
    lab, a = world.lab_a, put(world.p1, world.u.pi, "trials.csv")
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, a)], stop="tool_use"),
        claude_message([text("/files/trials.csv")], container=CONTAINER),  # the side request
        claude_message([*ran("srvtoolu_1", "python -c 'print(1.5)'"), text("Mean 1.5.")]),
    )
    c = api(world.u.contrib)
    conv = new_conv(c, lab)
    evs = send(c, lab, conv)
    assert (
        "tool",
        {"type": "tool", "name": "run_code", "title": "Ran code", "status": "done"},
    ) in (evs)
    assert fake.files.uploaded == {"file_in1": ("trials.csv", b"x,y\n1,2\n")}
    assert fake.files.deleted == ["file_in1"]
    place = fake.calls[1]
    assert place["messages"][0]["content"][0] == {"type": "container_upload", "file_id": "file_in1"}
    assert place["tools"] == [code_exec.TOOL] and "container" not in place
    after = fake.calls[2]
    assert after["container"] == "container_1"
    assert code_exec.TOOL in after["tools"]
    assert "container_upload" not in json.dumps(after["messages"])  # history stays replayable
    result = last_result(after)
    assert not result.get("is_error") and "/files/trials.csv" in result["content"]
    ev = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=a.pk)
    assert ev.metadata["for"] == "code_execution" and ev.metadata["via"] == "in_app"
    state = Conversation.objects.get(pk=conv).code_exec
    assert state["inputs"] == [str(a.pk)] and state["container"]["id"] == "container_1"
    code = [
        i for i in c.get(url(lab, "conversations", conv)).json()["items"] if i["kind"] == "code"
    ]
    assert code[0]["title"] == "Ran code" and code[0]["output"] == "mean 1.5"


@pytest.mark.parametrize("which", ["flagged", "in_flagged_folder", "other_lab", "hidden_project"])
def test_files_ai_may_not_see_are_refused_before_anything_is_sent(world, monkeypatch, which):
    lab = world.lab_a
    box = Folder.objects.create(
        lab=lab, project=world.p1, name="Box", created_by=world.u.pi, contains_participant_data=True
    )
    target = {
        "flagged": lambda: put(world.p1, world.u.pi, "P.csv", contains_participant_data=True),
        "in_flagged_folder": lambda: put(world.p1, world.u.pi, "P.csv", folder=box),
        "other_lab": lambda: put(world.pb, world.u.other, "SECRET.csv"),
        "hidden_project": lambda: put(world.p2, world.u.pi, "SECRET.csv"),
    }[which]()
    ok = put(world.p1, world.u.pi, "fine.csv")
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, ok, target)], stop="tool_use"),
        claude_message([text("I can't.")]),
    )
    c = api(world.u.contrib)
    send(c, lab, new_conv(c, lab))
    result = last_result(fake.calls[1])
    assert result["is_error"]
    if which.startswith("flag") or which == "in_flagged_folder":
        assert result["content"] == privacy.REFUSAL
    assert "SECRET" not in result["content"]
    assert fake.files.uploaded == {} and len(fake.calls) == 2  # nothing uploaded, no side request


def test_a_google_copy_of_flagged_upload_is_refused(world, monkeypatch):
    lab = world.lab_a
    original = put(world.p1, world.u.pi, "P.docx", contains_participant_data=True)
    copy = put(world.p1, world.u.pi, "copy.csv")
    copy.copied_from = original
    copy.save()
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, copy)], stop="tool_use"),
        claude_message([text("No.")]),
    )
    c = api(world.u.contrib)
    send(c, lab, new_conv(c, lab))
    assert last_result(fake.calls[1])["content"] == privacy.REFUSAL
    assert fake.files.uploaded == {}


def test_uploads_are_deleted_when_loading_fails(world, monkeypatch):
    lab, a = world.lab_a, put(world.p1, world.u.pi, "trials.csv")
    down = anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.test"))
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, a)], stop="tool_use"),
        down,
        claude_message([text("Sorry.")]),
    )
    c = api(world.u.contrib)
    conv = new_conv(c, lab)
    send(c, lab, conv)
    assert fake.files.deleted == list(fake.files.uploaded) == ["file_in1"]
    assert last_result(fake.calls[2])["is_error"]
    assert "container" not in Conversation.objects.get(pk=conv).code_exec


def save_call(lab, project, **extra):
    args = {"lab_id": str(lab.pk), "project_id": str(project.pk), "title": "Mean RT", **extra}
    return tool_use("toolu_s1", code_exec.SAVE, args)


def test_outputs_are_saved_after_approval_with_an_analysis(world, monkeypatch):
    lab, a = world.lab_a, put(world.p1, world.u.pi, "trials.csv")
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, a)], stop="tool_use"),
        claude_message([text("/files/trials.csv")], container=CONTAINER),
        claude_message(
            [
                *ran("srvtoolu_1", "python plot.py", ["file_out1", "file_out2"]),
                save_call(lab, world.p1, summary="RT is fast."),
            ],
            stop="tool_use",
        ),
        claude_message([text("Saved.")]),
    )
    fake.files.outputs = {
        "file_out1": ("/tmp/outputs/../fig.png", PNG),
        "file_out2": ("page.html", b"<script>alert(1)</script>"),
    }
    c = api(world.u.contrib)
    conv = new_conv(c, lab)
    evs = send(c, lab, conv)
    waiting = next(d for k, d in evs if k == "approval_required")["calls"][0]
    assert {"label": "Files that will be saved", "text": "fig.png, page.html"} in waiting["preview"]
    assert not Analysis.objects.for_lab(lab).filter(title="Mean RT").exists()  # nothing yet

    r = c.post(
        url(lab, "conversations", conv, "approvals"),
        {"decisions": {"toolu_s1": True}},
        "application/json",
    )
    stream(r)
    out = json.loads(last_result(fake.calls[-1])["content"])
    assert [s["name"] for s in out["saved"]] == ["fig.png"]
    assert out["skipped"][0]["name"] == "page.html"
    an = Analysis.objects.for_lab(lab).get(title="Mean RT")
    assert an.project_id == world.p1.pk and an.ran_by_id == world.u.contrib.pk
    assert "trials.csv" in an.description and "RT is fast." in an.description
    with document_services.lab_files().open(an.code_attachment.storage_key, "rb") as fh:
        assert fh.read() == b"python plot.py"
    res = Result.objects.for_lab(lab).get(analysis=an)
    [fig] = res.attachments.all()
    assert fig.original_filename == "fig.png" and fig.content_type == "image/png"
    ev = AuditEvent.objects.get(action=AuditAction.AI_TOOL_WRITE)
    assert ev.metadata["tool"] == code_exec.SAVE and ev.metadata["via"] == "in_app"
    [row] = [
        i for i in c.get(url(lab, "conversations", conv)).json()["items"] if i["kind"] == "code"
    ]
    files = {f["name"]: f for f in row["files"]}
    assert files["fig.png"]["analysis_url"].endswith(f"/analyses/{an.pk}")
    assert files["page.html"]["url"] is None


def test_a_viewer_cannot_save_outputs(world, monkeypatch):
    lab = world.lab_a
    fake = patch_claude(
        monkeypatch,
        claude_message(
            [*ran("srvtoolu_1", "python plot.py", ["file_out1"]), save_call(lab, world.p1)],
            stop="tool_use",
        ),
        claude_message([text("I can't.")]),
    )
    fake.files.outputs = {"file_out1": ("fig.png", PNG)}
    c = api(world.u.viewer)
    conv = new_conv(c, lab)
    send(c, lab, conv)
    r = c.post(
        url(lab, "conversations", conv, "approvals"),
        {"decisions": {"toolu_s1": True}},
        "application/json",
    )
    stream(r)
    assert last_result(fake.calls[-1])["is_error"]
    assert not Analysis.objects.for_lab(lab).filter(title="Mean RT").exists()


def test_the_container_is_dropped_once_a_loaded_file_is_flagged(world, monkeypatch):
    lab, a = world.lab_a, put(world.p1, world.u.pi, "trials.csv")
    fake = patch_claude(
        monkeypatch,
        claude_message([load_call(lab, a)], stop="tool_use"),
        claude_message([text("/files/trials.csv")], container=CONTAINER),
        claude_message([text("Loaded.")], container=CONTAINER),
        claude_message([text("Hi.")]),
    )
    c = api(world.u.contrib)
    conv = new_conv(c, lab)
    send(c, lab, conv)
    privacy.set_flag(a, True, user=world.u.pi)
    send(c, lab, conv, "Again")
    assert "container" not in fake.calls[-1]
    assert Conversation.objects.get(pk=conv).code_exec["inputs"] == []


def test_no_code_tools_outside_new_claude_chats(world, monkeypatch):
    lab = world.lab_a
    fake = patch_claude(monkeypatch, claude_message([text("Hi.")]), claude_message([text("Hi.")]))
    c = api(world.u.contrib)
    fresh, old = new_conv(c, lab), new_conv(c, lab)
    Conversation.objects.filter(pk=old).update(code_exec=None)  # made before code execution
    send(c, lab, fresh)
    send(c, lab, old)
    names = [[t.get("name") for t in call["tools"]] for call in fake.calls]
    assert "code_execution" in names[0] and code_exec.LOAD in names[0]
    assert "code_execution" not in names[1] and code_exec.LOAD not in names[1]
    assert code_exec.SAVE not in names[1] and "container" not in fake.calls[1]
    # OpenAI chats never get it; nor does the MCP server
    r = c.post(url(lab, "conversations"), {"provider": "openai"}, "application/json")
    assert Conversation.objects.get(pk=r.json()["id"]).code_exec is None
    assert code_exec.LOAD not in [d["name"] for d in tools.definitions()]
    ctx = tools.Context(user=world.u.contrib, lab_ids=frozenset({str(lab.pk)}), can_write=False)
    with pytest.raises(KeyError):
        tools.call(ctx, code_exec.LOAD, {"lab_id": str(lab.pk), "file_ids": []})


def test_the_lab_key_is_charged_for_the_loading_request(world, monkeypatch):
    lab, a = world.lab_a, put(world.p1, world.u.pi, "trials.csv")
    AIProviderKey.objects.filter(user=world.u.contrib).delete()  # so the lab key is used
    row = LabAIKey(lab=lab, provider="anthropic", monthly_cap_usd=Decimal("10.00"))
    row.set_key(LAB_CANARY)
    row.save()
    patch_claude(
        monkeypatch,
        claude_message([load_call(lab, a)], stop="tool_use"),
        claude_message(
            [text("/files/trials.csv")], container=CONTAINER, usage={"input_tokens": 1_000_000}
        ),
        claude_message([text("Loaded.")]),
    )
    c = api(world.u.contrib)
    send(c, lab, new_conv(c, lab))
    usage = LabAIUsage.objects.for_lab(lab).get(user=world.u.contrib)
    # three requests at 100 input tokens each would cost far less than the loading one alone
    assert usage.cost_usd >= Decimal("4.00") and usage.input_tokens >= 1_000_000
