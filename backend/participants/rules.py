"""Inclusion rules, locked analysis sets and the participant flow summary.

A rule says who counts: these columns Complete, these groups, not these enrolment statuses.
Locking freezes the participant list and, for each, the status and link versions (title and
last-modified date) of the columns the rule needs. Later changes never alter a locked set; they
are reported next to it. The flow summary is counts only, with small groups flagged."""

import datetime
from collections import Counter

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from documents.services import Conflict
from participants.models import (
    AnalysisSet,
    CellStatus,
    Component,
    EnrolmentStatus,
    InclusionRule,
    Participant,
    ParticipantComponent,
)

SMALL_CELL = 5
DEFAULT_EXCLUDE = [EnrolmentStatus.WITHDRAWN, EnrolmentStatus.INELIGIBLE]


def _spec(spec: dict | None) -> dict:
    spec = spec or {}
    return {
        "requires": list(dict.fromkeys(spec.get("requires", []))),
        "groups": list(dict.fromkeys(spec.get("groups", []))),
        "exclude_enrolment": list(spec.get("exclude_enrolment", DEFAULT_EXCLUDE)),
    }


@transaction.atomic
def save_rule(project, user, *, data, rule=None, request=None):
    values = dict(data)
    spec = _spec(values.pop("spec", None) if "spec" in values else (rule.spec if rule else None))
    keys = set(
        Component.objects.for_lab(project.lab)
        .filter(project=project, archived_at__isnull=True)
        .values_list("key", flat=True)
    )
    unknown = [k for k in spec["requires"] if k not in keys]
    if unknown:
        raise ValidationError({"spec": "One of the required columns does not exist."})
    try:
        with transaction.atomic():
            if rule is None:
                rule = InclusionRule.objects.create(
                    lab=project.lab, project=project, created_by=user, spec=spec, **values
                )
            else:
                if spec != rule.spec:  # a changed definition is a new version; the old one is kept
                    rule.history = [
                        *rule.history,
                        {
                            "version": rule.version,
                            "spec": rule.spec,
                            "at": timezone.now().isoformat(),
                        },
                    ]
                    rule.version += 1
                    rule.spec = spec
                for key, value in values.items():
                    setattr(rule, key, value)
                rule.save()
    except IntegrityError as exc:
        raise ValidationError({"name": "A rule with that name already exists."}) from exc
    record(
        AuditAction.PARTICIPANT_RULE_SAVED,
        actor=user,
        lab=project.lab,
        target=rule,
        request=request,
        metadata={"version": rule.version},
    )
    return rule


@transaction.atomic
def archive_rule(rule, user, request=None):
    rule.archived_at = timezone.now()
    rule.save(update_fields=["archived_at", "updated_at"])
    record(
        AuditAction.PARTICIPANT_RULE_ARCHIVED,
        actor=user,
        lab=rule.lab,
        target=rule,
        request=request,
    )


def _grid(project):
    people = list(
        Participant.objects.for_lab(project.lab).filter(project=project, archived_at__isnull=True)
    )
    columns = {
        c.key: c
        for c in Component.objects.for_lab(project.lab).filter(
            project=project, archived_at__isnull=True
        )
    }
    cells = {}
    for c in (
        ParticipantComponent.objects.for_lab(project.lab)
        .filter(project=project)
        .prefetch_related("files")
    ):
        cells[(c.participant_id, c.component_id)] = c
    return people, columns, cells


def evaluate(project, spec: dict) -> dict:
    """Who is in, who is one step away (and what blocks them), and how many are out."""
    spec = _spec(spec)
    people, columns, cells = _grid(project)
    eligible, one_away, out = [], [], Counter()
    for p in people:
        if spec["groups"] and p.group not in spec["groups"]:
            out["group"] += 1
            continue
        if p.enrolment_status in spec["exclude_enrolment"]:
            out["enrolment"] += 1
            continue
        blocking = []
        for key in spec["requires"]:
            col = columns[key]
            cell = cells.get((p.pk, col.pk))
            status = cell.status if cell else CellStatus.NOT_STARTED
            if status != CellStatus.COMPLETE:
                blocking.append({"column": col.name, "status": status})
        if not blocking:
            eligible.append(p)
        elif len(blocking) == 1:
            one_away.append({"code": p.code, "blocking": blocking})
        else:
            out["blocked"] += 1
    return {
        "eligible": sorted(p.code for p in eligible),
        "one_away": sorted(one_away, key=lambda x: x["code"]),
        "not_eligible": sum(out.values()),
        "not_eligible_why": dict(out),
        "_people": eligible,
    }


def _snapshot(project, people, spec):
    _, columns, cells = _grid(project)
    snap = {}
    for p in people:
        row = {}
        for key in spec["requires"]:
            col = columns[key]
            cell = cells.get((p.pk, col.pk))
            row[key] = {
                "status": cell.status if cell else "not_started",
                "files": sorted(
                    (
                        {
                            "title": f.title,
                            "modified": (
                                f.last_modified_remote.isoformat() if f.last_modified_remote else ""
                            ),
                        }
                        for f in (cell.files.all() if cell else [])
                    ),
                    key=lambda f: (f["title"], f["modified"]),
                ),
            }
        snap[str(p.pk)] = row
    return snap


@transaction.atomic
def lock_set(project, user, *, rule, name, supersedes=None, request=None):
    result = evaluate(project, rule.spec)
    people = result["_people"]
    if not people:
        raise ValidationError(
            {"rule": "No participants meet this rule yet, so there is nothing to lock."}
        )
    s = AnalysisSet.objects.create(
        lab=project.lab,
        project=project,
        name=name,
        rule=rule,
        rule_version=rule.version,
        participant_ids=[str(p.pk) for p in people],
        snapshot=_snapshot(project, people, _spec(rule.spec)),
        created_by=user,
        supersedes=supersedes,
    )
    record(
        AuditAction.PARTICIPANT_SET_LOCKED,
        actor=user,
        lab=project.lab,
        target=s,
        request=request,
        metadata={"participants": len(people), "rule_version": rule.version},
    )
    return s


def set_changes(project, s: AnalysisSet) -> list[dict]:
    """What differs now from what was locked. A locked set itself never changes."""
    spec = _spec(s.rule.spec) if s.rule else {"requires": []}
    keys = {k for row in s.snapshot.values() for k in row}
    spec = {**spec, "requires": sorted(keys)}
    people = list(
        Participant.objects.for_lab(project.lab).filter(project=project, pk__in=s.participant_ids)
    )
    current = _snapshot(project, people, spec)
    codes = {str(p.pk): p.code for p in people}
    changes = []
    for pid in s.participant_ids:
        if pid not in codes:
            changes.append(
                {"participant": "(removed)", "column": "", "kind": "participant removed"}
            )
            continue
        for key, then in s.snapshot.get(pid, {}).items():
            now = current.get(pid, {}).get(key)
            if now != then:
                kind = "status" if now and now["status"] != then["status"] else "linked files"
                changes.append({"participant": codes[pid], "column": key, "kind": kind})
    return changes


@transaction.atomic
def new_version(project, user, s: AnalysisSet, request=None):
    """Lock the rule again as a new set that points back at the old one."""
    if s.rule is None:
        raise Conflict("This set has no rule to build a new version from.")
    stem = s.name.split(" (v")[0]
    count = (
        AnalysisSet.objects.for_lab(project.lab)
        .filter(project=project, name__startswith=stem)
        .count()
    )
    return lock_set(
        project, user, rule=s.rule, name=f"{stem} (v{count + 1})", supersedes=s, request=request
    )


# ---------------------------------------------------------------- participant flow


def flow(project, s: AnalysisSet | None = None) -> dict:
    people = list(Participant.objects.for_lab(project.lab).filter(project=project))
    active = [p for p in people if p.archived_at is None]
    by = Counter(p.enrolment_status for p in active)
    total = len(active)
    screened_only = by[EnrolmentStatus.SCREENED]
    enrolled = total - screened_only
    excluded_cells = (
        ParticipantComponent.objects.for_lab(project.lab)
        .filter(project=project, status=CellStatus.EXCLUDED, participant__archived_at__isnull=True)
        .select_related("reason")
    )
    reasons: dict[str, set] = {}
    for c in excluded_cells:
        reasons.setdefault(c.reason.label if c.reason else "No reason", set()).add(c.participant_id)
    analysed = len(s.participant_ids) if s else None
    groups = Counter(p.group or "No group" for p in active)

    def n(v):  # a count, with a flag when it is small enough to identify someone
        return {"count": v, "small": 0 < v < SMALL_CELL}

    out = {
        "screened": n(total),
        "enrolled": n(enrolled),
        "completed": n(by[EnrolmentStatus.COMPLETED]),
        "withdrawn": n(by[EnrolmentStatus.WITHDRAWN]),
        "ineligible": n(by[EnrolmentStatus.INELIGIBLE]),
        "excluded": [{"reason": r, **n(len(ids))} for r, ids in sorted(reasons.items())],
        "analysed": n(analysed) if analysed is not None else None,
        "groups": [{"group": g, **n(v)} for g, v in sorted(groups.items())],
        "set": s.name if s else None,
        "small_cell_limit": SMALL_CELL,
        "warning": None,
    }
    flagged = [
        k
        for k in ("screened", "enrolled", "completed", "withdrawn", "ineligible", "analysed")
        if out[k] and out[k]["small"]
    ]
    if (
        flagged
        or any(g["small"] for g in out["groups"])
        or any(e["small"] for e in out["excluded"])
    ):
        out["warning"] = (
            f"Some counts are under {SMALL_CELL}. Small groups can identify people: check your "
            "ethics protocol before reporting them."
        )
    return out


def record_export(project, user, kind: str, request=None):
    record(
        AuditAction.PARTICIPANT_FLOW_EXPORTED,
        actor=user,
        lab=project.lab,
        request=request,
        metadata={"kind": kind, "date": datetime.date.today().isoformat()},
    )
