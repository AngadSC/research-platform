"""Import participants from a sheet or CSV, and match Drive files to cells by name.

The platform reads codes, group labels, statuses and link addresses only. A column whose header
looks like a name or contact detail is refused, a code that looks like one is refused, and
nothing a row says is ever written to a log. Re-importing the same sheet updates by code and
never duplicates. A dry run does all the work inside a transaction and rolls it back."""

import csv
import io
import re

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from participants import identifiers, services
from participants.models import (
    CellStatus,
    Component,
    ComponentFile,
    ImportRun,
    Participant,
    ParticipantComponent,
)

MAX_ROWS = 1000
MAX_COLUMNS = 80
MAX_BYTES = 1_000_000
MAX_ATTENTION = 60

BLOCKED_HEADER = re.compile(
    r"\b(first|last|full|given|family|sur)?\s*name\b|e-?mail|phone|mobile|tel\b|address|"
    r"birth|dob|postal|zip|\bsin\b|health\s*card",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s,;<>\"']+")
_STATUS_WORDS = (
    (re.compile(r"^(complete|completed|done|yes|y|x|✓|✔)$", re.I), CellStatus.COMPLETE),
    (re.compile(r"^(in progress|wip|started|partial)$", re.I), CellStatus.IN_PROGRESS),
    (re.compile(r"^(needs? review|to check|review)$", re.I), CellStatus.NEEDS_REVIEW),
)
_ROLES = (
    ("translat", "translation"),
    ("transcri", "transcript"),
    ("scor", "scoring"),
    ("audio", "raw"),
    ("record", "raw"),
    ("raw", "raw"),
)


def guess_role(header: str) -> str:
    h = header.lower()
    return next((role for needle, role in _ROLES if needle in h), "other")


def guess_category(header: str) -> str:
    h = header.lower()
    for needle, cat in (
        ("translat", "translation"),
        ("transcri", "transcript"),
        ("scor", "scoring"),
        ("questionnaire", "questionnaire"),
        ("consent", "consent"),
        ("narrative", "session"),
        ("session", "session"),
    ):
        if needle in h:
            return cat
    return "other"


def read_table(text: str):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValidationError({"csv": "That file is too large to import (1 MB limit)."})
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader]
    if not rows:
        raise ValidationError({"csv": "The file is empty."})
    headers = [h.strip() for h in rows[0]]
    if len(headers) > MAX_COLUMNS:
        raise ValidationError({"csv": f"Too many columns (limit {MAX_COLUMNS})."})
    body = rows[1:]
    if len(body) > MAX_ROWS:
        raise ValidationError({"csv": f"Too many rows (limit {MAX_ROWS})."})
    return headers, body


def preview(text: str) -> dict:
    """Headers and the first rows, for the mapping step. Link-bearing cells are flagged."""
    headers, body = read_table(text)
    return {
        "headers": headers,
        "rows": [r[: len(headers)] for r in body[:10]],
        "total": len(body),
        "blocked_headers": [h for h in headers if BLOCKED_HEADER.search(h)],
        "link_columns": [
            h
            for i, h in enumerate(headers)
            if any(URL_RE.search(r[i]) for r in body[:50] if i < len(r))
        ],
    }


def _check_mapping(headers, mapping):
    def need(name, required=False):
        h = mapping.get(name)
        if not h:
            if required:
                raise ValidationError({"mapping": f"Choose the {name} column."})
            return None
        if h not in headers:
            raise ValidationError({"mapping": f"The {name} column was not found."})
        return h

    cols = {
        "code": need("code", True),
        "group": need("group"),
        "cohort": need("cohort"),
        "enrolment_status": need("enrolment_status"),
    }
    comps = []
    for item in mapping.get("components") or []:
        h = item.get("column")
        if h not in headers:
            raise ValidationError({"mapping": "A data column was not found in the file."})
        comps.append(item)
    used = [h for h in [*cols.values(), *[c["column"] for c in comps]] if h]
    bad = [h for h in used if BLOCKED_HEADER.search(h)]
    if bad:
        raise ValidationError(
            {
                "mapping": "A column that looks like a name or contact detail cannot be imported. "
                "Leave it out and use coded IDs only."
            }
        )
    if len(set(used)) != len(used):
        raise ValidationError({"mapping": "Each column can be used only once."})
    return cols, comps


def _status_and_links(text: str):
    urls = URL_RE.findall(text)
    rest = URL_RE.sub("", text).strip(" ,;")
    status = next((s for rx, s in _STATUS_WORDS if rx.match(rest)), None)
    return status, urls


@transaction.atomic
def _apply(project, user, headers, body, cols, comps, request):
    idx = {h: i for i, h in enumerate(headers)}
    get = lambda row, h: (row[idx[h]].strip() if h and idx[h] < len(row) else "")  # noqa: E731
    created, updated, skipped, links = [], [], 0, 0
    attention = []
    undo = {"participants": [], "cells": [], "files": [], "components": [], "before": {}}
    blocked_fields = set()

    columns = {}
    existing = {c.key: c for c in Component.objects.for_lab(project.lab).filter(project=project)}
    for item in comps:
        name = (item.get("name") or item["column"]).strip()
        key = slugify(name)[:60] or "column"
        col = existing.get(key)
        if col is None:
            col = Component.objects.create(
                lab=project.lab,
                project=project,
                name=name[:100],
                key=key,
                category=item.get("category") or guess_category(item["column"]),
                order=len(existing),
            )
            existing[key] = col
            undo["components"].append(str(col.pk))
        columns[item["column"]] = (col, guess_role(item["column"]))

    seen = set()
    for n, row in enumerate(body, start=2):  # row 1 is the header
        code = get(row, cols["code"])
        if not code:
            skipped += 1
            attention.append({"row": n, "message": "No participant code. Skipped."})
            continue
        if code in seen:
            skipped += 1
            attention.append(
                {"row": n, "message": "This code appears earlier in the file. Skipped."}
            )
            continue
        seen.add(code)
        problem = identifiers.code_problem(code)
        if problem:
            skipped += 1
            blocked_fields.add("code")
            attention.append({"row": n, "message": f"Code refused: {problem}"})
            continue
        group, cohort = get(row, cols["group"]), get(row, cols["cohort"])
        bad = False
        for field, value in (("group", group), ("cohort", cohort)):
            if value and identifiers.free_text_problem(value):
                blocked_fields.add(field)
                attention.append(
                    {"row": n, "message": f"The {field} value looks like a name or contact detail."}
                )
                bad = True
        if bad:
            skipped += 1
            continue
        enrol = get(row, cols["enrolment_status"]).lower().replace(" ", "")
        cell_data = []
        for header, (col, role) in columns.items():
            status, urls = _status_and_links(get(row, header))
            if status or urls:
                cell_data.append((col, role, status, urls))
        if not cell_data and not group and not cohort:
            skipped += 1
            attention.append({"row": n, "message": "No data in this row. Skipped."})
            continue

        p = Participant.objects.for_lab(project.lab).filter(project=project, code=code).first()
        if p is None:
            p = Participant.objects.create(
                lab=project.lab,
                project=project,
                created_by=user,
                code=code,
                group=group,
                cohort=cohort,
                **(
                    {"enrolment_status": enrol}
                    if enrol in dict(Participant._meta.get_field("enrolment_status").choices)
                    else {}
                ),
            )
            undo["participants"].append(str(p.pk))
            created.append(code)
        else:
            changed = False
            before = {}
            for field, value in (("group", group), ("cohort", cohort)):
                if value and not getattr(p, field):
                    before[field] = ""
                    setattr(p, field, value)
                    changed = True
            if changed:
                p.save()
                undo["before"][f"p:{p.pk}"] = before
                updated.append(code)
        for col, role, status, urls in cell_data:
            cell, made = ParticipantComponent.objects.for_lab(project.lab).get_or_create(
                participant=p,
                component=col,
                defaults={"lab": project.lab, "project": project, "updated_by": user},
            )
            touched = made
            if made:
                undo["cells"].append(str(cell.pk))
            if status and cell.status == CellStatus.NOT_STARTED:
                if not made:
                    undo["before"][f"c:{cell.pk}"] = {"status": cell.status}
                cell.status = status
                if status == CellStatus.COMPLETE:
                    cell.verified_at = timezone.now()
                cell.updated_by = user
                cell.save()
                touched = True
            have = set(cell.files.values_list("url", flat=True)) if not made else set()
            for url in urls:
                if url in have:
                    continue
                f = ComponentFile.objects.create(
                    lab=project.lab,
                    project=project,
                    cell=cell,
                    provider=services.provider_of(url),
                    url=url[:1000],
                    external_id=(
                        services._GOOGLE_ID.search(url).group(1)
                        if services._GOOGLE_ID.search(url)
                        else ""
                    ),
                    role=role,
                    added_by=user,
                )
                undo["files"].append(str(f.pk))
                links += 1
                touched = True
            if touched and not made and code not in updated and code not in created:
                updated.append(code)
    return (
        {
            "created": len(created),
            "updated": len(updated),
            "skipped": skipped,
            "links": links,
            "components_created": len(undo["components"]),
            "attention": attention[:MAX_ATTENTION],
            "attention_total": len(attention),
        },
        undo,
        blocked_fields,
    )


def run_import(project, user, *, text, mapping, dry_run, source="csv", request=None) -> dict:
    headers, body = read_table(text)
    cols, comps = _check_mapping(headers, mapping)
    with transaction.atomic():
        summary, undo, blocked = _apply(project, user, headers, body, cols, comps, request)
        if dry_run:
            transaction.set_rollback(True)  # nothing saved; the counts are still exact
        else:
            run = ImportRun.objects.create(
                lab=project.lab,
                project=project,
                created_by=user,
                source=source,
                summary={k: v for k, v in summary.items() if k != "attention"},
                undo=undo,
            )
            summary["run"] = str(run.pk)
            record(
                AuditAction.PARTICIPANT_IMPORTED,
                actor=user,
                lab=project.lab,
                target=run,
                request=request,
                metadata={k: summary[k] for k in ("created", "updated", "skipped", "links")},
            )
    if blocked:  # outside the transaction, so a dry run still leaves the trace
        record(
            AuditAction.PARTICIPANT_IDENTIFIER_BLOCKED,
            actor=user,
            lab=project.lab,
            request=request,
            metadata={"fields": sorted(blocked), "source": "import"},
        )
    summary["dry_run"] = dry_run
    return summary


@transaction.atomic
def undo_last(project, user, run, request=None):
    last = (
        ImportRun.objects.for_lab(project.lab)
        .filter(project=project, undone_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if last is None or last.pk != run.pk:
        raise services.Conflict("Only the most recent import can be undone.")
    u = run.undo
    ComponentFile.objects.for_lab(project.lab).filter(pk__in=u.get("files", [])).delete()
    ParticipantComponent.objects.for_lab(project.lab).filter(pk__in=u.get("cells", [])).delete()
    for key, before in u.get("before", {}).items():
        kind, pk = key.split(":")
        model = Participant if kind == "p" else ParticipantComponent
        model.objects.for_lab(project.lab).filter(pk=pk).update(**before)
    Participant.objects.for_lab(project.lab).filter(pk__in=u.get("participants", [])).delete()
    Component.objects.for_lab(project.lab).filter(
        pk__in=u.get("components", []), cells__isnull=True
    ).delete()
    run.undone_at = timezone.now()
    run.save(update_fields=["undone_at", "updated_at"])
    record(
        AuditAction.PARTICIPANT_IMPORT_UNDONE,
        actor=user,
        lab=project.lab,
        target=run,
        request=request,
    )
    return run


# ---------------------------------------------------------------- Drive file matching


def pattern_regex(pattern: str):
    if "{number}" not in pattern or "{component}" not in pattern:
        raise ValidationError({"pattern": "The pattern needs {number} and {component}."})
    if len(pattern) > 100:
        raise ValidationError({"pattern": "That pattern is too long."})
    out = ""
    for part in re.split(r"(\{number\}|\{component\})", pattern):
        if part == "{number}":
            out += r"(?P<number>\d+)"
        elif part == "{component}":
            out += r"(?P<component>.+?)"
        else:
            out += re.escape(part)
    return re.compile(rf"^{out}$", re.I)


def match_files(project, files, pattern: str) -> list[dict]:
    rx = pattern_regex(pattern)
    participants = list(
        Participant.objects.for_lab(project.lab).filter(project=project, archived_at__isnull=True)
    )
    by_number = {}
    for p in participants:
        digits = re.sub(r"\D", "", p.code)
        if digits:
            by_number.setdefault(int(digits), []).append(p)
    columns = list(
        Component.objects.for_lab(project.lab).filter(project=project, archived_at__isnull=True)
    )
    out = []
    for f in files[:500]:
        stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", f["name"]).strip()
        m = rx.match(stem)
        item = {**f, "participant": None, "component": None, "confidence": "none"}
        if m:
            people = by_number.get(int(m.group("number")), [])
            slug = slugify(m.group("component"))
            exact = [c for c in columns if c.key == slug or slugify(c.name) == slug]
            near = [c for c in columns if slug and (slug in c.key or c.key in slug)]
            col = exact[0] if len(exact) == 1 else (near[0] if len(near) == 1 else None)
            if len(people) == 1:
                item["participant"] = str(people[0].pk)
                item["participant_code"] = people[0].code
            if col:
                item["component"] = str(col.pk)
                item["component_name"] = col.name
            if item["participant"] and col:
                item["confidence"] = "high" if exact else "medium"
            elif item["participant"] or col:
                item["confidence"] = "low"
        out.append(item)
    return out


@transaction.atomic
def attach_matches(project, user, items, request=None) -> dict:
    done = skipped = 0
    for it in items[:500]:
        p = (
            Participant.objects.for_lab(project.lab)
            .filter(project=project, pk=it["participant"])
            .first()
        )
        c = (
            Component.objects.for_lab(project.lab)
            .filter(project=project, pk=it["component"])
            .first()
        )
        if not p or not c:
            skipped += 1
            continue
        cell = services.set_cell(p, c, user=user, data={}, request=request)
        if cell.files.filter(url=it["url"]).exists():
            skipped += 1
            continue
        services.add_file(
            cell,
            user=user,
            data={
                "url": it["url"],
                "title": (it.get("title") or "")[:300],
                "role": guess_role(c.name),
            },
            request=request,
        )
        done += 1
    record(
        AuditAction.PARTICIPANT_FILES_MATCHED,
        actor=user,
        lab=project.lab,
        request=request,
        metadata={"attached": done, "skipped": skipped},
    )
    return {"attached": done, "skipped": skipped}
