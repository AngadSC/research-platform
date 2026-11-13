"""VISION C1: in the in-app assistant, Claude runs Python on chosen project files with Anthropic's
code execution tool (Python runs in Anthropic's sandbox, never on our server), and saves what it
made back to the project as an Analysis.

- Only Claude conversations made after this existed have it (`Conversation.code_exec` is not
  None); they always run on an API key, the person's own or the lab's (D277).
- `load_files_for_analysis` runs every check `read_file` runs (the file is fetched through
  `tools._file`: lab, project access, the participant-data flag on the file, its folder and the
  upload a Google copy came from), then uploads the bytes to the Files API and puts them in the
  conversation's container with one small side request. The side request keeps the chat history
  append-only: a `container_upload` block in the history would name a file we delete when the
  load ends, and every later request replays the history. The uploads are deleted in `finally`.
- The container is reused for the whole conversation (same key only, under 30 days old). It is
  dropped as soon as a file loaded into it is flagged, deleted or no longer visible to the person.
- `save_analysis_outputs` is a write, so the person approves it like every other write. It saves
  the files the code wrote to $OUTPUT_DIR (allowed types, attachment size limit, basename only),
  the code that ran (as a text file) and an Analysis with a Result holding the outputs.
"""

import datetime
import hashlib
import logging
import posixpath

import anthropic
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from assistant import drive_files, privacy, tools
from assistant.ai import claude, lab_keys
from assistant.models import Conversation, LabAIKey, Role
from audit.models import AuditAction
from audit.services import record
from core.permissions import scope
from documents import services as document_services
from documents.models import Attachment
from projects.models import Project
from provenance import services as provenance_services

log = logging.getLogger(__name__)

TOOL = {"type": "code_execution_20260521", "name": "code_execution"}
LOAD, SAVE = "load_files_for_analysis", "save_analysis_outputs"
MAX_FILES = 10
SIDE_MAX_TOKENS = 2000  # the loading request only lists the file paths
MAX_BYTES = settings.ATTACHMENT_MAX_BYTES  # all loaded files together, and each saved output
CONTAINER_DAYS = 29  # Anthropic keeps a container 30 days after it was made
OUTPUT_TYPES = {  # what may be saved back: no HTML or SVG, which could carry script
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
EXPORT_EXT = {"text/plain": ".txt", "text/csv": ".csv"}  # Google's own formats, exported
PLACE_PROMPT = (
    "Files were uploaded with this message. Run one bash command that prints the full path of "
    "each uploaded file, then reply with only those paths, one per line."
)
# ponytail: Anthropic bills code execution by container time (1,550 free hours a month per
# organisation, then $0.05 an hour, 5 minutes minimum), but `usage` reports only a request count
# (server_tool_use.code_execution_requests), so the lab key's cap counts tokens only. Charge an
# estimate per request here if labs ever go past the free hours.


def on(conv) -> bool:
    return conv.code_exec is not None


def _store(conv):
    Conversation.objects.filter(pk=conv.pk).update(code_exec=conv.code_exec)


def _key_tag(key) -> str:
    # the ciphertext changes whenever the key is replaced in place (another org or workspace)
    digest = hashlib.sha256(key.key_ciphertext.encode()).hexdigest()[:12]
    return f"{key._meta.model_name}:{key.pk}:{digest}"


def safe_name(name, fallback="output") -> str:
    """Basename only, no characters the Files API or a file system refuses, at most 255."""
    name = posixpath.basename(str(name or "").replace("\\", "/"))
    name = "".join("_" if c in '<>:"|?*' or not c.isprintable() else c for c in name).strip()
    return (name if name not in ("", ".", "..") else fallback)[:255]


# ---------------------------------------------------------------- the container


def container_for(conv, key):
    """The container to reuse, or None for a new one. Dropped when it belongs to another key,
    is near its 30 days, or holds a file the person may no longer give to AI."""
    state = conv.code_exec or {}
    c = state.get("container")
    if not c:
        return None
    inputs = state.get("inputs", [])
    visible = (
        privacy.ai_visible(scope(Attachment, conv.user, conv.lab))
        .filter(
            pk__in=inputs,
            deleted_at__isnull=True,
            project__isnull=False,
            project__deleted_at__isnull=True,
        )
        .count()
    )
    old = timezone.now() - datetime.datetime.fromisoformat(c["created"])
    if (
        c["key"] != _key_tag(key)
        or old > datetime.timedelta(days=CONTAINER_DAYS)
        or (visible != len(inputs))
    ):
        state.pop("container")
        state["inputs"] = []
        # what the code made from those files must not be saved either (a flagged source)
        outputs = state.get("outputs", {})
        state["outputs"] = {k: v for k, v in outputs.items() if v["attachment"]}
        _store(conv)
        _delete_files(key, [k for k in outputs if k not in state["outputs"]])
        return None
    return c["id"]


def _delete_files(key, file_ids):
    """Best effort: remove files from the key holder's Files API."""
    if not file_ids:
        return
    try:
        client = claude._client(key.api_key())
    except Exception:
        return
    for file_id in file_ids:
        try:
            client.files.delete(file_id)
        except Exception:
            log.warning("could not delete a code output")


def keep_container(conv, key, container_id):
    state = conv.code_exec
    if not container_id or (state.get("container") or {}).get("id") == container_id:
        return
    state["container"] = {
        "id": container_id,
        "key": _key_tag(key),
        "created": timezone.now().isoformat(),
    }
    _store(conv)


# ---------------------------------------------------------------- after each model turn


def _results(content):
    for b in content:
        if b.get("type") in claude.CODE_RESULTS:
            yield b


def output_ids(content):
    """Files the code wrote to $OUTPUT_DIR, in the order they were made."""
    for b in _results(content):
        inner = b.get("content")
        inner = inner if isinstance(inner, dict) else {}
        for o in inner.get("content") or []:
            if o.get("type") == "bash_code_execution_output" and o.get("file_id"):
                yield o["file_id"]


def after_turn(run, result):
    """Remember the container and name every new output (the Files API gives the name)."""
    conv = run.conv
    keep_container(conv, run.key, result.meta.pop("container", None))
    new = [f for f in output_ids(result.content) if f not in conv.code_exec.get("outputs", {})]
    if not new:
        return
    outputs = conv.code_exec.setdefault("outputs", {})
    client = claude._client(run.key.api_key())
    for file_id in new:
        try:
            meta = client.files.retrieve_metadata(file_id)
            name, size = meta.filename, meta.size_bytes or 0
        except Exception:  # the name is only for show; saving fetches the file again
            log.warning("code output metadata failed")
            name, size = "output", 0
        outputs[file_id] = {"name": safe_name(name), "size": size, "attachment": None}
    _store(conv)


# ---------------------------------------------------------------- what the chat shows


def _code_of(block) -> tuple[str, str]:
    """(title, code) of one server_tool_use block."""
    args = block.get("input") or {}
    if block.get("name") == "bash_code_execution":
        return "Ran code", str(args.get("command", ""))
    path, cmd = str(args.get("path", "")), args.get("command")
    if cmd == "create":
        return "Wrote a file", f"# {path}\n{args.get('file_text', '')}"
    if cmd == "str_replace":
        return (
            "Edited a file",
            f"# {path}\n- {args.get('old_str', '')}\n+ {args.get('new_str', '')}",
        )
    return "Read a file", path


def _output_of(result) -> tuple[bool, str]:
    inner = (result or {}).get("content") or {}
    if not isinstance(inner, dict):
        return True, ""
    if inner.get("error_code"):
        return False, f"Error: {inner['error_code']}"
    if "stdout" in inner:
        out = "\n".join(x for x in (inner.get("stdout"), inner.get("stderr")) if x)
        return inner.get("return_code", 0) == 0, out
    viewed = inner.get("type", "").endswith("view_result")
    return True, str(inner.get("content", "")) if viewed else ""


def results_by_id(messages) -> dict:
    """Every code result of the conversation by the id of its step (a step's result can arrive
    in a later message when Claude also called one of our tools)."""
    return {
        b.get("tool_use_id"): b
        for m in messages
        if m.role == Role.ASSISTANT
        for b in _results(m.content)
    }


def items(conv, message, results) -> list[dict]:
    """One "Ran code" row per code step in an assistant message, with its output and the files
    it made (linked once saved)."""
    if not on(conv):
        return []
    outputs = conv.code_exec.get("outputs", {})
    base = f"/labs/{conv.lab_id}/projects"  # app paths, for the chat's own links
    rows = []
    for b in message.content:
        if b.get("type") != "server_tool_use":
            continue
        result = results.get(b.get("id"))
        title, code = _code_of(b)
        ok, output = _output_of(result)
        files = []
        for file_id in output_ids([result] if result else []):
            out = outputs.get(file_id, {"name": "output"})
            saved = out.get("project")
            files.append(
                {
                    "name": out["name"],
                    "url": f"{base}/{saved}/documents" if saved else None,
                    "analysis_url": (
                        f"{base}/{saved}/workflow/analysis/analyses/{out['analysis']}"
                        if saved
                        else None
                    ),
                }
            )
        rows.append(
            {
                "id": f"{message.pk}:{b.get('id')}",
                "kind": "code",
                "title": title,
                "code": code[:20_000],
                "output": output[:10_000],
                "status": ("done" if ok else "error") if result else "running",
                "files": files,
            }
        )
    return rows


def pending(conv, names=None) -> list[tuple[str, dict]]:
    """Outputs not saved yet; only those named, when names are given."""
    rows = [
        (f, o) for f, o in (conv.code_exec or {}).get("outputs", {}).items() if not o["attachment"]
    ]
    return [r for r in rows if r[1]["name"] in set(names)] if names else rows


def preview(conv, args) -> list[dict]:
    """The approval dialog's line naming the files that will be saved."""
    names = [o["name"] for _f, o in pending(conv, (args or {}).get("files"))]
    return [{"label": "Files that will be saved", "text": ", ".join(names) or "None"}]


# ---------------------------------------------------------------- the tools


def _run(ctx):
    run = ctx.run
    if run is None or not on(run.conv):
        raise tools.ToolError("Running code is not available in this conversation.")
    return run


def _bytes(ctx, lab, a) -> tuple[bytes, str]:
    """(bytes, file name) of one file the person may give to AI (checked by the caller)."""
    if a.from_drive:
        data, _kind = tools._drive_bytes(ctx, lab, a)  # the person's own Google connection
        name = safe_name(a.original_filename, "file")
        ext = EXPORT_EXT.get(drive_files.EXPORTS.get(a.content_type, ""), "")
        return data, name if name.endswith(ext) else name + ext
    if a.size_bytes > MAX_BYTES:
        raise tools.ToolError(f"{a.original_filename} is too large to load.")
    try:
        with document_services.lab_files().open(a.storage_key, "rb") as fh:
            return fh.read(), safe_name(a.original_filename, "file")
    except FileNotFoundError:
        raise tools.ToolError("The stored file could not be found.") from None


def _place(client, run, file_ids, container):
    """One small request that puts the uploaded files into the container. Returns the response."""
    kwargs = {
        "model": run.conv.model,
        "max_tokens": SIDE_MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "container_upload", "file_id": f} for f in file_ids]
                + [{"type": "text", "text": PLACE_PROMPT}],
            }
        ],
        "tools": [TOOL],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low"},
    }
    if container:
        try:
            return client.messages.create(container=container, **kwargs)
        except (anthropic.BadRequestError, anthropic.NotFoundError):
            pass  # the container expired: start a new one
    return client.messages.create(**kwargs)


@tools.tool(
    LOAD,
    "Load files for code",
    "Copy project files into your code sandbox so you can analyse them with Python (pandas, "
    "numpy, scipy, statsmodels, matplotlib and seaborn are installed; there is no internet). "
    f"Pass file ids from list_files: up to {MAX_FILES} files, {MAX_BYTES // 2**20} MB in total. "
    "Google Docs and Slides arrive as text and Sheets as CSV (first sheet). Files marked as "
    "participant data cannot be loaded. The result gives each file's path in the sandbox. To "
    "keep a figure or table, write it to $OUTPUT_DIR, then call save_analysis_outputs. Loading "
    "is recorded in the lab's audit log, as a download is in the app.",
    required=("lab_id", "file_ids"),
    in_app=True,
    lab_id=tools.LAB,
    file_ids={
        "type": "array",
        "items": {"type": "string"},
        "maxItems": MAX_FILES,
        "description": "File ids, from list_files.",
    },
)
def load_files_for_analysis(ctx, lab_id, file_ids):
    run = _run(ctx)
    lab = tools._lab(ctx, lab_id)
    if not file_ids:
        raise tools.ToolError("file_ids is required.")
    # every check read_file makes, for every file, before anything is read or sent anywhere
    files = [tools._file(ctx, lab, f) for f in dict.fromkeys(file_ids)]
    blobs, total, seen = [], 0, set()
    for a in files:
        data, name = _bytes(ctx, lab, a)
        total += len(data)
        if total > MAX_BYTES:
            raise tools.ToolError(f"These files are over {MAX_BYTES // 2**20} MB together.")
        while name in seen:  # two files with one name would overwrite each other
            name = f"{a.pk.hex[:6]}-{name}"
        seen.add(name)
        blobs.append((a, name, data))
    hold = None
    if isinstance(run.key, LabAIKey):  # the side request counts against the cap like a turn
        try:
            estimate = {"input_tokens": 2000, "output_tokens": SIDE_MAX_TOKENS}
            run.key, hold = lab_keys.reserve(run.key, estimate, run.conv.model)
        except lab_keys.Unavailable as exc:
            raise tools.ToolError(exc.message) from None
    uploaded, loaded = [], False  # uploaded: (file, Files API id)
    try:
        client = claude._client(run.key.api_key())
        for a, name, data in blobs:
            uploaded.append((a, client.files.upload(file=(name, data)).id))
        resp = _place(client, run, [i for _a, i in uploaded], container_for(run.conv, run.key))
        loaded = True
    except Exception as exc:
        raise tools.ToolError(claude.translate(exc).message) from None
    finally:
        try:
            for (
                a,
                file_id,
            ) in uploaded:  # the container has its copy; nothing stays in the Files API
                try:
                    client.files.delete(file_id)
                except Exception:
                    log.warning("could not delete an uploaded code input")
                # the bytes left the server, so it is recorded even when the load then failed
                record(
                    AuditAction.ATTACHMENT_DOWNLOADED,
                    actor=ctx.user,
                    lab=lab,
                    target=a,
                    request=ctx.request,
                    metadata={
                        "via": ctx.via,
                        "client": ctx.client,
                        "for": "code_execution",
                        "loaded": loaded,
                    },
                )
            if isinstance(run.key, LabAIKey) and loaded:
                usage = claude._usage(resp)
                lab_keys.record_usage(run.key, ctx.user, usage, resp.model, run.conv.model)
        finally:
            if hold is not None:  # the real cost is recorded by now (or the load failed)
                hold.delete()
    container = getattr(resp.container, "id", None) if resp.container else None
    if not container:
        raise tools.ToolError("The files could not be loaded. Try again.")
    keep_container(run.conv, run.key, container)
    state = run.conv.code_exec
    state["inputs"] = list(dict.fromkeys(state.get("inputs", []) + [str(a.pk) for a in files]))
    _store(run.conv)
    paths = claude.text_of([b.to_dict() for b in resp.content]).strip()
    return {
        "loaded": [{"id": a.pk, "name": name} for a, name, _d in blobs],
        "paths": tools.untrusted(paths or "Find them by name with: find / -name '<name>'"),
    }


@tools.tool(
    SAVE,
    "Save results from code",
    "Save the files your code wrote to $OUTPUT_DIR into a project, with the code you ran, as an "
    "Analysis the lab sees on its Analyses page. Saved types: images (PNG, JPEG, GIF, WebP), PDF, "
    f"CSV, TSV, TXT, Markdown, JSON, Excel, Word and PowerPoint, up to "
    f"{MAX_BYTES // 2**20} MB each. Pass `files` (file names) to save only some. Needs "
    "permission to edit the project's content; the person approves it in the app.",
    required=("lab_id", "project_id", "title"),
    write=True,
    in_app=True,
    lab_id=tools.LAB,
    project_id=tools.PROJECT,
    title={"type": "string", "maxLength": 300, "_min": 1, "description": "Analysis title."},
    summary={"type": "string", "maxLength": 4000, "description": "What it shows, briefly."},
    files={
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 20,
        "description": "Names of files in $OUTPUT_DIR. Default: every file not saved yet.",
    },
)
def save_analysis_outputs(ctx, lab_id, project_id, title, summary="", files=None):
    # ponytail: runs inside tools.call's transaction, downloads included (like the upload link's
    # save); move the downloads before it if outputs get large or slow.
    run = _run(ctx)
    conv = run.conv
    lab = tools._lab(ctx, lab_id)
    p = tools._get(ctx, lab, Project, project_id, "project", deleted_at__isnull=True)
    tools._require_edit(ctx, p)
    container_for(conv, run.key)  # drops outputs of a file flagged since the code ran
    picked = pending(conv, files)
    if not picked:
        raise tools.ToolError("There are no new files from your code to save.")
    client = claude._client(run.key.api_key())
    saved, skipped = [], []
    for file_id, out in picked:
        name = out["name"]
        ext = posixpath.splitext(name)[1].lower()
        if ext not in OUTPUT_TYPES:
            skipped.append({"name": name, "reason": "This type of file cannot be saved."})
            continue
        if out["size"] > MAX_BYTES:
            skipped.append({"name": name, "reason": "The file is too large."})
            continue
        try:
            data = client.files.download(file_id).read()  # size was checked from its metadata
        except Exception as exc:
            raise tools.ToolError(claude.translate(exc).message) from None
        if len(data) > MAX_BYTES:
            skipped.append({"name": name, "reason": "The file is too large."})
            continue
        upload = SimpleUploadedFile(name, data, OUTPUT_TYPES[ext])
        saved.append(
            (
                file_id,
                out,
                document_services.upload_attachment(
                    user=ctx.user, file=upload, project=p, request=ctx.request, source="link"
                ),
            )
        )
    if not saved:
        raise tools.ToolError(
            "None of these files can be saved: "
            + "; ".join(f"{s['name']}: {s['reason']}" for s in skipped)
        )
    code = _code_since(conv, conv.code_exec.get("saved_seq", 0))
    code_file = document_services.upload_attachment(
        user=ctx.user,
        file=SimpleUploadedFile("analysis-code.txt", code.encode(), "text/plain"),
        project=p,
        request=ctx.request,
        source="link",
    )
    # only inputs of this project: the Analysis is readable by everyone who can see it
    inputs = privacy.ai_visible(Attachment.objects.for_lab(lab)).filter(
        pk__in=conv.code_exec.get("inputs", []), project=p, deleted_at__isnull=True
    )
    description = "\n\n".join(
        x
        for x in (
            summary,
            "Run by Claude in the in-app assistant.",
            (
                "Input files: " + ", ".join(sorted(a.original_filename for a in inputs))
                if inputs
                else ""
            ),
        )
        if x
    )
    analysis = provenance_services.create(
        "analysis",
        project=p,
        user=ctx.user,
        data={"title": title, "description": description, "code_attachment": code_file.pk},
        request=ctx.request,
    )
    provenance_services.create(
        "result",
        project=p,
        user=ctx.user,
        data={
            "title": title,
            "summary": summary,
            "analysis": analysis.pk,
            "attachments": [a.pk for _f, _o, a in saved],
        },
        request=ctx.request,
    )
    for _f, out, a in saved:
        out.update(attachment=str(a.pk), project=str(p.pk), analysis=str(analysis.pk))
    conv.code_exec["saved_seq"] = conv.messages.order_by("-seq").values_list("seq", flat=True)[0]
    _store(conv)
    # the copies in the Files API are no longer needed (after the save is committed)
    done = [f for f, _o, _a in saved]
    transaction.on_commit(lambda: _delete_files(run.key, done))
    tools._audit_write(ctx, lab, SAVE, analysis)
    base = f"/labs/{lab.pk}/projects/{p.pk}"
    return {
        "analysis": {
            "id": analysis.pk,
            "title": analysis.title,
            "url": tools._url(f"{base}/workflow/analysis/analyses/{analysis.pk}"),
        },
        "saved": [{"id": a.pk, "name": a.original_filename} for _f, _o, a in saved],
        "skipped": skipped,
        "url": tools._url(f"{base}/documents"),
    }


def _code_since(conv, seq) -> str:
    """Every code step Claude ran after `seq`, in order, as one text file."""
    steps = [
        code
        for m in conv.messages.filter(seq__gt=seq, role=Role.ASSISTANT, in_context=True)
        for b in m.content
        if b.get("type") == "server_tool_use"
        for _title, code in [_code_of(b)]
    ]
    return "\n\n".join(steps) or "(no code was recorded)"
