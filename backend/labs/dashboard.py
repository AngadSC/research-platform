"""PI dashboard (Run 5, D170-D174): `GET L/dashboard/` for pi and lab_admin (manage_lab).

Every query goes through `visible_to`, so nothing is shown that the requester could not open
elsewhere. The query count is fixed: it does not grow with projects, tasks or members.
"""

from datetime import timedelta

from django.db.models import Case, Count, IntegerField, Max, Q, Value, When
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from audit.models import AuditAction, AuditEvent
from core.permissions import Perm, visible_projects
from core.views import LabScopedViewMixin
from ethics.models import ApprovalStatus, EthicsApproval
from integrations.models import AccountStatus, ConnectedAccount
from labs.models import LabMembership
from projects.models import (
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    Task,
    TaskStatus,
)
from provenance.models import (
    DataManagementPlan,
    DatasetRecord,
    DmpStatus,
    FundingRecord,
    FundingStatus,
)

LIMIT = 20  # per attention list; the total is reported separately
DMP_GRACE_DAYS = 14  # a new project is not flagged for a missing plan until it is this old
ETHICS_DAYS, FUNDING_DAYS, DEADLINE_DAYS, STALLED_DAYS, DONE_DAYS = 60, 90, 14, 30, 30
ACTIVE_FUNDING = (FundingStatus.AWARDED, FundingStatus.ACTIVE)
_PRIORITY_RANK = Case(
    When(priority="high", then=Value(0)),
    When(priority="medium", then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)


def _name(user) -> str | None:
    return (user.display_name or user.email) if user else None


def _ref(user) -> dict | None:
    return {"id": user.pk, "name": _name(user)} if user else None


# ---------------------------------------------------------------- response shapes (schema only)


class PersonRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class _ProjectBits(serializers.Serializer):
    project_id = serializers.UUIDField()
    project_name = serializers.CharField()


class DashNextDeadlineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    due_date = serializers.DateField()
    priority = serializers.CharField()


class DashFundingSerializer(_ProjectBits):
    id = serializers.UUIDField()
    funder = serializers.CharField()
    end_date = serializers.DateField()
    days_left = serializers.IntegerField(help_text="Negative once the end date has passed.")
    status = serializers.CharField()


class DashProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    status = serializers.CharField()
    leads = PersonRefSerializer(many=True)
    open_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    in_progress_tasks = serializers.IntegerField()
    next_deadline = DashNextDeadlineSerializer(allow_null=True)
    last_activity_at = serializers.DateTimeField(allow_null=True)
    last_activity_by = PersonRefSerializer(allow_null=True)
    funding_end_date = serializers.DateField(allow_null=True)
    funding_status = serializers.CharField(allow_null=True)
    health = serializers.ChoiceField(choices=["red", "amber", "green"])
    health_reasons = serializers.ListField(child=serializers.CharField())


class DashOverdueTaskSerializer(_ProjectBits):
    id = serializers.UUIDField()
    title = serializers.CharField()
    due_date = serializers.DateField()
    days_overdue = serializers.IntegerField()
    assignee = PersonRefSerializer(allow_null=True)


class DashEthicsSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    approval_number = serializers.CharField()
    expiry_date = serializers.DateField()
    days_left = serializers.IntegerField(help_text="Negative once expired.")
    expired = serializers.BooleanField()


class DashDeadlineSerializer(_ProjectBits, DashNextDeadlineSerializer):
    days_left = serializers.IntegerField(help_text="Negative when already late.")


class DashStalledSerializer(_ProjectBits):
    last_activity_at = serializers.DateTimeField()
    days_idle = serializers.IntegerField()


class DashUnassignedSerializer(_ProjectBits):
    id = serializers.UUIDField()
    title = serializers.CharField()
    due_date = serializers.DateField(allow_null=True)


class DashDmpSerializer(_ProjectBits):
    dmp_status = serializers.CharField(help_text="none, draft or submitted.")


class DashIntegrationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.CharField()
    status = serializers.CharField()
    user = PersonRefSerializer()


def _list(item_serializer):
    return type(
        f"{item_serializer.__name__.removesuffix('Serializer')}List",
        (serializers.Serializer,),
        {"total": serializers.IntegerField(), "items": item_serializer(many=True)},
    )


class DashPersonSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    open_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    done_last_30_days = serializers.IntegerField()
    last_active_at = serializers.DateTimeField(allow_null=True)


class DashSummarySerializer(serializers.Serializer):
    active_projects = serializers.IntegerField()
    open_tasks = serializers.IntegerField()
    overdue_tasks = serializers.IntegerField()
    deadlines_soon = serializers.IntegerField()
    ethics_attention = serializers.IntegerField()
    funding_ending = serializers.IntegerField()
    stalled_projects = serializers.IntegerField()
    unassigned_tasks = serializers.IntegerField()
    integration_problems = serializers.IntegerField()
    projects_without_dmp = serializers.IntegerField()


class DashAttentionSerializer(serializers.Serializer):
    overdue_tasks = _list(DashOverdueTaskSerializer)()
    ethics = _list(DashEthicsSerializer)()
    funding = _list(DashFundingSerializer)()
    deadlines = _list(DashDeadlineSerializer)()
    stalled = _list(DashStalledSerializer)()
    unassigned = _list(DashUnassignedSerializer)()
    integrations = _list(DashIntegrationSerializer)()
    dmp = _list(DashDmpSerializer)()


class DashboardSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    summary = DashSummarySerializer()
    projects = DashProjectSerializer(many=True)
    attention = DashAttentionSerializer()
    people = DashPersonSerializer(many=True)


# ---------------------------------------------------------------- the data


def build_dashboard(user, lab) -> dict:
    now = timezone.now()
    today = now.date()
    projects = list(visible_projects(user, lab).select_related("last_activity_by").order_by("name"))
    pname = {p.pk: p.name for p in projects}

    # ponytail: one query per kind, grouped in Python; lab-sized data, no pagination.
    leads: dict = {}
    for m in (
        ProjectMembership.objects.visible_to(user, lab)
        .filter(role=ProjectRole.LEAD)
        .select_related("user")
        .order_by("created_at")
    ):
        leads.setdefault(m.project_id, []).append(_ref(m.user))

    tasks = Task.objects.visible_to(user, lab)
    not_done = ~Q(status=TaskStatus.DONE)
    late = Q(due_date__lt=today) & not_done
    counts = {
        r["project_id"]: r
        for r in tasks.values("project_id").annotate(
            open=Count("id", filter=not_done),
            overdue=Count("id", filter=late),
            in_progress=Count("id", filter=Q(status=TaskStatus.IN_PROGRESS)),
        )
    }
    per_person = {
        r["assignee_id"]: r
        for r in tasks.filter(assignee__isnull=False)
        .values("assignee_id")
        .annotate(
            open=Count("id", filter=not_done),
            overdue=Count("id", filter=late),
            # updated_at stands in for "completed at" (no such column); see D172.
            done=Count(
                "id",
                filter=Q(status=TaskStatus.DONE, updated_at__gte=now - timedelta(days=DONE_DAYS)),
            ),
        )
    }

    # The earliest unfinished deadline per project (late ones count: they are the next thing due).
    next_dl = {
        d.project_id: d
        for d in ProjectDeadline.objects.visible_to(user, lab)
        .filter(done=False)
        .order_by("project_id", "due_date", "id")
        .distinct("project_id")
    }
    soon = list(
        ProjectDeadline.objects.visible_to(user, lab)
        .filter(done=False, due_date__lte=today + timedelta(days=DEADLINE_DAYS))
        .annotate(rank=_PRIORITY_RANK)
        .order_by("rank", "due_date", "id")
    )

    funding = list(
        FundingRecord.objects.visible_to(user, lab)
        .filter(status__in=ACTIVE_FUNDING, end_date__isnull=False)
        .order_by("end_date", "id")
    )
    covering: dict = {}  # per project, the active record that runs longest
    for f in funding:
        covering[f.project_id] = f
    funding_due = [f for f in funding if (f.end_date - today).days <= FUNDING_DAYS]

    ethics_rows = list(
        EthicsApproval.objects.visible_to(user, lab)
        .filter(deleted_at__isnull=True, expiry_date__lte=today + timedelta(days=ETHICS_DAYS))
        .exclude(status=ApprovalStatus.WITHDRAWN)
        .order_by("expiry_date", "id")
    )

    overdue_top = list(
        tasks.filter(late).select_related("assignee").order_by("due_date", "id")[:LIMIT]
    )
    unassigned_qs = tasks.filter(
        not_done,
        assignee__isnull=True,
        pk__in=AuditEvent.objects.filter(lab=lab, action=AuditAction.TASK_UNASSIGNED).values(
            "target_id"
        ),
    ).order_by("due_date", "created_at")
    unassigned = list(unassigned_qs)

    broken = list(
        ConnectedAccount.objects.visible_to(user, lab)
        .filter(status__in=(AccountStatus.ERROR, AccountStatus.EXPIRED))
        .select_related("user")
        .order_by("provider", "id")
    )

    # D185: a planning or active project with no approved data management plan.
    dmp_status = dict(
        DataManagementPlan.objects.visible_to(user, lab).values_list("project_id", "status")
    )

    # A brand-new project is not flagged yet: wait DMP_GRACE_DAYS, or until it holds a dataset.
    has_data = set(DatasetRecord.objects.for_lab(lab.pk).values_list("project_id", flat=True))

    members = list(LabMembership.objects.for_lab(lab).select_related("user").order_by("created_at"))
    last_active = {
        r["actor_id"]: r["at"]
        for r in AuditEvent.objects.filter(lab=lab, actor__in=[m.user_id for m in members])
        .values("actor_id")
        .annotate(at=Max("occurred_at"))
    }

    # ---- project rows, health, stalled
    rows, stalled = [], []
    stale_before = now - timedelta(days=STALLED_DAYS)
    soon_ids = {d.project_id for d in soon}
    for p in projects:
        c = counts.get(p.pk, {})
        overdue = c.get("overdue", 0)
        f = covering.get(p.pk)
        activity = p.last_activity_at or p.created_at
        is_stalled = p.status in (ProjectStatus.PLANNING, ProjectStatus.ACTIVE) and (
            activity < stale_before
        )
        if is_stalled:
            stalled.append(
                {
                    "project_id": p.pk,
                    "project_name": p.name,
                    "last_activity_at": activity,
                    "days_idle": (now - activity).days,
                }
            )
        live = p.status not in (ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED)
        red, amber = [], []
        if live:
            if overdue:
                red.append(f"{overdue} overdue task{'s' if overdue != 1 else ''}")
            if f and f.end_date < today:
                red.append("Funding has ended")
            elif f and (f.end_date - today).days <= FUNDING_DAYS:
                amber.append("Funding ends soon")
            if p.pk in soon_ids:
                amber.append("Deadline within 14 days")
            if is_stalled:
                amber.append("No activity for 30 days")
        nd = next_dl.get(p.pk)
        rows.append(
            {
                "id": p.pk,
                "name": p.name,
                "status": p.status,
                "leads": leads.get(p.pk, []),
                "open_tasks": c.get("open", 0),
                "overdue_tasks": overdue,
                "in_progress_tasks": c.get("in_progress", 0),
                "next_deadline": nd
                and {
                    "id": nd.pk,
                    "title": nd.title,
                    "due_date": nd.due_date,
                    "priority": nd.priority,
                },
                "last_activity_at": p.last_activity_at,
                "last_activity_by": _ref(p.last_activity_by),
                "funding_end_date": f.end_date if f else None,
                "funding_status": f.status if f else None,
                "health": "red" if red else "amber" if amber else "green",
                "health_reasons": red + amber,
            }
        )

    total_overdue = sum(r["overdue_tasks"] for r in rows)
    ethics_items = [
        {
            "id": a.pk,
            "title": a.title,
            "approval_number": a.approval_number,
            "expiry_date": a.expiry_date,
            "days_left": (a.expiry_date - today).days,
            "expired": a.expiry_date < today,
        }
        for a in ethics_rows
    ]
    funding_items = [
        {
            "id": f.pk,
            "project_id": f.project_id,
            "project_name": pname.get(f.project_id, ""),
            "funder": f.funder,
            "end_date": f.end_date,
            "days_left": (f.end_date - today).days,
            "status": f.status,
        }
        for f in funding_due
    ]
    deadline_items = [
        {
            "id": d.pk,
            "title": d.title,
            "due_date": d.due_date,
            "priority": d.priority,
            "project_id": d.project_id,
            "project_name": pname.get(d.project_id, ""),
            "days_left": (d.due_date - today).days,
        }
        for d in soon
    ]
    stalled.sort(key=lambda s: s["last_activity_at"])
    dmp_items = [
        {
            "project_id": p.pk,
            "project_name": p.name,
            "dmp_status": dmp_status.get(p.pk, "none"),
        }
        for p in projects
        if p.status in (ProjectStatus.PLANNING, ProjectStatus.ACTIVE)
        and dmp_status.get(p.pk) != DmpStatus.APPROVED
        and (p.created_at <= now - timedelta(days=DMP_GRACE_DAYS) or p.pk in has_data)
    ]
    unassigned_items = [
        {
            "id": t.pk,
            "title": t.title,
            "due_date": t.due_date,
            "project_id": t.project_id,
            "project_name": pname.get(t.project_id, ""),
        }
        for t in unassigned
    ]
    integration_items = [
        {"id": a.pk, "provider": a.provider, "status": a.status, "user": _ref(a.user)}
        for a in broken
    ]

    def cap(items, total=None):
        return {"total": len(items) if total is None else total, "items": items[:LIMIT]}

    people = []
    for m in members:
        c = per_person.get(m.user_id, {})
        people.append(
            {
                "user_id": m.user_id,
                "name": _name(m.user),
                "role": m.role,
                "open_tasks": c.get("open", 0),
                "overdue_tasks": c.get("overdue", 0),
                "done_last_30_days": c.get("done", 0),
                "last_active_at": last_active.get(m.user_id),
            }
        )

    return {
        "generated_at": now,
        "summary": {
            "active_projects": sum(p.status == ProjectStatus.ACTIVE for p in projects),
            "open_tasks": sum(r["open_tasks"] for r in rows),
            "overdue_tasks": total_overdue,
            "deadlines_soon": len(deadline_items),
            "ethics_attention": len(ethics_items),
            "funding_ending": len(funding_items),
            "stalled_projects": len(stalled),
            "unassigned_tasks": len(unassigned_items),
            "integration_problems": len(integration_items),
            "projects_without_dmp": len(dmp_items),
        },
        "projects": rows,
        "attention": {
            "overdue_tasks": cap(
                [
                    {
                        "id": t.pk,
                        "title": t.title,
                        "due_date": t.due_date,
                        "days_overdue": (today - t.due_date).days,
                        "project_id": t.project_id,
                        "project_name": pname.get(t.project_id, ""),
                        "assignee": _ref(t.assignee),
                    }
                    for t in overdue_top
                ],
                total_overdue,
            ),
            "ethics": cap(ethics_items),
            "funding": cap(funding_items),
            "deadlines": cap(deadline_items),
            "stalled": cap(stalled),
            "unassigned": cap(unassigned_items),
            "integrations": cap(integration_items),
            "dmp": cap(dmp_items),
            # Training agent: add `"training": cap([...])` here and a summary count when its
            # expiring-certifications endpoint exists (D174).
        },
        "people": people,
    }


class DashboardView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = DashboardSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_LAB}  # pi and lab_admin only (D170)

    @extend_schema(responses=DashboardSerializer)
    def get(self, request, lab_id):
        return Response(DashboardSerializer(build_dashboard(request.user, request.lab)).data)
