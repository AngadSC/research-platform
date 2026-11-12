"""Lab-wide search (D93). Candidates come only from `scope()` (visible_to), and every hit passes
`can()` again before it is returned (ARCHITECTURE section 3, "Future search and AI").

Postgres full-text search (websearch syntax) OR a plain `icontains`, so a half-typed word still
matches; SQLite gets `icontains` only. ponytail: no GIN index, the vector is built per query;
add an indexed `SearchVectorField` if a lab grows past tens of thousands of rows per type."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from django.db import connection
from django.db.models import Q

from assistant.privacy import ai_visible
from core.permissions import Perm, can, scope
from documents.models import Document
from documents.services import lab_documents
from ethics.models import EthicsApproval
from integrations.models import ExternalLink
from papers.models import Paper, PaperNote
from projects.models import Project, Task
from provenance.models import (
    Analysis,
    DatasetRecord,
    Decision,
    FundingRecord,
    ManuscriptLink,
    Result,
    ReviewItem,
)

PER_TYPE = 8
MAX_TOTAL = 40
MIN_Q, MAX_Q = 2, 100


@dataclass(frozen=True)
class Spec:
    type: str
    model: type
    title: str  # title field
    text: tuple[str, ...]  # other searchable fields; the snippet is taken from these
    url: Callable  # obj -> SPA route
    perm: Perm = Perm.VIEW_PROJECT
    deleted: bool = False  # has a soft-delete column
    label: Callable | None = None  # obj -> hit title, when `title` is a path across a relation


def _p(o):
    return f"/labs/{o.lab_id}/projects/{o.project_id}"


def _r(section, kind):
    """D132: records live at /workflow/<section>/<kind>/<id> (the old /research URLs redirect)."""
    return lambda o: f"{_p(o)}/workflow/{section}/{kind}/{o.pk}"


def _w(tab):
    return lambda o: f"{_p(o)}/workflow/{tab}"


SPECS = [
    Spec(
        "project", Project, "name", ("description",), lambda o: f"/labs/{o.lab_id}/projects/{o.pk}"
    ),
    Spec("task", Task, "title", ("description",), lambda o: f"{_p(o)}/tasks"),
    Spec(
        "document",
        Document,
        "title",
        ("search_text",),
        lambda o: (
            f"{_p(o)}/documents/{o.pk}" if o.project_id else f"/labs/{o.lab_id}/documents/{o.pk}"
        ),
        deleted=True,
    ),
    Spec("dataset", DatasetRecord, "name", (), _r("data", "datasets")),
    Spec("analysis", Analysis, "title", ("description",), _r("analysis", "analyses")),
    Spec("result", Result, "title", ("summary",), _r("analysis", "results")),
    Spec("decision", Decision, "title", ("rationale",), _r("review", "decisions")),
    Spec("manuscript", ManuscriptLink, "title", (), _r("manuscript", "manuscripts")),
    Spec(  # D226: PIs only; amounts are neither searched nor shown
        "funding",
        FundingRecord,
        "funder",
        ("program", "award_number"),
        _w("funding"),
        perm=Perm.ACCESS_FUNDING,
    ),
    Spec("review", ReviewItem, "title", ("notes",), _w("review")),
    Spec(
        "ethics",
        EthicsApproval,
        "title",
        ("approval_number", "board"),
        lambda o: f"/labs/{o.lab_id}/ethics/{o.pk}",
        perm=Perm.VIEW_ETHICS,
        deleted=True,
    ),
    Spec("link", ExternalLink, "title", (), _p),
    Spec(
        "paper",
        Paper,
        "title",
        ("venue", "abstract"),
        lambda o: f"/labs/{o.lab_id}/papers/{o.pk}",
        perm=Perm.VIEW_LAB,
    ),
    Spec(
        "paper_note",
        PaperNote,
        "paper__title",
        ("body",),
        lambda o: f"/labs/{o.lab_id}/papers/{o.paper_id}",
        perm=Perm.VIEW_LAB,
        label=lambda o: f"Note on {o.paper.title}",
    ),
]
TYPES = {s.type: s for s in SPECS}


def match(qs, fields, q):
    cond = Q()
    for f in fields:
        cond |= Q(**{f"{f}__icontains": q})
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchVector

        qs = qs.annotate(_sv=SearchVector(*fields, config="english"))
        cond |= Q(_sv=SearchQuery(q, config="english", search_type="websearch"))
    return qs.filter(cond)


def _snippet(obj, spec, q) -> str:
    """Text around the first match in the type's own text fields, else its start."""
    for field in spec.text:
        text = re.sub(r"\s+", " ", str(getattr(obj, field) or "")).strip()
        if not text:
            continue
        if spec.type == "ethics":  # short identifying fields: show them together
            return " - ".join(str(getattr(obj, f)) for f in spec.text)
        hit = re.search("|".join(map(re.escape, q.split())), text, re.I)
        start = max(0, (hit.start() if hit else 0) - 40)
        piece = text[start : start + 140]
        return ("..." if start else "") + piece + ("..." if start + 140 < len(text) else "")
    return ""


def search(user, lab, q: str, types=None, for_ai=False) -> list[dict]:
    """`for_ai` leaves out items marked "Contains participant data" (assistant/privacy.py)."""
    q = " ".join(q.split())[:MAX_Q]
    if len(q) < MIN_Q:
        return []
    hits: list[dict] = []
    for spec in SPECS:
        if types and spec.type not in types:
            continue
        qs = scope(spec.model, user, lab)
        if spec.model is Document:  # D233: lab-wide documents have no project for scope() to check
            qs = qs | lab_documents(lab)
        if spec.deleted:
            qs = qs.filter(deleted_at__isnull=True)
        if for_ai:
            qs = ai_visible(qs)
        if hasattr(spec.model, "project"):
            qs = qs.select_related("project")
        qs = match(qs, (spec.title, *spec.text), q).order_by("-updated_at", "pk")
        for obj in qs[:PER_TYPE]:
            if not can(user, spec.perm, obj):
                continue
            project = obj if spec.type == "project" else getattr(obj, "project", None)
            hits.append(
                {
                    "type": spec.type,
                    "id": obj.pk,
                    "title": spec.label(obj) if spec.label else getattr(obj, spec.title),
                    "snippet": _snippet(obj, spec, q),
                    "project": {"id": project.pk, "name": project.name} if project else None,
                    "url": spec.url(obj),
                }
            )
    return hits[:MAX_TOTAL]
