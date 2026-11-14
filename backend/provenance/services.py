"""Provenance business logic (ARCHITECTURE sections 1, 4, 5). Every link is resolved inside the
one project (D20, D31): an ID from another project or lab fails exactly like a missing ID.
Writes record their audit event in the same transaction."""

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, ProtectedError, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from assistant.privacy import is_flagged, set_flag
from audit.models import AuditAction
from audit.services import record
from core.models import NotificationKind, User
from core.notifications import notify
from core.permissions import Perm, can, require
from documents.models import Attachment, Document
from documents.services import Conflict
from ethics.models import ApprovalStatus, EthicsApproval
from labs.models import LabMembership, LabRole
from projects.models import Project, ProjectDeadline, ProjectMembership, Task
from provenance.models import (
    WORKFLOW_STAGES,
    Analysis,
    DatasetRecord,
    Decision,
    ExternalOutput,
    FundingRecord,
    FundingStatus,
    ManuscriptLink,
    ManuscriptStatus,
    RecruitmentEntry,
    RecruitmentPlan,
    RecruitmentStatus,
    Result,
    ReviewItem,
    ReviewStatus,
)


class Spec:
    """What a kind links to. `fks` and `m2ms` map field -> (model, must_not_be_soft_deleted);
    `users` are user FKs (must be able to view the project); `owner` defaults to the actor."""

    def __init__(
        self, model, created, updated, deleted, *, owner, fks=(), m2ms=(), users=(), opt_users=()
    ):
        self.model, self.owner = model, owner
        self.created, self.updated, self.deleted = created, updated, deleted
        self.fks, self.m2ms, self.users = dict(fks), dict(m2ms), tuple(users)
        # optional people (a funding holder, a reviewer): no default, any lab member who can
        # view the project, and naming someone else needs no lead (it is not a record of who did it)
        self.opt_users = tuple(opt_users)


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
    "funding": Spec(
        FundingRecord,
        A.FUNDING_CREATED,
        A.FUNDING_UPDATED,
        A.FUNDING_DELETED,
        owner="created_by",
        fks={"attachment": (Attachment, True)},
        opt_users=("holder",),
    ),
    "review": Spec(
        ReviewItem,
        A.REVIEW_ITEM_CREATED,
        A.REVIEW_ITEM_UPDATED,
        A.REVIEW_ITEM_DELETED,
        owner="created_by",
        opt_users=("reviewer",),
    ),
    "recruitment": Spec(
        RecruitmentEntry,
        A.RECRUITMENT_ENTRY_CREATED,
        A.RECRUITMENT_ENTRY_UPDATED,
        A.RECRUITMENT_ENTRY_DELETED,
        owner="created_by",
    ),
    "external": Spec(
        ExternalOutput,
        A.EXTERNAL_OUTPUT_CREATED,
        A.EXTERNAL_OUTPUT_UPDATED,
        A.EXTERNAL_OUTPUT_DELETED,
        owner="created_by",
        fks={"attachment": (Attachment, True)},
    ),
}

# D133: grant money is for project leads (edit_project) to see and to write.
FUNDING_LEAD_ONLY = ("amount", "currency")


def _scoped(project, model, live, actor):
    if model is Attachment:  # PI-only files (grant letters) stay out of reach of everyone else
        qs = Attachment.objects.visible_to(actor, project.lab_id).filter(project=project)
    else:
        qs = model.objects.for_lab(project.lab_id).filter(project=project)
    return qs.filter(deleted_at__isnull=True) if live else qs


def _one(project, field, model, live, pk, actor):
    obj = _scoped(project, model, live, actor).filter(pk=pk).first()
    if obj is None:
        raise ValidationError({field: "This item does not exist in this project."})
    return obj


def _many(project, field, model, live, ids, actor):
    ids = set(ids)
    found = list(_scoped(project, model, live, actor).filter(pk__in=ids))
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
    m2m = {f: _many(project, f, *spec.m2ms[f], data.pop(f), actor) for f in spec.m2ms if f in data}
    for field, (model, live) in spec.fks.items():
        if data.get(field) is not None:
            data[field] = _one(project, field, model, live, data[field], actor)
    code = data.get("code_attachment")
    if code is not None and is_flagged(code):  # VISION C1: Claude may run an analysis's code
        msg = "This file identifies participants, so it can't be attached as code."
        raise ValidationError({"code_attachment": msg})
    for field in spec.users:
        if creating and data.get(field) is None:
            data[field] = actor  # D50: the person recording it, unless a lead says otherwise
        elif data.get(field) is not None:
            if str(data[field]) != str(actor.pk):
                require(actor, Perm.EDIT_PROJECT, project)  # D50: naming someone else
            data[field] = _user(project, field, data[field])
    for field in spec.opt_users:
        if data.get(field) is not None:
            data[field] = _user(project, field, data[field])
    if creating and data.get(spec.owner) is None:
        data[spec.owner] = actor
    return data, m2m


def _check_dates(obj):
    if isinstance(obj, FundingRecord) and obj.start_date and obj.end_date:
        if obj.end_date < obj.start_date:
            raise ValidationError({"end_date": "The end date must not be before the start date."})


def _save(obj):
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:  # unique (project, name, version_label), D33
        raise ValidationError({"detail": "An item with these details already exists."}) from exc


def _keep_letter_private(obj):
    """D244: the file stays PI-only even after this record stops pointing at it."""
    if isinstance(obj, FundingRecord) and obj.attachment_id:
        Attachment.objects.for_lab(obj.lab_id).filter(pk=obj.attachment_id).update(pi_only=True)


@transaction.atomic
def create(kind, *, project, user, data, request=None):
    spec = SPECS[kind]
    values, m2m = _resolve(spec, project, data, actor=user, creating=True)
    if kind == "analysis":
        values.setdefault("ran_at", timezone.now())
    if kind == "decision":
        values.setdefault("decided_on", timezone.localdate())
    previous = values.get("previous_version") if kind == "dataset" else None
    if previous and previous.contains_participant_data:
        # a new version of flagged data stays flagged unless the form said otherwise
        values.setdefault("contains_participant_data", True)
    obj = spec.model(lab=project.lab, project=project, **values)
    if kind == "analysis":
        _check_analysis(obj)
    _check_dates(obj)
    _save(obj)
    _keep_letter_private(obj)
    for field, items in m2m.items():
        getattr(obj, field).set(items)
    record(spec.created, actor=user, lab=project.lab, target=obj, request=request)
    return obj


@transaction.atomic
def update(kind, obj, *, user, data, request=None):
    spec = SPECS[kind]
    project = obj.project
    values, m2m = _resolve(spec, project, data, actor=user, creating=False)
    flag = values.pop("contains_participant_data", None)  # its own audit event (VISION A3)
    if values.get("previous_version") == obj:
        raise ValidationError({"previous_version": "A dataset cannot be its own previous version."})
    for key, value in values.items():
        setattr(obj, key, value)
    if kind == "analysis":
        _check_analysis(obj)
    _check_dates(obj)
    _save(obj)
    _keep_letter_private(obj)
    for field, items in m2m.items():
        getattr(obj, field).set(items)
    if flag is not None:
        set_flag(obj, flag, user=user, request=request)
    if not (values or m2m) and flag is not None:
        return obj
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


@transaction.atomic
def create_result_set(*, project, user, analysis, items, request=None):
    """One result per item, all from one analysis. Any bad item saves none of them."""
    return [
        create(
            "result",
            project=project,
            user=user,
            data={**item, "analysis": analysis},
            request=request,
        )
        for item in items
    ]


# ---------------------------------------------------------------- workflow progress


def workflow_progress(project, user) -> dict:
    """Which Workflow stages are done, and the first one that is not. A stage is done when its
    records say so, or when someone marked it done or not needed."""

    def mine(model):
        return model.objects.for_lab(project.lab_id).filter(project=project)

    counts = dict(
        mine(RecruitmentEntry).values_list("status").annotate(n=Sum("count")).order_by("status")
    )
    plan = mine(RecruitmentPlan).first()
    people = max(
        counts.get(RecruitmentStatus.ENROLLED, 0), counts.get(RecruitmentStatus.COMPLETED, 0)
    )
    reviews = mine(ReviewItem)
    found = {
        "funding": FundingRecord.objects.visible_to(user, project.lab_id)
        .filter(project=project)
        .exclude(
            status=FundingStatus.DECLINED
        )  # a record is enough; a declined grant pays for nothing
        .exists(),
        "ethics": EthicsApproval.objects.visible_to(user, project.lab_id)
        .filter(
            projects=project,
            deleted_at__isnull=True,
            status=ApprovalStatus.ACTIVE,
            expiry_date__gte=timezone.localdate(),
        )
        .exists(),
        "participants": people >= ((plan.target_enrolment if plan else None) or 1),
        "data": mine(DatasetRecord).exists(),
        "analysis": mine(Result).exists(),
        "manuscript": mine(ManuscriptLink).exclude(status=ManuscriptStatus.DRAFTING).exists(),
        "review": reviews.exists() and not reviews.exclude(status=ReviewStatus.APPROVED).exists(),
    }
    marked = set(project.workflow_marked_done)
    shown = [
        s for s in WORKFLOW_STAGES if s != "funding" or can(user, Perm.ACCESS_FUNDING, project)
    ]  # D226: the funding stage says whether a project is funded, so it is PIs only as well
    stages = [{"key": s, "done": found[s] or s in marked, "marked": s in marked} for s in shown]
    return {"stages": stages, "next": next((s["key"] for s in stages if not s["done"]), None)}


@transaction.atomic
def mark_workflow_stage(*, project, user, stage, done, request=None):
    if stage == "funding":
        require(user, Perm.ACCESS_FUNDING, project)
    if stage == "review" and done:
        waiting = list(
            ReviewItem.objects.for_lab(project.lab_id)
            .filter(project=project)
            .exclude(status=ReviewStatus.APPROVED)
            .values_list("title", flat=True)
        )
        if waiting:
            raise ValidationError(
                {"detail": "Review items still waiting: " + ", ".join(waiting) + "."}
            )
    locked = Project.objects.for_lab(project.lab_id).select_for_update().get(pk=project.pk)
    marked = [s for s in locked.workflow_marked_done if s != stage] + ([stage] if done else [])
    locked.workflow_marked_done = marked
    locked.save(update_fields=["workflow_marked_done", "updated_at"])
    record(
        # D226: a stage marked done says whether a project has money, and the audit log hides
        # only funding.* from people who are not PIs
        A.FUNDING_UPDATED if stage == "funding" else A.PROJECT_UPDATED,
        actor=user,
        lab=project.lab,
        target=locked,
        request=request,
        metadata={"fields": ["workflow_marked_done"], "stage": stage, "done": done},
    )
    return locked


# ---------------------------------------------------------------- recruitment plan (D136)


def recruitment_plan(project):
    """The project's plan, or an unsaved empty one (nothing is written by a read)."""
    plan = RecruitmentPlan.objects.for_lab(project.lab_id).filter(project=project).first()
    return plan or RecruitmentPlan(lab=project.lab, project=project)


@transaction.atomic
def update_recruitment_plan(*, project, user, data, request=None):
    plan = (
        RecruitmentPlan.objects.for_lab(project.lab_id)
        .select_for_update()
        .filter(project=project)
        .first()
    ) or RecruitmentPlan(lab=project.lab, project=project)
    for key, value in data.items():
        setattr(plan, key, value)
    plan.save()
    record(
        A.RECRUITMENT_PLAN_UPDATED,
        actor=user,
        lab=project.lab,
        target=plan,
        request=request,
        metadata={"fields": sorted(data)},
    )
    return plan


# ---------------------------------------------------------------- export


def export_project(*, project, user, context, request=None) -> dict:
    """One JSON document: metadata, tasks, latest documents and provenance. No file bytes.
    Every query is scoped to `project` and its lab, so nothing from another project leaks."""
    from provenance.serializers import PLURAL, queryset

    def mine(model):
        return model.objects.for_lab(project.lab_id).filter(project=project)

    live = {"deleted_at__isnull": True}
    files = Attachment.objects.visible_to(user, project.lab_id)  # D226: no grant letters
    out = {
        "exported_at": timezone.now(),
        "project": project,
        "tasks": mine(Task)
        .select_related("assignee", "created_by")
        .prefetch_related(Prefetch("attachments", files))
        .order_by("created_at", "id"),
        "deadlines": mine(ProjectDeadline).order_by("due_date", "id"),
        "documents": mine(Document)
        .filter(**live)
        .select_related("created_by", "updated_by")
        .order_by("created_at", "id"),
        "attachments": files.filter(project=project, **live).select_related("uploaded_by"),
        **{PLURAL[kind]: queryset(kind, project, user) for kind in SPECS},
        "recruitment_plan": recruitment_plan(project),
        "members": ProjectMembership.objects.for_lab(project.lab_id)
        .filter(project=project)
        .select_related("user")
        .order_by("created_at", "id"),
        # same visibility as the Ethics tab (D56)
        "ethics_approvals": EthicsApproval.objects.visible_to(user, project.lab_id)
        .filter(projects=project, deleted_at__isnull=True)
        .order_by("approval_date", "id"),
    }
    record(
        AuditAction.PROJECT_EXPORTED,
        actor=user,
        lab=project.lab,
        target=project,
        request=request,
        metadata={  # the audit log is also read by lab admins, so no funding count (D226)
            k: v.count() for k, v in out.items() if hasattr(v, "count") and k != "funding"
        },
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
