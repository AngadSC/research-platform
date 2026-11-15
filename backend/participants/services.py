"""Participant registry rules. Every change writes an audit event and a registry event; neither
ever holds a note, a link or free text (only field names, statuses and ids)."""

import re
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can
from documents.services import Conflict
from participants import identifiers
from participants.models import (
    REASON_KIND,
    CellStatus,
    CellTask,
    Component,
    ComponentFile,
    Participant,
    ParticipantComponent,
    ParticipantEvent,
    Provider,
    StatusReason,
)
from participants.serializers import TEXT_FIELDS

DEFAULT_REASONS = (
    ("Did not attend", "missing"),
    ("Recording failure", "missing"),
    ("Translator pending", "missing"),
    ("Consent not on file", "missing"),
    ("Withdrew", "excluded"),
    ("Protocol exclusion", "excluded"),
    ("Duplicate", "excluded"),
    ("Other", "missing"),
    ("Other", "excluded"),
    ("Not part of this study arm", "not_applicable"),
    ("Other", "not_applicable"),
)

_HOSTS = {
    Provider.GOOGLE_DRIVE: ("drive.google.com", "docs.google.com"),
    Provider.ONEDRIVE: ("onedrive.live.com", "1drv.ms", "sharepoint.com"),
    Provider.DROPBOX: ("dropbox.com",),
    Provider.BOX: ("box.com",),
    Provider.GITHUB: ("github.com",),
}
_GOOGLE_ID = re.compile(r"/(?:d|folders)/([A-Za-z0-9_-]{10,})")


# ---------------------------------------------------------------- identifier guard


def guard(*, lab, actor, data: dict, request=None, code_fields=("code",)) -> None:
    """Refuse a direct identifier before anything is saved. Runs outside the write's transaction
    so the audit event survives the refusal; it names the field, never the value."""
    errors = {}
    for field in code_fields:
        value = data.get(field)
        if isinstance(value, str) and (problem := identifiers.code_problem(value.strip())):
            errors[field] = problem
    for field in TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and (problem := identifiers.free_text_problem(value)):
            errors[field] = (
                f"This looks like {problem}. Coded IDs only: remove it and use a code instead."
            )
    for item in data.get("applies_to_groups") or []:
        if identifiers.free_text_problem(item):
            errors["applies_to_groups"] = "A group name cannot hold contact details or a date."
    if errors:
        record(
            AuditAction.PARTICIPANT_IDENTIFIER_BLOCKED,
            actor=actor,
            lab=lab,
            request=request,
            metadata={"fields": sorted(errors)},
        )
        raise ValidationError(errors)


# ---------------------------------------------------------------- reasons


def seed_reasons(lab) -> None:
    if StatusReason.objects.for_lab(lab).exists():
        return
    for label, kind in DEFAULT_REASONS:
        StatusReason.objects.for_lab(lab).get_or_create(
            label=label, kind=kind, defaults={"lab": lab}
        )


@transaction.atomic
def save_reason(lab, *, user, data, reason=None, request=None):
    values = dict(data)
    try:
        with transaction.atomic():
            if reason is None:
                reason = StatusReason.objects.create(lab=lab, **values)
            else:
                for key, value in values.items():
                    setattr(reason, key, value)
                reason.save()
    except IntegrityError as exc:
        raise ValidationError({"label": "That reason already exists."}) from exc
    record(
        AuditAction.PARTICIPANT_REASON_CHANGED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"fields": sorted(values)},
    )
    return reason


# ---------------------------------------------------------------- events


def _event(participant, actor, action, *, component=None, old="", new=""):
    ParticipantEvent.objects.create(
        lab=participant.lab,
        project=participant.project,
        participant=participant,
        component=component,
        actor=actor,
        action=action,
        from_value=str(old or "")[:100],
        to_value=str(new or "")[:100],
    )


# ---------------------------------------------------------------- participants


@transaction.atomic
def create_participants(project, *, user, rows, request=None):
    """Add coded participants. A code already in the project is a conflict, not an overwrite."""
    seen = set()
    for row in rows:
        code = row["code"].strip()
        if code in seen:
            raise ValidationError({"code": "The same code appears twice in this list."})
        seen.add(code)
    existing = set(
        Participant.objects.for_lab(project.lab)
        .filter(project=project, code__in=seen)
        .values_list("code", flat=True)
    )
    if existing:
        raise Conflict(f"{len(existing)} of these codes already exist in this project.")
    made = []
    for row in rows:
        row = {**row, "code": row["code"].strip()}
        p = Participant.objects.create(lab=project.lab, project=project, created_by=user, **row)
        _event(p, user, "created")
        made.append(p)
    record(
        AuditAction.PARTICIPANT_CREATED,
        actor=user,
        lab=project.lab,
        target=made[0] if len(made) == 1 else project,
        request=request,
        metadata={"count": len(made)},
    )
    return made


@transaction.atomic
def update_participant(participant, *, user, data, request=None):
    changed = []
    for key, value in data.items():
        if key == "code":
            value = value.strip()
        if getattr(participant, key) != value:
            if key == "code" and (
                Participant.objects.for_lab(participant.lab)
                .filter(project=participant.project, code=value)
                .exclude(pk=participant.pk)
                .exists()
            ):
                raise Conflict("That code is already used in this project.")
            if key == "enrolment_status":
                _event(
                    participant,
                    user,
                    "enrolment_status",
                    old=participant.enrolment_status,
                    new=value,
                )
            setattr(participant, key, value)
            changed.append(key)
    if changed:
        participant.save()
        record(
            AuditAction.PARTICIPANT_UPDATED,
            actor=user,
            lab=participant.lab,
            target=participant,
            request=request,
            metadata={"fields": sorted(changed)},
        )
    return participant


@transaction.atomic
def set_archived(participant, archived: bool, *, user, request=None):
    """Archive or restore. Participants are never hard-deleted from the registry (retention)."""
    if archived == (participant.archived_at is not None):
        return participant
    participant.archived_at = timezone.now() if archived else None
    participant.save(update_fields=["archived_at", "updated_at"])
    _event(participant, user, "archived" if archived else "restored")
    record(
        AuditAction.PARTICIPANT_ARCHIVED if archived else AuditAction.PARTICIPANT_RESTORED,
        actor=user,
        lab=participant.lab,
        target=participant,
        request=request,
    )
    return participant


# ---------------------------------------------------------------- components


def _unique_key(project, base):
    base = slugify(base)[:50] or "component"
    taken = set(
        Component.objects.for_lab(project.lab)
        .filter(project=project, key__startswith=base)
        .values_list("key", flat=True)
    )
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    return key


@transaction.atomic
def create_component(project, *, user, data, request=None):
    values = dict(data)
    if values.get("key"):
        if (
            Component.objects.for_lab(project.lab)
            .filter(project=project, key=values["key"])
            .exists()
        ):
            raise Conflict("A column with that key already exists.")
    else:
        values["key"] = _unique_key(project, values["name"])
    c = Component.objects.create(lab=project.lab, project=project, **values)
    record(
        AuditAction.PARTICIPANT_COMPONENT_CREATED,
        actor=user,
        lab=project.lab,
        target=c,
        request=request,
    )
    return c


@transaction.atomic
def update_component(component, *, user, data, request=None):
    values = dict(data)
    values.pop("key", None)  # a key is stable: links and templates refer to it
    for key, value in values.items():
        setattr(component, key, value)
    component.save()
    record(
        AuditAction.PARTICIPANT_COMPONENT_UPDATED,
        actor=user,
        lab=component.lab,
        target=component,
        request=request,
        metadata={"fields": sorted(values)},
    )
    return component


@transaction.atomic
def delete_component(component, *, user, request=None) -> int:
    """Remove a column and its cells. Returns how many cells went, so the page can say so."""
    cells = component.cells.count()
    record(
        AuditAction.PARTICIPANT_COMPONENT_DELETED,
        actor=user,
        lab=component.lab,
        target=component,
        request=request,
        metadata={"cells": cells},
    )
    component.delete()
    return cells


# ---------------------------------------------------------------- cells


_UNSET = object()


@transaction.atomic
def set_cell(participant, component, *, user, data, request=None):
    """Create or change one cell. Status changes are explicit: a link alone never moves it."""
    from core.models import User

    lab, project = participant.lab, participant.project
    if component.project_id != project.pk or component.archived_at is not None:
        raise ValidationError({"component": "Choose a column in this project."})
    cell, created = ParticipantComponent.objects.for_lab(lab).get_or_create(
        participant=participant,
        component=component,
        defaults={"lab": lab, "project": project, "updated_by": user},
    )
    old_status = cell.status
    changed = []

    def put(field, value):
        if getattr(cell, field) != value:
            setattr(cell, field, value)
            changed.append(field)

    if "status" in data:
        put("status", data["status"])
    reason = _UNSET
    if "reason" in data:
        reason = None
        if data["reason"] is not None:
            reason = StatusReason.objects.for_lab(lab).filter(pk=data["reason"]).first()
            if reason is None:
                raise ValidationError({"reason": "Choose a reason from the list."})
        put("reason", reason)
    if "owner" in data:
        owner = None
        if data["owner"] is not None:
            owner = User.objects.filter(pk=data["owner"], is_active=True).first()
            if owner is None or not can(owner, Perm.VIEW_PROJECT, project):
                raise ValidationError({"owner": "Choose someone who can see this project."})
        put("owner", owner)
    for key in ("due_date", "collected_on", "note"):
        if key in data:
            put(key, data[key])
    if "decision" in data:
        decision = None
        if data["decision"] is not None:
            from provenance.models import Decision

            decision = (
                Decision.objects.for_lab(lab).filter(project=project, pk=data["decision"]).first()
            )
            if decision is None:
                raise ValidationError({"decision": "Choose a decision from this project."})
        put("decision", decision)
    if cell.status == CellStatus.COMPLETE and (
        "status" in changed or data.get("verified") or cell.verified_at is None
    ):
        cell.verified_at = timezone.now()  # confirmed complete now; later edits get flagged
        if "status" not in changed:
            changed.append("verified")

    if cell.status != CellStatus.EXCLUDED and cell.decision_id and "decision" in changed:
        raise ValidationError({"decision": "A decision can only be linked to an Excluded cell."})
    if cell.status != CellStatus.EXCLUDED and cell.decision_id:
        put("decision", None)  # leaving Excluded drops the link
    needed = REASON_KIND.get(CellStatus(cell.status))
    if needed is None:
        if reason not in (_UNSET, None):
            raise ValidationError(
                {"reason": "A reason only applies to Missing, Not applicable or Excluded."}
            )
        put("reason", None)  # leaving those statuses clears the old explanation
    elif cell.reason is None:
        raise ValidationError({"reason": "Say why: this status needs a reason."})
    elif not cell.reason.active or cell.reason.kind != needed:
        raise ValidationError({"reason": "That reason does not fit this status."})

    if changed or created:
        cell.updated_by = user
        cell.save()
        if "status" in changed or created:
            _event(
                participant,
                user,
                "status",
                component=component,
                old="" if created else old_status,
                new=cell.status,
            )
        meta = {"fields": sorted(changed)}
        if "status" in changed:
            meta |= {"from": old_status, "to": cell.status}
        record(
            AuditAction.PARTICIPANT_CELL_CHANGED,
            actor=user,
            lab=lab,
            target=cell,
            request=request,
            metadata=meta,
        )
    return cell


# ---------------------------------------------------------------- links


def provider_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for provider, hosts in _HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return provider
    return Provider.OTHER


@transaction.atomic
def add_file(cell, *, user, data, request=None):
    url = data["url"]
    if urlparse(url).scheme not in ("http", "https"):
        raise ValidationError({"url": "Use a web address (https://...)."})
    match = _GOOGLE_ID.search(url)
    f = ComponentFile.objects.create(
        lab=cell.lab,
        project=cell.project,
        cell=cell,
        provider=provider_of(url),
        external_id=match.group(1) if match else "",
        added_by=user,
        **data,
    )
    record(
        AuditAction.PARTICIPANT_FILE_ADDED,
        actor=user,
        lab=cell.lab,
        target=f,
        request=request,
        metadata={"provider": f.provider},
    )
    return f


@transaction.atomic
def update_file(f, *, user, data, request=None):
    values = dict(data)
    if "url" in values:
        match = _GOOGLE_ID.search(values["url"])
        values["provider"] = provider_of(values["url"])
        values["external_id"] = match.group(1) if match else ""
        values["link_state"] = values.get("link_state", "unchecked")
    for key, value in values.items():
        setattr(f, key, value)
    f.save()
    record(
        AuditAction.PARTICIPANT_FILE_CHANGED,
        actor=user,
        lab=f.lab,
        target=f,
        request=request,
        metadata={"fields": sorted(values)},
    )
    return f


@transaction.atomic
def remove_file(f, *, user, request=None) -> None:
    record(AuditAction.PARTICIPANT_FILE_REMOVED, actor=user, lab=f.lab, target=f, request=request)
    f.delete()


# ---------------------------------------------------------------- link health


def link_health(project) -> dict:
    """Problem links, links not checked yet, and cells edited since they were confirmed."""
    files = list(
        ComponentFile.objects.for_lab(project.lab)
        .filter(project=project)
        .select_related("cell__participant", "cell__component")
    )
    problems = [f for f in files if f.link_state in ("moved", "no_access", "not_found")]
    changed = [
        c
        for c in ParticipantComponent.objects.for_lab(project.lab)
        .filter(project=project, status=CellStatus.COMPLETE, verified_at__isnull=False)
        .prefetch_related("files")
        .select_related("participant", "component")
        if any(
            f.last_modified_remote and f.last_modified_remote > c.verified_at for f in c.files.all()
        )
    ]
    return {
        "counts": {
            "total": len(files),
            "ok": sum(f.link_state == "ok" for f in files),
            "unchecked": sum(f.link_state == "unchecked" for f in files),
            "problems": len(problems),
            "changed_since_verified": len(changed),
        },
        "problems": [
            {
                "file": str(f.pk),
                "cell": str(f.cell_id),
                "participant": f.cell.participant.code,
                "component": f.cell.component.name,
                "title": f.title,
                "url": f.url,
                "state": f.link_state,
            }
            for f in problems
        ],
        "changed": [
            {"cell": str(c.pk), "participant": c.participant.code, "component": c.component.name}
            for c in changed
        ],
    }


def refresh_links(project, user, *, request=None) -> dict:
    """Ask Google Drive (as the requesting person) about each linked Google file: title, last
    edited, and whether it can still be reached. Reads metadata only; changes no status."""
    from integrations import services as integration_services
    from integrations.http import IntegrationError
    from integrations.providers import google_drive

    account = integration_services.active_account_or_404(project.lab, user, google_drive.PROVIDER)
    checked = problems = 0
    qs = ComponentFile.objects.for_lab(project.lab).filter(project=project).exclude(external_id="")
    for f in qs[:200]:
        try:
            meta = google_drive.fetch_item(account, f.external_id)
        except IntegrationError:
            continue  # leave as it was: a throttled check says nothing about the file
        checked += 1
        f.last_checked_at = timezone.now()
        if meta is None:
            f.link_state = "not_found"
            problems += 1
        else:
            f.link_state = "ok"
            f.title = f.title or meta["title"][:300]
            f.mime_type = meta["mime_type"][:100]
            f.last_modified_remote = meta["modified_at"]
        f.save()
    record(
        AuditAction.PARTICIPANT_LINKS_CHECKED,
        actor=user,
        lab=project.lab,
        request=request,
        metadata={"checked": checked, "problems": problems},
    )
    return {"checked": checked, "problems": problems}


# ---------------------------------------------------------------- tasks from gaps

_VERBS = {
    "transcript": "Transcribe",
    "translation": "Translate",
    "scoring": "Score",
    "questionnaire": "Collect questionnaire for",
    "consent": "Get consent for",
    "session": "Collect",
}
_OPEN_STATUSES = (CellStatus.NOT_STARTED, CellStatus.IN_PROGRESS, CellStatus.MISSING)


@transaction.atomic
def create_tasks(project, user, *, pairs, mode, assignee=None, due_date=None, request=None):
    """One task per cell, per participant, or per column, linked back to the cells. A cell that
    already has an open task is left alone, so asking twice never doubles the work."""
    from projects import services as project_services
    from projects.models import TaskStatus

    cells = []
    for participant_id, component_id in pairs:
        p = (
            Participant.objects.for_lab(project.lab)
            .filter(project=project, pk=participant_id)
            .first()
        )
        c = Component.objects.for_lab(project.lab).filter(project=project, pk=component_id).first()
        if p is None or c is None:
            raise ValidationError({"cells": "Choose cells in this project."})
        cells.append(set_cell(p, c, user=user, data={}, request=request))
    open_ids = set(
        CellTask.objects.for_lab(project.lab)
        .filter(cell__in=cells)
        .exclude(task__status=TaskStatus.DONE)
        .values_list("cell_id", flat=True)
    )
    todo = [c for c in cells if c.pk not in open_ids and c.status in _OPEN_STATUSES]
    skipped = len(cells) - len(todo)
    groups: dict[object, list] = {}
    for c in todo:
        key = {"cell": c.pk, "participant": c.participant_id, "component": c.component_id}[mode]
        groups.setdefault(key, []).append(c)
    base = f"/labs/{project.lab_id}/projects/{project.pk}/participants"
    made = []
    for group in groups.values():
        first = group[0]
        verb = _VERBS.get(first.component.category, "Complete")
        if mode == "cell":
            title = f"{verb} {first.participant.code}, {first.component.name}"
            body = f"{base}/{first.participant_id}"
        elif mode == "participant":
            title = (
                f"Finish {first.participant.code}: {len(group)} item{'s' if len(group) > 1 else ''}"
            )
            body = (
                "\n".join(f"- {c.component.name}" for c in group)
                + f"\n\n{base}/{first.participant_id}"
            )
        else:
            noun = "participants" if len(group) > 1 else "participant"
            title = f"{verb} {first.component.name} for {len(group)} {noun}"
            body = "\n".join(f"- {c.participant.code}" for c in group) + f"\n\n{base}"
        task = project_services.create_task(
            project=project,
            by=user,
            data={
                "title": title[:300],
                "description": body,
                **({"assignee": assignee} if assignee else {}),
                **({"due_date": due_date} if due_date else {}),
            },
        )
        for c in group:
            CellTask.objects.create(lab=project.lab, project=project, cell=c, task=task)
        made.append(task)
    record(
        AuditAction.PARTICIPANT_TASKS_CREATED,
        actor=user,
        lab=project.lab,
        request=request,
        metadata={"tasks": len(made), "cells": len(todo), "skipped": skipped, "mode": mode},
    )
    return made, skipped
