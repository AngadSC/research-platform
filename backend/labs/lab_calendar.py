"""The lab calendar: `GET L/calendar/?from=&to=` merges everything with a date.

Every source goes through `visible_to`, so a hidden project's items and a restricted ethics
approval never appear. Lab events are the only rows owned here; the rest link back to their source.
"""

from datetime import timedelta

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from core.permissions import Perm
from core.serializers import no_control_chars
from core.views import LabScopedViewMixin
from ethics.models import ApprovalStatus, EthicsApproval
from labs import admin_services as svc
from labs.models import InventoryItem, InventoryStatus, LabEvent
from projects.models import ProjectDeadline, Task, TaskStatus
from provenance.models import FundingRecord, FundingStatus

MAX_RANGE = timedelta(days=92)  # a month grid is 42 days; this leaves room for a quarter view
KINDS = ("event", "deadline", "task", "inventory", "ethics", "funding")


class CalendarRangeSerializer(serializers.Serializer):
    to = serializers.DateField()

    def get_fields(self):  # `from` is a Python keyword, so it can't be a class attribute
        return {"from": serializers.DateField(), **super().get_fields()}

    def validate(self, data):
        if data["to"] < data["from"]:
            raise serializers.ValidationError({"to": "The end is before the start."})
        if data["to"] - data["from"] > MAX_RANGE:
            raise serializers.ValidationError({"to": f"At most {MAX_RANGE.days} days at a time."})
        return data


class CalendarItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=KINDS)
    id = serializers.UUIDField()
    title = serializers.CharField()
    date = serializers.DateField()
    end_date = serializers.DateField(allow_null=True)
    project_id = serializers.UUIDField(allow_null=True)
    project_name = serializers.CharField(allow_null=True)
    project_color = serializers.CharField(allow_null=True)
    done = serializers.BooleanField()
    notes = serializers.CharField(help_text="Lab events only; empty for everything else.")


class LabEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabEvent
        fields = ["id", "title", "date", "end_date", "notes", "created_at", "updated_at"]
        read_only_fields = fields


class LabEventInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    date = serializers.DateField()
    end_date = serializers.DateField(allow_null=True, required=False)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)


def _item(kind, obj, title, date, project=None, *, end_date=None, done=False, notes=""):
    return {
        "kind": kind,
        "id": obj.pk,
        "title": title,
        "date": date,
        "end_date": end_date,
        "project_id": project.pk if project else None,
        "project_name": project.name if project else None,
        "project_color": project.color if project else None,
        "done": done,
        "notes": notes,
    }


def build_calendar(user, lab, start, end) -> list[dict]:
    window = (start, end)
    items = [
        _item("event", e, e.title, e.date, end_date=e.end_date, notes=e.notes)
        for e in LabEvent.objects.visible_to(user, lab).filter(
            Q(end_date__gte=start) | Q(end_date__isnull=True, date__gte=start), date__lte=end
        )
    ]
    items += [
        _item("deadline", d, d.title, d.due_date, d.project, done=d.done)
        for d in ProjectDeadline.objects.visible_to(user, lab)
        .filter(due_date__range=window)
        .select_related("project")
    ]
    items += [
        _item("task", t, t.title, t.due_date, t.project, done=t.status == TaskStatus.DONE)
        for t in Task.objects.visible_to(user, lab)
        .filter(due_date__range=window)
        .select_related("project")
    ]
    items += [
        _item("inventory", i, f"{i.name} (maintenance due)", i.due_date)
        for i in InventoryItem.objects.visible_to(user, lab).filter(
            due_date__range=window, status__in=(InventoryStatus.ACTIVE, InventoryStatus.IN_REPAIR)
        )
    ]
    items += [
        _item("ethics", a, f"{a.title} (ethics expires)", a.expiry_date)
        for a in EthicsApproval.objects.visible_to(user, lab)
        .filter(deleted_at__isnull=True, expiry_date__range=window)
        .exclude(status=ApprovalStatus.WITHDRAWN)
    ]
    items += [
        _item("funding", f, f"{f.funder} (funding ends)", f.end_date, f.project)
        for f in FundingRecord.objects.visible_to(user, lab)
        .filter(end_date__range=window, status__in=(FundingStatus.AWARDED, FundingStatus.ACTIVE))
        .select_related("project")
    ]
    items.sort(key=lambda i: (i["date"], i["title"]))
    return items


class CalendarView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = CalendarItemSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(
        parameters=[CalendarRangeSerializer], responses=CalendarItemSerializer(many=True)
    )
    def get(self, request, lab_id):
        ser = CalendarRangeSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        rows = build_calendar(
            request.user, request.lab, ser.validated_data["from"], ser.validated_data["to"]
        )
        return Response(self.get_serializer(rows, many=True).data)


class LabEventMixin(LabScopedViewMixin):
    model = LabEvent
    serializer_class = LabEventSerializer
    pagination_class = None

    def body(self, *, partial=False):
        ser = LabEventInputSerializer(data=self.request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        return ser.validated_data


class LabEventCreateView(LabEventMixin, generics.GenericAPIView):
    perms = {"POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=LabEventInputSerializer, responses={201: LabEventSerializer})
    def post(self, request, lab_id):
        event = svc.create_lab_event(
            lab=request.lab, user=request.user, data=self.body(), request=request
        )
        return Response(self.get_serializer(event).data, status=status.HTTP_201_CREATED)


class LabEventDetailView(LabEventMixin, generics.GenericAPIView):
    lookup_url_kwarg = "labevent_id"
    perms = {"PATCH": Perm.CONTRIBUTE_LAB, "DELETE": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=LabEventInputSerializer, responses=LabEventSerializer)
    def patch(self, request, lab_id, labevent_id):
        event = svc.update_lab_event(
            self.get_object(), user=request.user, data=self.body(partial=True), request=request
        )
        return Response(self.get_serializer(event).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, labevent_id):
        svc.delete_lab_event(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
