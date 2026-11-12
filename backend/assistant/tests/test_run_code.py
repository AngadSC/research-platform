"""VISION C2 and D2: the run_code AI tool and the analysis runner client (provenance/runner.py),
with the runner itself mocked. The runner's own tests are in runner/test_server.py."""

import base64
import hashlib
import hmac
import json
import time

import pytest
import requests
from django.conf import settings as django_settings
from django.core.files.uploadedfile import SimpleUploadedFile

from assistant import mcp, privacy, services, tools
from assistant.tests.test_mcp import data, rpc
from audit.models import AuditAction, AuditEvent
from documents import services as document_services
from documents.models import Attachment, Folder
from provenance import runner
from provenance.models import Analysis, Result

pytestmark = pytest.mark.django_db
SECRET = "test-runner-secret-" + "x" * 20
PNG = b"\x89PNG fake figure"


@pytest.fixture(autouse=True)
def lab_files(settings, tmp_path):
    settings.STORAGES = {
        **django_settings.STORAGES,
        "lab_files": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }


@pytest.fixture
def on(settings):
    settings.ANALYSIS_RUNNER_URL = "http://runner.example.test:8700"
    settings.ANALYSIS_RUNNER_SECRET = SECRET


@pytest.fixture
def sent(monkeypatch):
    """Replaces the runner: records each job and answers with `sent.answer`."""
    jobs = []

    def fake(language, code, files):
        jobs.append({"language": language, "code": code, "files": dict(files)})
        if isinstance(sent.answer, Exception):
            raise sent.answer
        return sent.answer

    sent = type("Sent", (), {"jobs": jobs})()
    sent.answer = {
        "exit_code": 0,
        "timed_out": False,
        "stdout": "mean rt 512\n",
        "stderr": "",
        "outputs": [("rt.png", PNG), ("summary.csv", b"m,512\n")],
        "skipped_outputs": 0,
    }
    monkeypatch.setattr(runner, "run", fake)
    return sent


def put(project, user, name, data, folder=None, flagged=False):
    return document_services.upload_attachment(
        user=user,
        project=project,
        folder=folder,
        file=SimpleUploadedFile(name, data, content_type="text/csv"),
        contains_participant_data=flagged,
    )


@pytest.fixture
def files(world):
    p1, pi = world.p1, world.u.pi
    secret = Folder.objects.create(
        lab=world.lab_a,
        project=p1,
        name="PARTICIPANT box",
        created_by=pi,
        contains_participant_data=True,
    )
    flagged = put(p1, pi, "PARTICIPANT.csv", b"name\nJane", flagged=True)
    copy = Attachment.objects.create(
        lab=world.lab_a,
        project=p1,
        uploaded_by=pi,
        size_bytes=0,
        sha256="",
        original_filename="PARTICIPANT copy",
        storage_key="k-copy",
        copied_from=flagged,
    )
    return {
        "csv": put(p1, pi, "rt.csv", b"id,rt\n1,512\n"),
        "flagged": flagged,
        "in_flagged": put(p1, pi, "PARTICIPANT-in-box.csv", b"x", folder=secret),
        "copy": copy,
        "p2": put(world.p2, pi, "SECRET-p2.csv", b"hidden"),
        "b": put(world.pb, world.u.other, "SECRET-labb.csv", b"other lab"),
    }


def ctx(user, lab, write=True, via="mcp"):
    return tools.Context(
        user=user, lab_ids=frozenset({str(lab.pk)}), can_write=write, via=via, client="Test"
    )


def args(world, *file_keys, files=None, **more):
    return {
        "lab_id": str(world.lab_a.pk),
        "project_id": str(world.p1.pk),
        "language": "python",
        "code": "import pandas as pd\nprint(pd.read_csv('rt.csv').rt.mean())",
        "file_ids": [str(files[k].pk) for k in file_keys],
        **more,
    }


def refused(c, a):
    with pytest.raises(tools.ToolError) as exc:
        tools.call(c, "run_code", a)
    return str(exc.value)


# ---------------------------------------------------------------- offered only when configured


def test_hidden_and_refused_when_the_runner_is_not_set_up(world, files, sent):
    assert not runner.configured()
    assert "run_code" not in {d["name"] for d in tools.definitions()}
    assert "run_code" not in {t["name"] for t in mcp._tool_list()}
    c = ctx(world.u.pi, world.lab_a)
    assert "not available" in refused(c, args(world, "csv", files=files))
    assert sent.jobs == []


def test_offered_to_the_assistant_and_over_mcp_when_set_up(world, on):
    by = {d["name"]: d for d in tools.definitions()}
    assert by["run_code"]["write"] is True
    assert by["run_code"]["input_schema"]["properties"]["language"]["enum"] == [
        "python",
        "r",
        "octave",
    ]
    listed = {t["name"]: t for t in mcp._tool_list()}
    assert listed["run_code"]["annotations"]["readOnlyHint"] is False
    assert "run_code" in mcp.INSTRUCTIONS


def test_runs_over_mcp_on_the_persons_own_plan(world, files, on, sent):
    _, token = services.create_pat(
        world.u.contrib, name="CLI", lab_ids=[world.lab_a.pk], access="write", days=30
    )
    a = args(world, "csv", files=files)
    out = data(rpc(token, "tools/call", {"name": "run_code", "arguments": a}))
    assert out["saved"] is True and out["analysis"]["title"] == "Python run"
    assert sent.jobs[0]["files"] == {"rt.csv": b"id,rt\n1,512\n"}
    # a read-only connection is asked to step up and never reaches the runner
    _, read_only = services.create_pat(
        world.u.contrib, name="RO", lab_ids=[world.lab_a.pk], access="read", days=30
    )
    result = rpc(read_only, "tools/call", {"name": "run_code", "arguments": a}).json()["result"]
    assert result["isError"] is True and len(sent.jobs) == 1


# ---------------------------------------------------------------- what may be sent


@pytest.mark.parametrize("key", ["flagged", "in_flagged", "copy"])
def test_participant_data_never_reaches_the_runner(world, files, on, sent, key):
    c = ctx(world.u.pi, world.lab_a)
    assert refused(c, args(world, "csv", key, files=files)) == privacy.REFUSAL
    assert sent.jobs == []


def test_a_flag_set_later_on_the_folder_is_honoured(world, files, on, sent):
    box = Folder.objects.create(
        lab=world.lab_a, project=world.p1, name="Raw", created_by=world.u.pi
    )
    files["later"] = put(world.p1, world.u.pi, "later.csv", b"1", folder=box)
    privacy.set_flag(box, True, user=world.u.pi)
    c = ctx(world.u.pi, world.lab_a)
    assert refused(c, args(world, "later", files=files)) == privacy.REFUSAL
    assert sent.jobs == []


def test_other_projects_labs_and_roles_are_refused(world, files, on, sent):
    pi = ctx(world.u.pi, world.lab_a)
    assert "No file with that id in this project" in refused(pi, args(world, "p2", files=files))
    assert "No file" in refused(pi, args(world, "b", files=files))  # lab B's file
    other_lab = {**args(world, files=files), "lab_id": str(world.lab_b.pk)}
    assert "No lab" in refused(pi, other_lab)
    other_project = {**args(world, files=files), "project_id": str(world.pb.pk)}
    assert "No project" in refused(pi, other_project)
    # P2 is the pi's only: the contributor cannot see it, nor its files
    contrib = ctx(world.u.contrib, world.lab_a)
    on_p2 = {**args(world, "p2", files=files), "project_id": str(world.p2.pk)}
    assert "No project" in refused(contrib, on_p2)
    viewer = ctx(world.u.viewer, world.lab_a)
    assert "does not allow changes" in refused(viewer, args(world, "csv", files=files))
    with pytest.raises(tools.WriteNotAllowed):
        tools.call(ctx(world.u.pi, world.lab_a, write=False), "run_code", args(world, files=files))
    assert sent.jobs == []


def test_the_size_cap_is_checked_before_anything_is_sent(world, files, on, sent, monkeypatch):
    monkeypatch.setattr(runner, "MAX_INPUT_BYTES", 5)
    c = ctx(world.u.pi, world.lab_a)
    assert "too large" in refused(c, args(world, "csv", files=files))
    assert sent.jobs == []


def test_the_approval_dialog_names_the_files(world, files, on):
    c = ctx(world.u.pi, world.lab_a)
    described = tools.describe_call(c, "run_code", args(world, "csv", files=files))
    assert described["resolved"]["files"] == "rt.csv"
    assert described["preview"][0]["label"] == "Code that will run on the analysis server"
    flagged = tools.describe_call(c, "run_code", args(world, "csv", "flagged", files=files))
    assert flagged["resolved"]["files"] == tools.NOT_FOUND


# ---------------------------------------------------------------- what is kept


def test_a_successful_run_is_saved_as_an_analysis(world, files, on, sent):
    c = ctx(world.u.contrib, world.lab_a, via="in_app")
    out = tools.call(c, "run_code", args(world, "csv", files=files, title="RT means"))
    assert sent.jobs[0]["language"] == "python"
    assert sent.jobs[0]["files"] == {"rt.csv": b"id,rt\n1,512\n"}
    assert out["stdout"]["untrusted_content"] == "mean rt 512\n"
    analysis = Analysis.objects.for_lab(world.lab_a).get(pk=out["analysis"]["id"])
    assert (analysis.title, analysis.project, analysis.ran_by) == (
        "RT means",
        world.p1,
        world.u.contrib,
    )
    assert "Inputs: rt.csv." in analysis.description and "mean rt 512" in analysis.description
    code = analysis.code_attachment
    assert code.original_filename == "analysis.py" and code.project == world.p1
    with document_services.lab_files().open(code.storage_key, "rb") as fh:
        assert fh.read().decode() == args(world, files=files)["code"]
    results = Result.objects.for_lab(world.lab_a).filter(analysis=analysis).order_by("title")
    assert [r.title for r in results] == ["rt.png", "summary.csv"]
    png = results[0].attachments.get()
    assert (png.content_type, png.source, png.uploaded_by) == ("image/png", "link", world.u.contrib)
    assert {o["name"] for o in out["outputs"]} == {"rt.png", "summary.csv"}
    assert out["url"].endswith(f"/workflow/analysis/analyses/{analysis.pk}")
    events = AuditEvent.objects.filter(lab=world.lab_a)
    read = events.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=files["csv"].pk)
    assert read.metadata["to"] == "analysis_runner"
    write = events.get(action=AuditAction.AI_TOOL_WRITE)
    assert (write.metadata["tool"], write.target_id) == ("run_code", analysis.pk)
    assert events.filter(action=AuditAction.ANALYSIS_CREATED, target_id=analysis.pk).exists()


@pytest.mark.parametrize(
    "answer", [{"exit_code": 1, "timed_out": False}, {"exit_code": None, "timed_out": True}]
)
def test_a_failed_run_saves_nothing(world, files, on, sent, answer):
    sent.answer = {**sent.answer, **answer, "stderr": "Traceback: boom"}
    before = Attachment.objects.for_lab(world.lab_a).count()
    out = tools.call(ctx(world.u.pi, world.lab_a), "run_code", args(world, "csv", files=files))
    assert out["saved"] is False and out["stderr"]["untrusted_content"] == "Traceback: boom"
    assert Attachment.objects.for_lab(world.lab_a).count() == before
    assert not Analysis.objects.for_lab(world.lab_a).filter(title="Python run").exists()
    write = AuditEvent.objects.get(lab=world.lab_a, action=AuditAction.AI_TOOL_WRITE)
    assert write.target_id == world.p1.pk


def test_a_runner_failure_keeps_the_audit_of_what_was_sent(world, files, on, sent):
    sent.answer = runner.RunnerError("The analysis server is busy. Try again in a minute.")
    out = tools.call(ctx(world.u.pi, world.lab_a), "run_code", args(world, "csv", files=files))
    assert out == {"error": "The analysis server is busy. Try again in a minute.", "saved": False}
    assert AuditEvent.objects.filter(
        lab=world.lab_a, action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=files["csv"].pk
    ).exists()


# ---------------------------------------------------------------- the signed client


class Answer:
    def __init__(self, status, body, sign=True):
        self.status_code, self.content = status, json.dumps(body).encode()
        mac = hmac.new(SECRET.encode(), self.content, hashlib.sha256).hexdigest()
        self.headers = {"X-Runner-Signature": mac if sign else "0" * 64}

    def json(self):
        return json.loads(self.content)


def test_the_client_signs_the_job_and_checks_the_answer(on, monkeypatch):
    seen = {}

    def post(url, data, headers, timeout, allow_redirects):
        seen.update(url=url, body=data, sig=headers["X-Runner-Signature"])
        job = json.loads(data)["job"]
        out = [{"name": "f.png", "data": base64.b64encode(PNG).decode()}]
        return seen["answer"](job, out)

    monkeypatch.setattr(requests, "post", post)
    seen["answer"] = lambda job, out: Answer(200, {"job": job, "exit_code": 0, "outputs": out})
    got = runner.run("r", "x <- 1", [("a.csv", b"1")])
    assert seen["url"] == "http://runner.example.test:8700/run"
    assert hmac.compare_digest(
        seen["sig"], hmac.new(SECRET.encode(), seen["body"], hashlib.sha256).hexdigest().encode()
    )
    job = json.loads(seen["body"])
    assert job["language"] == "r" and abs(job["ts"] - time.time()) < 5
    assert job["files"] == [{"name": "a.csv", "data": base64.b64encode(b"1").decode()}]
    assert got["outputs"] == [("f.png", PNG)]

    for answer, message in (
        (lambda job, out: Answer(200, {"job": job}, sign=False), "could not be trusted"),
        (lambda job, out: Answer(200, {"job": "another"}), "refused"),
        (lambda job, out: Answer(503, {"error": "busy"}), "busy"),
        (lambda job, out: Answer(400, {"error": "Rename the file 'a/b'"}), "Rename the file"),
        (lambda job, out: Answer(401, {"error": "Bad signature."}), "refused the run"),
    ):
        seen["answer"] = answer
        with pytest.raises(runner.RunnerError, match=message):
            runner.run("python", "1", [])

    def down(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", down)
    with pytest.raises(runner.RunnerError, match="could not be reached"):
        runner.run("python", "1", [])
