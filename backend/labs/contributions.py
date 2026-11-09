"""Contribution graph for the PI dashboard: `GET L/contributions/?user=<id>`.

A year of daily activity counts, like GitHub's contribution calendar, for the whole lab or one
member. Counted from the records people make (document edits, files, tasks, task updates, chat
messages and research records), never from the audit log, so viewing something does not count.

Every query goes through `visible_to`, so activity in a project the requester cannot open is
never counted. The query count is fixed: one per source, whatever the lab's size.
"""

import uuid
from datetime import datetime, time, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.permissions import Perm
from core.views import LabScopedViewMixin
from documents.models import Attachment, DocumentRevision
from ethics.models import EthicsApproval
from labs.models import LabMembership
from projects.models import ChatMessage, Project, Task, TaskPost
from provenance.models import (
    Analysis,
    DataManagementPlanRevision,
    DatasetRecord,
    Decision,
    FundingRecord,
    ManuscriptLink,
    RecruitmentEntry,
    Result,
    ReviewItem,
)

WEEKS = 53  # the grid: 52 full weeks back plus the current one, Sunday first

KINDS = ("documents", "files", "tasks", "task_updates", "chat", "records")

# (kind, model, user field, what one contribution is). Documents count each document edited
# that day once, so an autosave-heavy session reads as one edit, not dozens.
SOURCES = (
    ("documents", DocumentRevision, "created_by", "document"),
    ("files", Attachment, "uploaded_by", "id"),
    ("tasks", Task, "created_by", "id"),
    ("task_updates", TaskPost, "author", "id"),
    ("chat", ChatMessage, "author", "id"),
    ("records", Project, "created_by", "id"),
    ("records", DatasetRecord, "created_by", "id"),
    ("records", Analysis, "ran_by", "id"),
    ("records", Result, "created_by", "id"),
    ("records", Decision, "decided_by", "id"),
    ("records", ManuscriptLink, "created_by", "id"),
    ("records", FundingRecord, "created_by", "id"),
    ("records", ReviewItem, "created_by", "id"),
    ("records", RecruitmentEntry, "created_by", "id"),
    ("records", DataManagementPlanRevision, "created_by", "id"),
    ("records", EthicsApproval, "created_by", "id"),
)


def grid_start(today):
    """The Sunday that starts the first column, so the last column holds today."""
    sunday_this_week = today - timedelta(days=(today.weekday() + 1) % 7)
    return sunday_this_week - timedelta(weeks=WEEKS - 1)


def build_contributions(user, lab, person=None) -> dict:
    today = timezone.localdate()
    start = grid_start(today)
    since = timezone.make_aware(datetime.combine(start, time.min))

    per_day: dict = {}
    for kind, model, field, unit in SOURCES:
        qs = model.objects.visible_to(user, lab).filter(created_at__gte=since)
        qs = qs.filter(**{field: person}) if person else qs.filter(**{f"{field}__isnull": False})
        rows = (
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(n=Count(unit, distinct=unit != "id"))
        )
        for r in rows:
            day = per_day.setdefault(r["day"], dict.fromkeys(KINDS, 0))
            day[kind] += r["n"]

    days = [
        {"date": d, "count": sum(k.values()), "by_kind": k}
        for d, k in sorted(per_day.items())
        if start <= d <= today
    ]
    totals = dict.fromkeys(KINDS, 0)
    for d in days:
        for k, n in d["by_kind"].items():
            totals[k] += n
    return {
        "start": start,
        "end": today,
        "user_id": person.pk if person else None,
        "total": sum(totals.values()),
        "by_kind": totals,
        "days": days,
    }


# ---------------------------------------------------------------- response shape (schema only)


class ContributionKindsSerializer(serializers.Serializer):
    documents = serializers.IntegerField(help_text="Documents edited (each document once a day).")
    files = serializers.IntegerField(help_text="Files uploaded.")
    tasks = serializers.IntegerField(help_text="Tasks created.")
    task_updates = serializers.IntegerField(help_text="Updates posted on tasks.")
    chat = serializers.IntegerField(help_text="Project chat messages.")
    records = serializers.IntegerField(
        help_text="Projects, datasets, analyses, results, decisions, manuscripts, funding, "
        "reviews, recruitment entries, data management plan edits and ethics approvals."
    )


class ContributionDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField()
    by_kind = ContributionKindsSerializer()


class ContributionsSerializer(serializers.Serializer):
    start = serializers.DateField(help_text="A Sunday; the first day of the grid.")
    end = serializers.DateField(help_text="Today, the last day of the grid.")
    user_id = serializers.UUIDField(allow_null=True, help_text="Null for the whole lab.")
    total = serializers.IntegerField()
    by_kind = ContributionKindsSerializer()
    days = ContributionDaySerializer(many=True, help_text="Only days with activity, oldest first.")


class ContributionsView(LabScopedViewMixin, generics.GenericAPIView):
    """A year of daily activity counts for the whole lab or one member (the contribution graph)."""

    serializer_class = ContributionsSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_LAB}  # same audience as the dashboard (D170)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "user", str, description="A lab member's id. Leave out for the whole lab."
            )
        ],
        responses=ContributionsSerializer,
    )
    def get(self, request, lab_id):
        person = None
        raw = request.query_params.get("user")
        if raw:
            membership = (
                LabMembership.objects.for_lab(request.lab)
                .select_related("user")
                .filter(user_id=_uuid(raw))
                .first()
            )
            if membership is None:
                raise ValidationError({"user": "Not a member of this lab."})
            person = membership.user
        data = build_contributions(request.user, request.lab, person)
        return Response(ContributionsSerializer(data).data)


def _uuid(raw):
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationError({"user": "Not a valid id."}) from exc
