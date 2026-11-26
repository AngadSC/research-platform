"""Site-wide Usage page for the operators (D379): GET /api/usage/?days=30&include_test=0.

Staff only (`Perm.SITE_STAFF`; anyone else signed in gets 404). It counts across every lab,
which nothing else does, so lab-scoped rows come only through `permissions.all_labs`, which
re-checks staff. It returns counts, dates and a short list of new accounts (name, email, the
institution of their first lab). Never any titles, text, file names or participant data.

"Active" means the person did something on that day (UTC): an audit event as the actor (sign-in,
task, document opened, upload...), a chat message, a document save, a paper added or a question
to the assistant. Test accounts (`TEST_EMAIL_SUFFIXES`) are left out unless `include_test=1`.
"""

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Case, CharField, Count, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.models import Message, Role
from audit import services as audit
from audit.models import AuditAction, AuditEvent
from core.models import User
from core.permissions import Perm, all_labs
from documents.models import DocumentRevision
from labs.models import Lab, LabChatMessage, LabMembership
from papers.models import Paper
from projects.models import ChatMessage, ChatSource, Project

WINDOWS = ("7", "30", "90")
# Reserved for tests and examples (RFC 2606/6761); seed_pilot and seed_full use example.test.
TEST_EMAIL_SUFFIXES = (".test", ".invalid", "@example.com", "@example.org", "@example.net")
COHORT_WEEKS = 8
RECENT_LIMIT = 50

# Feature -> the audit action prefixes it covers, or the name of a row source (below) for
# activity that writes no audit event. Statistics run in the browser and leave no trace here.
# Prefixes are tried in this order, so Exports comes first (its actions start with others').
FEATURES: dict[str, tuple[str, ...] | str] = {
    "Exports": ("project.exported", "inventory.exported", "notebook.exported"),
    "Tasks": ("task",),
    "Documents (created, opened, commented)": ("document.",),
    "Document saves": "doc_saves",
    "Files": ("attachment.", "file_link."),
    "Lab chat messages": "lab_chat",
    "Project chat messages": "project_chat",
    "Meetings": ("meeting.",),
    "Calendar events": ("lab_event.", "calendar_feed."),
    "Papers added": "papers",
    "Projects": ("project.", "project_membership."),
    "Invites and members": ("membership.",),
    "Research records (data, analyses, results)": (
        "dataset.",
        "analysis.",
        "result.",
        "decision.",
        "manuscript.",
        "external_output.",
        "review_item.",
        "handover.",
    ),
    "Participants": ("participant", "recruitment", "subject."),
    "Ethics": ("ethics_approval.",),
    "Inventory and orders": ("inventory",),
    "Protocols": ("protocol.",),
    "Notebook": ("notebook.",),
    "Training": ("training",),
    "Funding": ("funding.",),
    "Data management plans": ("dmp.",),
    "Integrations and Google Chat": ("integration.", "external_link.", "google_chat.", "webhook."),
    "AI assistant (questions asked)": "assistant",
    "Outside AI tools (MCP)": ("ai_tool.", "ai_access."),
}


def _fake(prefix="") -> Q:
    q = Q()
    for suffix in TEST_EMAIL_SUFFIXES:
        q |= Q(**{f"{prefix}email__iendswith": suffix})
    # The founders' own use would swamp the numbers, so staff count as test accounts here.
    return q | Q(**{f"{prefix}is_staff": True})


def _row_sources(staff) -> dict:
    """Activity with no audit event: name -> (rows, person field, time field)."""
    return {
        "lab_chat": (
            all_labs(staff, LabChatMessage).filter(source=ChatSource.APP),
            "author",
            "created_at",
        ),
        "project_chat": (
            all_labs(staff, ChatMessage).filter(source=ChatSource.APP),
            "author",
            "created_at",
        ),
        "doc_saves": (all_labs(staff, DocumentRevision), "created_by", "created_at"),
        "papers": (all_labs(staff, Paper), "added_by", "created_at"),
        "assistant": (Message.objects.filter(role=Role.USER), "conversation__user", "created_at"),
    }


class Usage:
    def __init__(self, staff, days: int, include_test: bool):
        self.include_test = include_test
        self.today = timezone.now().date()
        self.start = self.today - timedelta(days=days - 1)
        monday = self.today - timedelta(days=self.today.weekday())
        self.cohort_start = monday - timedelta(weeks=COHORT_WEEKS - 1)
        # far enough back for the window, a month (MAU) and the retention cohorts
        self.since = min(self.start, self.cohort_start, self.today - timedelta(days=29))
        self.rows = _row_sources(staff)
        self.staff = staff

    def _at(self, day):
        return timezone.make_aware(datetime.combine(day, time.min), timezone.get_current_timezone())

    def _real(self, qs, person=""):
        return qs if self.include_test else qs.exclude(_fake(person))

    def _sources(self):
        """(rows, person field, time field) for everything that counts as activity."""
        audit = AuditEvent.objects.exclude(action=AuditAction.AUTH_LOGIN_FAILED)
        return [(audit, "actor", "occurred_at"), *self.rows.values()]

    def _activity(self) -> set:
        """(user id, day) for every day each person did something since `self.since`."""
        # ponytail: distinct (person, day) pairs land in Python; fine to ~100k pairs (thousands
        # of people over 90 days). Past that, count in SQL over a UNION of the sources.
        pairs = set()
        for qs, person, at in self._sources():
            qs = self._real(qs.filter(**{f"{at}__gte": self._at(self.since)}), f"{person}__")
            pairs.update(
                qs.filter(**{f"{person}__isnull": False})
                .annotate(day=TruncDate(at))
                .values_list(person, "day")
                .distinct()
            )
        return pairs

    def build(self) -> dict:
        start_at = self._at(self.start)
        users = self._real(User.objects.all())
        joined = list(
            users.filter(date_joined__gte=self._at(min(self.start, self.cohort_start)))
            .values_list("pk", "date_joined")
            .order_by()
        )
        joined_day = {pk: timezone.localdate(at) for pk, at in joined}
        new_ids = [pk for pk, day in joined_day.items() if day >= self.start]
        pairs = self._activity()
        days_by_user = defaultdict(set)
        for pk, day in pairs:
            days_by_user[pk].add(day)

        def active_since(day):
            return len({pk for pk, d in pairs if d >= day})

        labs = self._real(Lab.objects.all(), "created_by__")
        projects = self._real(
            all_labs(self.staff, Project).filter(deleted_at__isnull=True), "created_by__"
        )
        headline = {
            "total_users": users.filter(is_active=True).count(),
            "new_users": len(new_ids),
            "active_users": active_since(self.start),
            "labs_total": labs.count(),
            "labs_new": labs.filter(created_at__gte=start_at).count(),
            "projects_total": projects.count(),
            "dau": active_since(self.today),
            "wau": active_since(self.today - timedelta(days=6)),
            "mau": active_since(self.today - timedelta(days=29)),
        }
        return {
            "days": (self.today - self.start).days + 1,
            "include_test": self.include_test,
            "headline": headline,
            "daily": self._daily(start_at, new_ids, joined_day, pairs),
            "funnel": self._funnel(new_ids, joined_day, days_by_user),
            "features": self._features(start_at),
            "integrations": self._integrations(start_at),
            "recent_signups": self._recent(start_at, days_by_user),
            "retention": self._retention(joined_day, days_by_user),
        }

    def _daily(self, start_at, new_ids, joined_day, pairs):
        signups = Counter(joined_day[pk] for pk in new_ids)
        logins = dict(
            self._real(
                AuditEvent.objects.filter(
                    action=AuditAction.AUTH_LOGIN, occurred_at__gte=start_at, actor__isnull=False
                ),
                "actor__",
            )
            .annotate(day=TruncDate("occurred_at"))
            .values("day")
            .annotate(n=Count("pk"))
            .values_list("day", "n")
        )
        active = Counter(day for _, day in pairs)
        out = []
        day = self.start
        while day <= self.today:
            out.append(
                {
                    "date": day,
                    "signups": signups[day],
                    "sign_ins": logins.get(day, 0),
                    "active_users": active[day],
                }
            )
            day += timedelta(days=1)
        return out

    def _funnel(self, new_ids, joined_day, days_by_user):
        in_lab = all_labs(self.staff, LabMembership).filter(user__in=new_ids).values("user")
        made_project = all_labs(self.staff, Project).filter(created_by__in=new_ids)
        invited = AuditEvent.objects.filter(
            action=AuditAction.MEMBERSHIP_INVITED, actor__in=new_ids
        ).values("actor")
        came_back = sum(
            1 for pk in new_ids if any(d > joined_day[pk] for d in days_by_user.get(pk, ()))
        )
        steps = [
            ("signed_up", "Signed up", len(new_ids)),
            ("in_lab", "Joined or created a lab", in_lab.distinct().count()),
            (
                "project",
                "Created a project",
                made_project.values("created_by").distinct().count(),
            ),
            ("invited", "Invited someone", invited.distinct().count()),
            ("came_back", "Came back on a later day", came_back),
        ]
        total = len(new_ids)
        return [
            {
                "key": key,
                "label": label,
                "count": n,
                "percent": round(100 * n / total) if total else 0,
            }
            for key, label, n in steps
        ]

    def _features(self, start_at):
        whens = [
            When(action__startswith=prefix, then=Value(label))
            for label, source in FEATURES.items()
            if isinstance(source, tuple)
            for prefix in source
        ]
        audited = (
            self._real(
                AuditEvent.objects.filter(occurred_at__gte=start_at, actor__isnull=False),
                "actor__",
            )
            .annotate(feature=Case(*whens, default=Value(""), output_field=CharField()))
            .exclude(feature="")
            .values("feature")
            .annotate(events=Count("pk"), users=Count("actor", distinct=True))
        )
        counts = {r["feature"]: (r["events"], r["users"]) for r in audited}
        for label, source in FEATURES.items():
            if isinstance(source, str):
                qs, person, at = self.rows[source]
                qs = self._real(qs.filter(**{f"{at}__gte": start_at}), f"{person}__")
                r = qs.aggregate(events=Count("pk"), users=Count(person, distinct=True))
                counts[label] = (r["events"], r["users"])
        rows = []
        for label in FEATURES:
            events, people = counts.get(label, (0, 0))
            rows.append({"feature": label, "events": events, "users": people})
        return sorted(rows, key=lambda r: (-r["users"], -r["events"]))

    def _integrations(self, start_at):
        rows = (
            self._real(
                AuditEvent.objects.filter(
                    action=AuditAction.INTEGRATION_CONNECTED,
                    occurred_at__gte=start_at,
                    actor__isnull=False,
                ),
                "actor__",
            )
            .values("metadata__provider")
            .annotate(connections=Count("pk"), users=Count("actor", distinct=True))
            .order_by("-connections")
        )
        return [
            {
                "provider": str(r["metadata__provider"] or "other"),
                "connections": r["connections"],
                "users": r["users"],
            }
            for r in rows
        ]

    def _recent(self, start_at, days_by_user):
        first_lab = (
            all_labs(self.staff, LabMembership)
            .filter(user=OuterRef("pk"))
            .order_by("created_at")
            .values("lab__institution__name")[:1]
        )
        people = list(
            self._real(User.objects.filter(date_joined__gte=start_at))
            .annotate(labs=Count("labmembership", distinct=True), institution=Subquery(first_lab))
            .order_by("-date_joined")[:RECENT_LIMIT]
        )
        ids = [u.pk for u in people]
        events = Counter()
        for qs, person, _ in self._sources():
            for pk, n in (
                qs.filter(**{f"{person}__in": ids})
                .values(person)
                .annotate(n=Count("pk"))
                .values_list(person, "n")
            ):
                events[pk] += n
        return [
            {
                "id": u.pk,
                "display_name": u.display_name,
                "email": u.email,
                "institution": u.institution or "",
                "date_joined": u.date_joined,
                "labs": u.labs,
                "last_active": max(days_by_user[u.pk]) if days_by_user.get(u.pk) else None,
                "events": events[u.pk],
            }
            for u in people
        ]

    def _retention(self, joined_day, days_by_user):
        """Weekly sign-up cohorts (weeks start Monday): % active in each later week so far."""
        out = []
        for k in range(COHORT_WEEKS):
            week = self.cohort_start + timedelta(weeks=k)
            cohort = [pk for pk, d in joined_day.items() if week <= d < week + timedelta(days=7)]
            later = []
            for j in range(1, COHORT_WEEKS - k):
                lo = week + timedelta(weeks=j)
                hi = lo + timedelta(days=7)
                n = sum(1 for pk in cohort if any(lo <= d < hi for d in days_by_user.get(pk, ())))
                later.append(round(100 * n / len(cohort)) if cohort else None)
            out.append({"week_start": week, "users": len(cohort), "weeks": later})
        return out


# ---------------------------------------------------------------- response shape (schema only)


class SiteUsageHeadline(serializers.Serializer):
    total_users = serializers.IntegerField()
    new_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    labs_total = serializers.IntegerField()
    labs_new = serializers.IntegerField()
    projects_total = serializers.IntegerField()
    dau = serializers.IntegerField()
    wau = serializers.IntegerField()
    mau = serializers.IntegerField()


class SiteUsageDay(serializers.Serializer):
    date = serializers.DateField()
    signups = serializers.IntegerField()
    sign_ins = serializers.IntegerField()
    active_users = serializers.IntegerField()


class SiteUsageStep(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    percent = serializers.IntegerField()


class SiteUsageFeature(serializers.Serializer):
    feature = serializers.CharField()
    events = serializers.IntegerField()
    users = serializers.IntegerField()


class SiteUsageIntegration(serializers.Serializer):
    provider = serializers.CharField()
    connections = serializers.IntegerField()
    users = serializers.IntegerField()


class SiteUsageSignup(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()
    institution = serializers.CharField()
    date_joined = serializers.DateTimeField()
    labs = serializers.IntegerField()
    last_active = serializers.DateField(allow_null=True)
    events = serializers.IntegerField()


class SiteUsageCohort(serializers.Serializer):
    week_start = serializers.DateField()
    users = serializers.IntegerField()
    weeks = serializers.ListField(child=serializers.IntegerField(allow_null=True))


class SiteUsageSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    include_test = serializers.BooleanField()
    headline = SiteUsageHeadline()
    daily = SiteUsageDay(many=True)
    funnel = SiteUsageStep(many=True)
    features = SiteUsageFeature(many=True)
    integrations = SiteUsageIntegration(many=True)
    recent_signups = SiteUsageSignup(many=True)
    retention = SiteUsageCohort(many=True)


class UsageView(APIView):
    """D379: how people use the app, across every lab. Site staff only; others get 404."""

    perms = {"GET": Perm.SITE_STAFF}

    @extend_schema(
        operation_id="usage_retrieve",
        parameters=[
            OpenApiParameter("days", OpenApiTypes.INT, enum=[7, 30, 90], default=30),
            OpenApiParameter("include_test", OpenApiTypes.BOOL, default=False),
        ],
        responses=SiteUsageSerializer,
    )
    def get(self, request):
        days = request.query_params.get("days", "30")
        if days not in WINDOWS:
            raise serializers.ValidationError({"days": "Choose 7, 30 or 90 days."})
        include_test = request.query_params.get("include_test", "") in ("1", "true")
        data = Usage(request.user, int(days), include_test).build()
        # It shows people's names and emails across labs, so every look is on record.
        audit.record(
            AuditAction.SITE_USAGE_VIEWED,
            actor=request.user,
            lab=None,
            request=request,
            metadata={"days": int(days), "include_test": include_test},
        )
        return Response(SiteUsageSerializer(data).data)
