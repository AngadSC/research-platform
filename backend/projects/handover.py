"""Handover report (ARCHITECTURE section 5, Phase 6). Every queryset goes through
`visible_to(requester, lab)`, so the report never shows the requester anything they could not
already see: hidden projects, and restricted ethics approvals (D56), are simply absent.

The number of queries is constant: one per section plus a few for the "no other owner" checks.
"""

from django.db.models import Count, Q
from django.utils import timezone

from documents.models import Document
from ethics.models import EthicsApproval
from labs.models import LabMembership, LabRole
from projects.models import Project, ProjectMembership, ProjectRole, Task, TaskStatus
from provenance.models import Analysis, DatasetRecord, Decision, Result

SECTIONS = [
    ("open_tasks", "Open tasks"),
    ("documents", "Documents"),
    ("analyses", "Analyses"),
    ("results", "Results"),
    ("datasets", "Datasets"),
    ("decisions", "Decisions"),
    ("ethics_approvals", "Ethics approvals"),
    ("projects_led", "Projects led"),
]


def _ref(p):
    return {"id": p.pk, "name": p.name}


def _item(lab_id, kind, obj, title, project, path, reason):
    """`project` is the item's project; a project item passes itself. `path` is relative to
    the lab, and `{p}` stands for `projects/<project id>`."""
    return {
        "id": obj.pk,
        "kind": kind,
        "title": title,
        "project": _ref(project) if project else None,
        "href": f"/labs/{lab_id}/"
        + path.replace("{p}", f"projects/{project.pk}" if project else ""),
        "reason": reason,
    }


def build_report(*, requester, lab, membership, project=None) -> dict:
    """`membership` is the target's LabMembership; `project` limits the report to one project
    the requester can already see."""
    target = membership.user
    lid = lab.pk

    def scoped(model):
        qs = model.objects.visible_to(requester, lab)
        if project is None:
            return qs
        return qs.filter(pk=project.pk) if model is Project else qs.filter(project=project)

    def research(model, field, kind, plural, reason):
        qs = scoped(model).filter(**{field: target}).select_related("project")
        return [
            _item(lid, kind, o, o.title, o.project, f"{{p}}/research/{plural}/{o.pk}", reason)
            for o in qs.order_by("created_at", "id")
        ]

    led = list(
        scoped(Project)
        .filter(memberships__user=target, memberships__role=ProjectRole.LEAD)
        .order_by("name", "id")
    )
    led_ids = [p.pk for p in led]
    lead_counts = dict(
        ProjectMembership.objects.visible_to(requester, lab)
        .filter(project_id__in=led_ids, role=ProjectRole.LEAD)
        .values_list("project_id")
        .annotate(n=Count("id"))
    )
    tasks = (
        scoped(Task)
        .filter(assignee=target)
        .exclude(status=TaskStatus.DONE)
        .select_related("project")
        .order_by("due_date", "id")
    )
    docs = list(
        scoped(Document)
        .filter(deleted_at__isnull=True)
        .filter(Q(created_by=target) | Q(updated_by=target))
        .select_related("project")
        .order_by("title", "id")
    )
    datasets = list(
        scoped(DatasetRecord)
        .filter(controlled_by=target)
        .select_related("project")
        .order_by("name", "id")
    )
    approvals = list(
        EthicsApproval.objects.visible_to(requester, lab)
        .filter(deleted_at__isnull=True, projects__in=led_ids)
        .prefetch_related("projects")
        .distinct()
        .order_by("expiry_date", "id")
    )

    projects_led = [
        _item(lid, "project", p, p.name, p, "{p}/overview", f"They lead it ({p.status})")
        for p in led
    ]
    documents = [
        _item(
            lid,
            "document",
            d,
            d.title,
            d.project,
            f"{{p}}/documents/{d.pk}",
            "Created by them" if d.created_by_id == target.pk else "Last edited by them",
        )
        for d in docs
    ]
    dataset_items = [
        _item(
            lid,
            "dataset",
            d,
            f"{d.name} {d.version_label}",
            d.project,
            f"{{p}}/research/datasets/{d.pk}",
            "Controlled by them",
        )
        for d in datasets
    ]
    ethics = []
    for a in approvals:
        mine = [p for p in a.projects.all() if p.pk in led_ids]
        ethics.append(
            _item(
                lid,
                "ethics_approval",
                a,
                f"{a.approval_number}: {a.title}",
                mine[0],
                f"ethics/{a.pk}",
                "Linked to " + ", ".join(p.name for p in mine),
            )
        )
    by_key = {
        "open_tasks": [
            _item(lid, "task", t, t.title, t.project, "{p}/tasks", f"Assigned to them ({t.status})")
            for t in tasks
        ],
        "documents": documents,
        "analyses": research(Analysis, "ran_by", "analysis", "analyses", "Run by them"),
        "results": research(Result, "analysis__ran_by", "result", "results", "From their analysis"),
        "datasets": dataset_items,
        "decisions": research(Decision, "decided_by", "decision", "decisions", "Decided by them"),
        "ethics_approvals": ethics,
        "projects_led": projects_led,
    }

    # "No other owner": they are the only lead, they created the document, or they control a
    # dataset and no other non-viewer project member can edit content.
    # ponytail: pi and lab_admin act as implicit leads everywhere (D19) but are not counted as
    # owners here; count them if the lab wants that.
    lab_viewers = LabMembership.objects.visible_to(requester, lab).filter(role=LabRole.VIEWER)
    has_editor = set(
        ProjectMembership.objects.visible_to(requester, lab)
        .filter(
            project_id__in={d.project_id for d in datasets},
            role__in=[ProjectRole.LEAD, ProjectRole.CONTRIBUTOR],
        )
        .exclude(user=target)
        .exclude(user_id__in=lab_viewers.values("user_id"))
        .values_list("project_id", flat=True)
    )
    orphan = [
        item | {"reason": "They are the only lead. Needs a new lead."}
        for p, item in zip(led, projects_led, strict=True)
        if lead_counts.get(p.pk) == 1
    ]
    orphan += [
        item | {"reason": "They created it. Needs a new owner."}
        for d, item in zip(docs, documents, strict=True)
        if d.created_by_id == target.pk
    ]
    orphan += [
        item | {"reason": "No other member can edit this project's data."}
        for d, item in zip(datasets, dataset_items, strict=True)
        if d.project_id not in has_editor
    ]

    return {
        "generated_at": timezone.now(),
        "person": {
            "id": target.pk,
            "membership_id": membership.pk,
            "display_name": target.display_name,
            "email": target.email,
        },
        "project": _ref(project) if project else None,
        "no_other_owner": orphan,
        "sections": [{"key": k, "label": label, "items": by_key[k]} for k, label in SECTIONS],
    }
