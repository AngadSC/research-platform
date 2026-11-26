"""Read-only roll-up across the projects a person can see: the numbers behind the Home and My
work cards and the lab's Participants page. Counts and codes only; no links."""

import datetime
from collections import Counter, defaultdict

from core.permissions import visible_projects
from participants.models import CellStatus, Component, Participant, ParticipantComponent

DONE = {CellStatus.COMPLETE}
LEFT_OUT = {CellStatus.NOT_APPLICABLE, CellStatus.EXCLUDED}


def lab_overview(user, lab) -> dict:
    today = datetime.date.today()
    projects = list(visible_projects(user, lab).values("id", "name", "color"))
    ids = [p["id"] for p in projects]
    people = {
        p["id"]: p
        for p in Participant.objects.for_lab(lab)
        .filter(project_id__in=ids, archived_at__isnull=True)
        .values("id", "code", "group", "project_id")
    }
    cells = list(
        ParticipantComponent.objects.for_lab(lab)
        .filter(project_id__in=ids, participant_id__in=people)
        .values(
            "id",
            "project_id",
            "participant_id",
            "component_id",
            "status",
            "owner_id",
            "due_date",
            "updated_at",
            "reason__label",
            "component__name",
            "component__category",
            "component__archived_at",
            "component__applies_to_groups",
        )
    )
    # Same cells the project's Participants page counts: no archived columns, and no column that
    # is limited to other groups.
    cells = [
        c
        for c in cells
        if c["component__archived_at"] is None
        and (
            not c["component__applies_to_groups"]
            or people[c["participant_id"]]["group"] in c["component__applies_to_groups"]
        )
    ]
    per = defaultdict(lambda: Counter())
    by_component = defaultdict(lambda: [0, 0])
    # Percent complete counts every participant x column that applies, like the project's
    # Participants page: a cell nobody has touched yet is "not started", not absent.
    state = {(c["participant_id"], c["component_id"]): c["status"] for c in cells}
    for comp in (
        Component.objects.for_lab(lab)
        .filter(project_id__in=ids, archived_at__isnull=True)
        .values("id", "project_id", "name", "applies_to_groups")
    ):
        for pid, person in people.items():
            if person["project_id"] != comp["project_id"]:
                continue
            if comp["applies_to_groups"] and person["group"] not in comp["applies_to_groups"]:
                continue
            status = state.get((pid, comp["id"]), CellStatus.NOT_STARTED)
            if status in LEFT_OUT:
                continue
            per[comp["project_id"]]["counted"] += 1
            by_component[comp["name"]][1] += 1
            if status in DONE:
                per[comp["project_id"]]["complete"] += 1
                by_component[comp["name"]][0] += 1
    reasons: Counter = Counter()
    pending: Counter = Counter()
    mine, recent = [], []
    for c in cells:
        pr = per[c["project_id"]]
        status = c["status"]
        if status == CellStatus.MISSING:
            pr["missing"] += 1
            reasons[c["reason__label"] or "No reason"] += 1
        if status == CellStatus.NEEDS_REVIEW:
            pr["review"] += 1
        if c["due_date"] and c["due_date"] < today and status not in DONE | LEFT_OUT:
            pr["overdue"] += 1
        if c["component__category"] == "translation" and status not in DONE | LEFT_OUT:
            pending[people[c["participant_id"]]["group"] or "No group"] += 1
        if c["owner_id"] == user.pk and status not in DONE | LEFT_OUT:
            mine.append(c)
        recent.append(c)
    count_people = Counter(p["project_id"] for p in people.values())

    def row(project):
        pr = per[project["id"]]
        return {
            "id": project["id"],
            "name": project["name"],
            "color": project["color"],
            "participants": count_people[project["id"]],
            "percent": round(100 * pr["complete"] / pr["counted"]) if pr["counted"] else 0,
            "missing": pr["missing"],
            "overdue": pr["overdue"],
            "needs_review": pr["review"],
        }

    names = {p["id"]: p["name"] for p in projects}

    def item(c):
        p = people[c["participant_id"]]
        return {
            "project": c["project_id"],
            "project_name": names[c["project_id"]],
            "participant": p["code"],
            "participant_id": c["participant_id"],
            "component": c["component__name"],
            "status": c["status"],
            "due_date": c["due_date"],
            "at": c["updated_at"],
        }

    mine.sort(key=lambda c: (c["due_date"] is None, c["due_date"] or today))
    recent.sort(key=lambda c: c["updated_at"], reverse=True)
    rows = [row(p) for p in projects if count_people[p["id"]]]
    return {
        "projects": rows,
        "by_component": sorted(
            (
                {"name": n, "percent": round(100 * d / t) if t else 0, "cells": t}
                for n, (d, t) in by_component.items()
            ),
            key=lambda x: x["percent"],
        )[:12],
        "missing_by_reason": [{"reason": r, "count": n} for r, n in reasons.most_common(8)],
        "translation_pending": [{"group": g, "count": n} for g, n in pending.most_common(8)],
        "waiting_on_me": [item(c) for c in mine[:20]],
        "recent": [item(c) for c in recent[:10]],
    }
