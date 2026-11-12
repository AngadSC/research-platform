"""Our own analysis runner (VISION C2 and D2): the app's side. The runner is a separate server
(runner/server.py, docs/DEPLOY.md "Analysis runner"); the feature is off until both
ANALYSIS_RUNNER_URL and ANALYSIS_RUNNER_SECRET are set.

`run` sends one job, signed with HMAC-SHA256 and stamped with the time so it cannot be replayed,
and checks the answer's signature. `save_run` keeps a successful run in the project: the code as
a file, each output as a file, and an Analysis with one Result per output, so the Analyses page
shows it. Callers check access and the participant-data flag before anything is sent (the AI
tool run_code in assistant/tools.py does).
"""

import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import secrets
import time

import requests
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from documents import services as document_services
from provenance import services as provenance_services

log = logging.getLogger(__name__)

LANGUAGES = {"python": ("Python", "py"), "r": ("R", "R"), "octave": ("Octave", "m")}
MAX_FILES = 20
MAX_INPUT_BYTES = 50 * 2**20  # the runner's own cap
WAIT = 240  # seconds: the runner's 120 s limit, plus sending files both ways


class RunnerError(Exception):
    """A plain message for the person: the run did not happen or its answer was not trusted."""


def configured() -> bool:
    return bool(settings.ANALYSIS_RUNNER_URL and settings.ANALYSIS_RUNNER_SECRET)


def _sign(body: bytes) -> bytes:
    key = settings.ANALYSIS_RUNNER_SECRET.encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest().encode()


def run(language, code, files) -> dict:
    """Run `code` with `files` [(name, bytes)] on the runner. Returns {exit_code, timed_out,
    stdout, stderr, outputs: [(name, bytes)], skipped_outputs}. Raises RunnerError."""
    job = secrets.token_hex(16)
    body = json.dumps(
        {
            "ts": int(time.time()),
            "job": job,
            "language": language,
            "code": code,
            "files": [{"name": n, "data": base64.b64encode(d).decode()} for n, d in files],
        }
    ).encode()
    try:
        resp = requests.post(
            settings.ANALYSIS_RUNNER_URL.rstrip("/") + "/run",
            data=body,
            headers={"Content-Type": "application/json", "X-Runner-Signature": _sign(body)},
            timeout=(10, WAIT),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        log.warning("analysis runner unreachable: %s", type(exc).__name__)
        raise RunnerError("The analysis server could not be reached. Try again later.") from None
    signature = resp.headers.get("X-Runner-Signature", "").encode("latin-1", "replace")
    if not hmac.compare_digest(_sign(resp.content), signature):
        log.warning("analysis runner answer not signed (HTTP %s)", resp.status_code)
        raise RunnerError("The analysis server's answer could not be trusted.")
    try:
        out = resp.json()
    except ValueError:
        out = {}
    if resp.status_code == 503:
        raise RunnerError("The analysis server is busy. Try again in a minute.")
    if resp.status_code == 400:  # our own server's message about the job, such as a file name
        raise RunnerError(str(out.get("error") or "The analysis server refused the run.")[:300])
    if resp.status_code != 200 or out.get("job") != job:
        log.warning("analysis runner refused the job (HTTP %s)", resp.status_code)
        raise RunnerError("The analysis server refused the run.")
    out["outputs"] = [(o["name"], base64.b64decode(o["data"])) for o in out.get("outputs", [])]
    return out


def _put(*, user, project, name, data, request):
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return document_services.upload_attachment(
        user=user,
        project=project,
        file=SimpleUploadedFile(name, data, content_type=content_type),
        request=request,
        source="link",  # shown as "added through Claude", like an upload link (D269)
    )


def save_run(*, user, project, language, code, inputs, result, title="", request=None):
    """Keep a finished run in `project`: the code and every output as files, and an Analysis
    (one Result per output). `inputs` are the input Attachments. Returns (analysis, outputs)."""
    label, ext = LANGUAGES[language]
    code_file = _put(
        user=user, project=project, name=f"analysis.{ext}", data=code.encode(), request=request
    )
    outputs = [
        _put(user=user, project=project, name=name, data=data, request=request)
        for name, data in result["outputs"]
    ]
    lines = [
        f"{label} code run on the analysis server by Claude.",
        "Inputs: " + (", ".join(a.original_filename for a in inputs) or "none") + ".",
    ]
    if result.get("stdout"):
        lines += ["", "Printed output:", result["stdout"][:2000]]
    analysis = provenance_services.create(
        "analysis",
        project=project,
        user=user,
        data={
            "title": (title or f"{label} run")[:300],
            "description": "\n".join(lines),
            "code_attachment": code_file.pk,
        },
        request=request,
    )
    provenance_services.create_result_set(
        project=project,
        user=user,
        analysis=analysis.pk,
        items=[{"title": a.original_filename, "attachments": [a.pk]} for a in outputs],
        request=request,
    )
    return analysis, outputs
