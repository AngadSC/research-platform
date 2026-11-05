"""Provenance business logic (ARCHITECTURE sections 1, 4, 5). Every link is resolved inside the
one project (D20, D31): an ID from another project or lab fails exactly like a missing ID.
Writes record their audit event in the same transaction."""

import datetime
import uuid

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from core.models import NotificationKind, User
from core.notifications import notify
from core.permissions import Perm, can, require
from documents.models import Attachment, Document
from documents.services import Conflict
from labs.models import LabMembership, LabRole
from projects.models import ProjectDeadline, Task
from provenance.models import Analysis, DatasetRecord, Decision, ManuscriptLink, Result


class Spec:
    """What a kind links to. `fks` and `m2ms` map field -> (model, must_not_be_soft_deleted);
    `users` are user FKs (must be able to view the project); `owner` defaults to the actor."""

    def __init__(self, model, created, updated, deleted, *, owner, fks=(), m2ms=(), users=()):
        self.model, self.owner = model, owner
        self.created, self.updated, self.deleted = created, updated, deleted
        self.fks, self.m2ms, self.users = dict(fks), dict(m2ms), tuple(users)


A = AuditAction
SPECS = {
    "dataset": Spec(
        DatasetRecord,
        A.DATASET_CREATED,
        A.DATASET_UPDATED,
        A.DATASET_DELETED,
        owner="created_by",
        fks={"previous_version": (DatasetRecord, False)},
        users=("controlled_by",),
    ),
    "analysis": Spec(
        Analysis,
        A.ANALYSIS_CREATED,
        A.ANALYSIS_UPDATED,
        A.ANALYSIS_DELETED,
        owner="ran_by",
        fks={"code_attachment": (Attachment, True)},
        m2ms={"datasets": (DatasetRecord, False)},
        users=("ran_by",),
    ),
    "result": Spec(
        Result,
        A.RESULT_CREATED,
        A.RESULT_UPDATED,
        A.RESULT_DELETED,
        owner="created_by",
        fks={"analysis": (Analysis, False)},
        m2ms={"attachments": (Attachment, True)},
    ),
    "decision": Spec(
        Decision,
        A.DECISION_CREATED,
        A.DECISION_UPDATED,
        A.DECISION_DELETED,
        owner="decided_by",
        m2ms={
            "supporting_documents": (Document, True),
            "supporting_attachments": (Attachment, True),
            "analyses": (Analysis, False),
            "results": (Result, False),
            "datasets": (DatasetRecord, False),
        },
        users=("decided_by",),
    ),
    "manuscript": Spec(
        ManuscriptLink,
        A.MANUSCRIPT_CREATED,
        A.MANUSCRIPT_UPDATED,
        A.MANUSCRIPT_DELETED,
        owner="created_by",
        m2ms={"results": (Result, False)},
    ),
}


def _scoped(project, model, live):
    qs = model.objects.for_lab(project.lab_id).filter(project=project)
    return qs.filter(deleted_at__isnull=True) if live else qs


def _one(project, field, model, live, pk):
    obj = _scoped(project, model, live).filter(pk=pk).first()
    if obj is None:
        raise ValidationError({field: "This item does not exist in this project."})
    return obj


def _many(project, field, model, live, ids):
    ids = set(ids)
    found = list(_scoped(project, model, live).filter(pk__in=ids))
    if len(found) != len(ids):
        raise ValidationError({field: "One or more items do not exist in this project."})
    return found


def _user(project, field, pk):
    user = User.objects.filter(pk=pk, is_active=True).first()
    if user is None or not can(user, Perm.VIEW_PROJECT, project):
        raise ValidationError({field: "This person must be able to view the project."})
    return user


def _check_analysis(obj):
    has_code = (obj.code_repo_url and obj.code_commit) or obj.code_attachment_id
    if not has_code:
        raise ValidationError(
            {"code_repo_url": "Give a repository URL and commit hash, or attach the code."}
        )


def _resolve(spec, project, data, *, actor, creating):
    """Split `data` into column values (links turned into objects) and M2M lists."""
    data = dict(data)
    m2m = {f: _many(project, f, *spec.m2ms[f], data.pop(f)) for f in spec.m2ms if f in data}
    for field, (model, live) in spec.fks.items():
        if data.get(field) is not None:
            data[field] = _one(project, field, model, live, data[field])
    for field in spec.users:
        if creating and data.get(field) is None:
            data[field] = actor  # D50: the person recording it, unless a lead says otherwise
        elif data.get(field) is not None:
            if str(data[field]) != str(actor.pk):
                require(actor, Perm.EDIT_PROJECT, project)  # D50: naming someone else
            data[field] = _user(project, field, data[field])
    if creating and data.get(spec.owner) is None:
        data[spec.owner] = actor
    return data, m2m


def _save(obj):
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:  # unique (project, name, version_label), D33
        raise ValidationError({"detail": "An item with these details already exists."}) from exc


@transaction.atomic
def create(kind, *, project, user, data, request=None):
    spec = SPECS[kind]
    values, m2m = _resolve(spec, project, data, actor=user, creating=True)
    if kind == "analysis":
        values.setdefault("ran_at", timezone.now())
    if kind == "decision":
        values.setdefault("decided_on", datetime.date.today())
    obj = spec.model(lab=project.lab, project=project, **values)
    if kind == "analysis":
        _check_analysis(obj)
    _save(obj)
    for field, items in m2m.items():
        getattr(obj, field).set(items)
    record(spec.created, actor=user, lab=project.lab, target=obj, request=request)
    return obj


@transaction.atomic
def update(kind, obj, *, user, data, request=None):
    spec = SPECS[kind]
    project = obj.project
    values, m2m = _resolve(spec, project, data, actor=user, creating=False)
    if values.get("previous_version") == obj:
        raise ValidationError({"previous_version": "A dataset cannot be its own previous version."})
    for key, value in values.items():
        setattr(obj, key, value)
    if kind == "analysis":
        _check_analysis(obj)
    _save(obj)
    for field, items in m2m.items():
        getattr(obj, field).set(items)
    record(
        spec.updated,
        actor=user,
        lab=obj.lab,
        target=obj,
        request=request,
        metadata={"fields": sorted([*values, *m2m])},
    )
    return obj


@transaction.atomic
def delete(kind, obj, *, user, request=None) -> None:
    """A dataset used by an analysis, or an analysis with results, cannot go (409, ARCH 1)."""
    spec = SPECS[kind]
    if kind == "dataset" and obj.analyses.exists():
        raise Conflict("This dataset is used by an analysis. Remove it from the analysis first.")
    record(spec.deleted, actor=user, lab=obj.lab, target=obj, request=request)
    try:
        with transaction.atomic():
            obj.delete()
    except ProtectedError as exc:
        raise Conflict("This analysis has results. Delete the results first.") from exc


# ---------------------------------------------------------------- export


def export_project(*, project, user, context, request=None) -> dict:
    """One JSON document: metadata, tasks, latest documents and provenance. No file bytes.
    Every query is scoped to `project` and its lab, so nothing from another project leaks."""
    from provenance.serializers import PLURAL, queryset

    def mine(model):
        return model.objects.for_lab(project.lab_id).filter(project=project)

    live = {"deleted_at__isnull": True}
    out = {
        "exported_at": timezone.now(),
        "project": project,
        "tasks": mine(Task).select_related("assignee", "created_by").order_by("created_at", "id"),
        "deadlines": mine(ProjectDeadline).order_by("due_date", "id"),
        "documents": mine(Document)
        .filter(**live)
        .select_related("created_by", "updated_by")
        .order_by("created_at", "id"),
        "attachments": mine(Attachment).filter(**live).select_related("uploaded_by"),
        **{PLURAL[kind]: queryset(kind, project, user) for kind in SPECS},
    }
    record(
        AuditAction.PROJECT_EXPORTED,
        actor=user,
        lab=project.lab,
        target=project,
        request=request,
        metadata={k: v.count() for k, v in out.items() if hasattr(v, "count")},
    )
    _notify_pis_of_export(project=project, user=user)
    return out


def _notify_pis_of_export(*, project, user) -> None:
    """D28: when anyone but a PI exports, every lab PI hears about it (in-app and email)."""
    lab = project.lab
    pis = [
        m.user
        for m in LabMembership.objects.for_lab(lab).filter(role=LabRole.PI).select_related("user")
    ]
    if any(pi.pk == user.pk for pi in pis):
        return
    who = user.display_name or user.email
    for pi in pis:
        notify(
            lab=lab,
            recipient=pi,
            kind=NotificationKind.PROJECT_EXPORTED,
            title=f"{who} exported {project.name}",
            body=f"{who} exported the project {project.name}.",
            target=project,
            dedupe_key=f"export:{project.pk}:{uuid.uuid4()}",
            email_template="export_notice",
            email_context={"exporter": who, "project": project.name, "lab": lab.name},
        )


# ---------------------------------------------------------------- lineage


def field_of(model, name):
    return model._meta.get_field(name)


def lineage(project) -> dict:
    """Every provenance item in the project as graph nodes and edges. Edge `kind` is the kind
    of its source node. Eleven queries however large the project is (the M2M link tables are
    read whole, once each), so the UI never needs a per-node call."""

    def mine(model, *related):
        return (
            model.objects.for_lab(project.lab_id)
            .filter(project=project)
            .select_related(*related)
            .order_by("created_at", "id")
        )

    def links(field):
        through = field.remote_field.through
        left, right = field.m2m_field_name(), field.m2m_reverse_field_name()
        return through.objects.filter(**{f"{left}__project": project}).values_list(
            f"{left}_id", f"{right}_id"
        )

    nodes, edges = [], []

    def node(kind, obj, label, subtitle, **meta):
        nodes.append(
            {
                "id": f"{kind}:{obj.pk}",
                "kind": kind,
                "label": label,
                "subtitle": subtitle,
                "href_id": obj.pk,
                "meta": meta,
            }
        )

    def edge(kind, source, target, source_pk, target_pk):
        source, target = f"{source}:{source_pk}", f"{target}:{target_pk}"
        edges.append({"id": f"{source}>{target}", "source": source, "target": target, "kind": kind})

    datasets = list(mine(DatasetRecord))
    analyses = list(mine(Analysis, "ran_by"))
    results = list(mine(Result))
    manuscripts = list(mine(ManuscriptLink))
    decisions = list(mine(Decision))
    analysis_titles = {a.pk: a.title for a in analyses}

    for d in datasets:
        node(
            "dataset",
            d,
            d.name,
            d.version_label,
            version_label=d.version_label,
            checksum=d.checksum,
            location_url=d.location_url,
            location_text=d.location_text,
        )
        if d.previous_version_id:
            edge("dataset", "dataset", "dataset", d.previous_version_id, d.pk)
    for a in analyses:
        node(
            "analysis",
            a,
            a.title,
            a.code_commit[:7] or "Code attached",
            code_repo_url=a.code_repo_url,
            code_commit=a.code_commit,
            code_attachment_id=a.code_attachment_id,
            ran_by=a.ran_by.display_name or a.ran_by.email,
            ran_at=a.ran_at,
        )
    for r in results:
        node(
            "result",
            r,
            r.title,
            analysis_titles.get(r.analysis_id, ""),
            summary=r.summary,
            analysis_id=r.analysis_id,
        )
        edge("analysis", "analysis", "result", r.analysis_id, r.pk)
    for m in manuscripts:
        node("manuscript", m, m.title, m.status, status=m.status, url=m.url)
    for d in decisions:
        node(
            "decision",
            d,
            d.title,
            d.decided_on.isoformat(),
            decided_on=d.decided_on,
            rationale=d.rationale,
        )

    # Outside files linked to nodes (integrations): one more query, shown in the node's panel.
    from integrations.models import ExternalLink

    by_node = {}
    outside = ExternalLink.objects.for_lab(project.lab_id).filter(project=project)
    for link in outside.order_by("created_at", "id"):
        for kind in ("dataset", "analysis", "result", "manuscript", "decision"):
            if getattr(link, f"{kind}_id"):
                by_node.setdefault(f"{kind}:{getattr(link, f'{kind}_id')}", []).append(
                    {
                        "id": link.pk,
                        "provider": link.provider,
                        "title": link.title,
                        "url": link.url,
                        "status": link.status,
                        "last_checked_at": link.last_checked_at,
                    }
                )
    for n in nodes:
        if n["id"] in by_node:
            n["meta"]["external_links"] = by_node[n["id"]]

    for analysis_id, dataset_id in links(field_of(Analysis, "datasets")):
        edge("dataset", "dataset", "analysis", dataset_id, analysis_id)
    for manuscript_id, result_id in links(field_of(ManuscriptLink, "results")):
        edge("result", "result", "manuscript", result_id, manuscript_id)
    for name, kind in (("analyses", "analysis"), ("results", "result"), ("datasets", "dataset")):
        for decision_id, other_id in links(field_of(Decision, name)):
            edge("decision", "decision", kind, decision_id, other_id)
    return {"nodes": nodes, "edges": edges}
