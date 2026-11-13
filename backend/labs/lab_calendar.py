"""The lab calendar: `GET L/calendar/?from=&to=` merges everything with a date.

Every source goes through `visible_to`, so a hidden project's items and a restricted ethics
approval never appear. Lab events are the only rows owned here; the rest link back to their source.
"""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, negotiation, serializers, status, views
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.auth import recent_auth_required
from core.permissions import Perm, get_lab_or_404
from core.serializers import SaneDateTimeField, no_control_chars
from core.tenancy import by_secret
from core.views import LabScopedViewMixin
from ethics.models import ApprovalStatus, EthicsApproval
from labs import admin_services as svc
from labs import video_calendar
from labs.models import (
    CalendarFeedToken,
    InventoryItem,
    InventoryStatus,
    LabEvent,
    Meeting,
    VideoProvider,
    hash_token,
)
from projects.models import ProjectDeadline, Task, TaskStatus
from provenance.models import FundingRecord, FundingStatus

MAX_RANGE = timedelta(days=92)  # a month grid is 42 days; this leaves room for a quarter view
KINDS = ("event", "meeting", "deadline", "task", "inventory", "ethics", "funding")
JOIN_HOSTS = ("zoom.us", "zoomgov.com", "meet.google.com")


class CalendarRangeSerializer(serializers.Serializer):
    to = serializers.DateField()
    mine = serializers.BooleanField(default=False, help_text="Only your own: D230.")

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
    notes = serializers.CharField(help_text="Lab events and meetings; empty for the rest.")
    starts_at = serializers.DateTimeField(allow_null=True, help_text="Meetings only.")
    ends_at = serializers.DateTimeField(allow_null=True, help_text="Meetings only.")
    join_url = serializers.CharField(help_text="Meetings only; may be empty.")
    video_provider = serializers.CharField(help_text="Meetings: google_meet, zoom or empty.")
    call_owner = serializers.UUIDField(
        allow_null=True, help_text="Meetings with a call: only this person may change it (D254)."
    )
    attendees = serializers.ListField(child=serializers.UUIDField())


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


def validate_join_url(value):
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise serializers.ValidationError("That is not a valid link.") from exc
    host = (parts.hostname or "").lower()
    known = any(host == h or host.endswith(f".{h}") for h in JOIN_HOSTS)
    if parts.scheme != "https" or parts.username or parts.password or not known:
        raise serializers.ValidationError("Paste a Zoom or Google Meet link starting with https://")


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = [
            "id",
            "title",
            "starts_at",
            "ends_at",
            "join_url",
            "notes",
            "attendees",
            "video_provider",
            "call_owner",
        ]
        read_only_fields = fields

    call_owner = serializers.SerializerMethodField()

    def get_call_owner(self, obj) -> str | None:
        return _call_owner(obj)


class MeetingInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    starts_at = SaneDateTimeField()
    ends_at = SaneDateTimeField()
    join_url = serializers.URLField(
        max_length=500, allow_blank=True, required=False, validators=[validate_join_url]
    )
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    attendees = serializers.ListField(child=serializers.UUIDField(), max_length=500, required=False)
    video = serializers.ChoiceField(
        choices=VideoProvider.choices,
        required=False,
        allow_blank=True,
        help_text="Make a Google Meet or Zoom call on your own account (D254). Only on create.",
    )


def _call_owner(meeting):
    account = meeting.video_account
    return str(account.user_id) if meeting.video_provider and account is not None else None


class GoogleEventSerializer(serializers.Serializer):
    """One of your own Google Calendar events, read live and never stored (D256)."""

    id = serializers.CharField()
    title = serializers.CharField()
    date = serializers.DateField()
    end_date = serializers.DateField(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    join_url = serializers.CharField()
    url = serializers.CharField(help_text="The event in Google Calendar; may be empty.")


class GoogleCalendarSyncSerializer(serializers.Serializer):
    connected = serializers.BooleanField()
    email = serializers.CharField(allow_blank=True)
    show_google_events = serializers.BooleanField()
    push_meetings = serializers.BooleanField()
    push_tasks = serializers.BooleanField()
    push_deadlines = serializers.BooleanField()
    last_synced_at = serializers.DateTimeField(allow_null=True)
    last_error = serializers.CharField(allow_blank=True)


class GoogleCalendarSyncInputSerializer(serializers.Serializer):
    show_google_events = serializers.BooleanField(required=False)
    push_meetings = serializers.BooleanField(required=False)
    push_tasks = serializers.BooleanField(required=False)
    push_deadlines = serializers.BooleanField(required=False)


class SyncResultSerializer(GoogleCalendarSyncSerializer):
    added = serializers.IntegerField()
    changed = serializers.IntegerField()
    removed = serializers.IntegerField()


class VideoOptionsSerializer(serializers.Serializer):
    """Which calls you can make now, and which could be made once connected."""

    google_meet = serializers.BooleanField()
    zoom = serializers.BooleanField()
    google_meet_available = serializers.BooleanField(
        help_text="Set up by the site, so connectable."
    )
    zoom_available = serializers.BooleanField()


class CalendarFeedStatusSerializer(serializers.Serializer):
    active = serializers.BooleanField()
    updated_at = serializers.DateTimeField(allow_null=True)


class CalendarFeedCreatedSerializer(CalendarFeedStatusSerializer):
    token = serializers.CharField(help_text="Shown once; only its hash is stored.")


def _item(
    kind,
    obj,
    title,
    date,
    project=None,
    *,
    end_date=None,
    done=False,
    notes="",
    starts_at=None,
    ends_at=None,
    join_url="",
    attendees=(),
):
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
        "starts_at": starts_at,
        "ends_at": ends_at,
        "join_url": join_url,
        "video_provider": "",
        "call_owner": None,
        "attendees": attendees,
    }


def _meeting_item(m):
    # `date` is the viewer's day (D291); the browser re-files it from `starts_at` as well.
    item = _item(
        "meeting",
        m,
        m.title,
        timezone.localdate(m.starts_at),
        notes=m.notes,
        starts_at=m.starts_at,
        ends_at=m.ends_at,
        join_url=m.join_url,
        attendees=[u.pk for u in m.attendees.all()],
    )
    item.update(video_provider=m.video_provider, call_owner=_call_owner(m))
    return item


def build_calendar(user, lab, start, end, *, mine=False) -> list[dict]:
    """Everything dated that `user` may see. `mine` narrows it to their own (D230): meetings they
    are on, tasks assigned to them and the deadlines of projects they belong to."""
    window = (start, end)
    day = timedelta(days=1)
    deadlines = ProjectDeadline.objects.visible_to(user, lab).filter(due_date__range=window)
    tasks = Task.objects.visible_to(user, lab).filter(due_date__range=window)
    if mine:
        deadlines = deadlines.filter(project__memberships__user=user)
        tasks = tasks.filter(assignee=user)
    items = [
        _meeting_item(m)
        for m in Meeting.objects.visible_to(user, lab)
        .filter(starts_at__date__range=(start - day, end + day))  # a local day can be either side
        .select_related("video_account")
        .prefetch_related("attendees")
    ]
    items += [
        _item("deadline", d, d.title, d.due_date, d.project, done=d.done)
        for d in deadlines.select_related("project")
    ]
    items += [
        _item("task", t, t.title, t.due_date, t.project, done=t.status == TaskStatus.DONE)
        for t in tasks.select_related("project")
    ]
    if not mine:
        items += _lab_wide_items(user, lab, start, end)
    items.sort(key=lambda i: (i["date"], str(i["starts_at"] or ""), i["title"]))
    return items


def _lab_wide_items(user, lab, start, end) -> list[dict]:
    window = (start, end)
    items = [
        _item("event", e, e.title, e.date, end_date=e.end_date, notes=e.notes)
        for e in LabEvent.objects.visible_to(user, lab).filter(
            Q(end_date__gte=start) | Q(end_date__isnull=True, date__gte=start), date__lte=end
        )
    ]
    if lab.inventory_enabled:  # D227
        items += [
            _item("inventory", i, f"{i.name} (maintenance due)", i.due_date)
            for i in InventoryItem.objects.visible_to(user, lab).filter(
                due_date__range=window,
                status__in=(InventoryStatus.ACTIVE, InventoryStatus.IN_REPAIR),
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
        data = ser.validated_data
        rows = build_calendar(
            request.user, request.lab, data["from"], data["to"], mine=data["mine"]
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


class MeetingMixin(LabScopedViewMixin):
    model = Meeting
    serializer_class = MeetingSerializer
    pagination_class = None

    def body(self, *, partial=False):
        ser = MeetingInputSerializer(data=self.request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        return ser.validated_data


class MeetingCreateView(MeetingMixin, generics.GenericAPIView):
    perms = {"POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=MeetingInputSerializer, responses={201: MeetingSerializer})
    def post(self, request, lab_id):
        meeting = svc.create_meeting(
            lab=request.lab, user=request.user, data=self.body(), request=request
        )
        return Response(self.get_serializer(meeting).data, status=status.HTTP_201_CREATED)


class MeetingDetailView(MeetingMixin, generics.GenericAPIView):
    """Anyone on the meeting who may add lab content can change it; it is a 404 for anyone else."""

    lookup_url_kwarg = "meeting_id"
    perms = {"PATCH": Perm.CONTRIBUTE_LAB, "DELETE": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=MeetingInputSerializer, responses=MeetingSerializer)
    def patch(self, request, lab_id, meeting_id):
        meeting = svc.update_meeting(
            self.get_object(), user=request.user, data=self.body(partial=True), request=request
        )
        return Response(self.get_serializer(meeting).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, meeting_id):
        svc.delete_meeting(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- Google Calendar (D255, D256)


def _sync_data(sync) -> dict:
    if sync is None:
        return {
            "connected": False,
            "email": "",
            "show_google_events": False,
            "push_meetings": False,
            "push_tasks": False,
            "push_deadlines": False,
            "last_synced_at": None,
            "last_error": "",
        }
    return {
        "connected": True,
        "email": sync.account.external_email,
        "show_google_events": sync.show_google_events,
        "push_meetings": sync.push_meetings,
        "push_tasks": sync.push_tasks,
        "push_deadlines": sync.push_deadlines,
        "last_synced_at": sync.last_synced_at,
        "last_error": sync.last_error,
    }


class GoogleEventsView(LabScopedViewMixin, generics.GenericAPIView):
    """Your own Google events for the calendar; [] when not connected or switched off."""

    serializer_class = GoogleEventSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(parameters=[CalendarRangeSerializer], responses=GoogleEventSerializer(many=True))
    def get(self, request, lab_id):
        ser = CalendarRangeSerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        rows = video_calendar.google_events(
            request.lab, request.user, ser.validated_data["from"], ser.validated_data["to"]
        )
        return Response(self.get_serializer(rows, many=True).data)


class GoogleCalendarSyncView(LabScopedViewMixin, generics.GenericAPIView):
    """Your own Google Calendar settings in this lab. `connected` is false until you connect."""

    serializer_class = GoogleCalendarSyncSerializer
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_INTEGRATIONS}

    @extend_schema(responses=GoogleCalendarSyncSerializer)
    def get(self, request, lab_id):
        return Response(_sync_data(video_calendar.sync_for(request.lab, request.user)))

    @extend_schema(
        request=GoogleCalendarSyncInputSerializer, responses=GoogleCalendarSyncSerializer
    )
    def patch(self, request, lab_id):
        sync = video_calendar.sync_for(request.lab, request.user)
        if sync is None:  # not connected: nothing to change; the answer says so
            return Response(_sync_data(None))
        ser = GoogleCalendarSyncInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        for key, value in ser.validated_data.items():
            setattr(sync, key, value)
        sync.save()
        return Response(_sync_data(sync))


class GoogleCalendarSyncRunView(LabScopedViewMixin, generics.GenericAPIView):
    """Sync now, instead of waiting for the next 15-minute run."""

    serializer_class = SyncResultSerializer
    perms = {"POST": Perm.MANAGE_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "calendar_sync"

    @extend_schema(request=None, responses=SyncResultSerializer)
    def post(self, request, lab_id):
        sync = video_calendar.sync_for(request.lab, request.user)
        if sync is None:
            return Response({**_sync_data(None), "added": 0, "changed": 0, "removed": 0})
        counts = video_calendar.push(sync)
        return Response({**_sync_data(sync), **counts})


class VideoOptionsView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = VideoOptionsSerializer
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=VideoOptionsSerializer)
    def get(self, request, lab_id):
        out = {}
        for key, provider in video_calendar.PROVIDER_OF.items():
            out[key] = (
                video_calendar.active_account(request.lab, request.user, provider.name) is not None
            )
            out[f"{key}_available"] = provider.configured
        return Response(out)


# ---------------------------------------------------------------- .ics feeds (D231)

FEED_PAST = timedelta(days=90)
FEED_FUTURE = timedelta(days=366)


class CalendarFeedTokenView(LabScopedViewMixin, generics.GenericAPIView):
    """Your own secret link for this lab. Viewers may subscribe too: the feed is read-only."""

    model = CalendarFeedToken
    serializer_class = CalendarFeedStatusSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB, "DELETE": Perm.VIEW_LAB}

    @extend_schema(responses=CalendarFeedStatusSerializer)
    def get(self, request, lab_id):
        feed = self.get_queryset().first()
        data = {"active": feed is not None, "updated_at": feed.updated_at if feed else None}
        return Response(self.get_serializer(data).data)

    @extend_schema(request=None, responses={201: CalendarFeedCreatedSerializer})
    def post(self, request, lab_id):
        stale = recent_auth_required(request)  # D194: a link that reads your calendar is a secret
        if stale:
            return stale
        feed, token = svc.issue_calendar_feed(lab=request.lab, user=request.user, request=request)
        data = {"active": True, "updated_at": feed.updated_at, "token": token}
        return Response(CalendarFeedCreatedSerializer(data).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, lab_id):
        feed = self.get_queryset().first()
        if feed is not None:
            svc.revoke_calendar_feed(feed, user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _ics_escape(value) -> str:
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value))  # keeps tabs and newlines
    for char, escaped in (("\\", "\\\\"), (";", "\\;"), (",", "\\,"), ("\n", "\\n")):
        text = text.replace(char, escaped)
    return text


def _ics_fold(line: str) -> str:
    """RFC 5545: lines of at most 75 octets, continued with a leading space, never mid-character."""
    parts, current, size = [], "", 0
    for char in line:
        width = len(char.encode())
        if size + width > 74:
            parts.append(current)
            current, size = "", 0
        current += char
        size += width
    return "\r\n ".join([*parts, current])


def _ics_stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ics_event(item, now) -> list[str]:
    join = item["join_url"]
    project = f"Project: {item['project_name']}" if item["project_name"] else ""
    details = "\n".join(filter(None, [project, join]))
    lines = [
        "BEGIN:VEVENT",
        f"UID:{item['kind']}-{item['id']}@labbenchos",
        f"DTSTAMP:{_ics_stamp(now)}",
        f"SUMMARY:{_ics_escape(item['title'])}",
    ]
    if item["starts_at"]:
        lines += [
            f"DTSTART:{_ics_stamp(item['starts_at'])}",
            f"DTEND:{_ics_stamp(item['ends_at'])}",
        ]
    else:
        last = item["end_date"] or item["date"]
        lines += [  # an all-day DTEND is the day after the last day
            f"DTSTART;VALUE=DATE:{item['date']:%Y%m%d}",
            f"DTEND;VALUE=DATE:{last + timedelta(days=1):%Y%m%d}",
        ]
    if details:
        lines.append(f"DESCRIPTION:{_ics_escape(details)}")
    return [*lines, "END:VEVENT"]


def render_ics(name: str, items: list[dict]) -> str:
    now = timezone.now()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//labbenchos//calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(name)}",
    ]
    for item in items:
        if not item["done"]:  # finished work drops off the subscribed calendar
            lines += _ics_event(item, now)
    lines.append("END:VCALENDAR")
    return "".join(f"{_ics_fold(line)}\r\n" for line in lines)


class AnyAccept(negotiation.BaseContentNegotiation):
    """Calendar apps send `Accept: text/calendar`, which would otherwise be a 406."""

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class CalendarIcsView(views.APIView):
    """`GET /api/calendar.ics?token=<secret>[&mine=1]`, for calendar apps (D231). The token is the
    only credential and it sits in the query string on purpose: nothing logs query strings.
    Its owner's access is re-read on every fetch, through the same `build_calendar` as the app."""

    authentication_classes = []  # a browser session must not stand in for the token
    content_negotiation_class = AnyAccept
    perms = {"GET": Perm.PUBLIC}

    @extend_schema(exclude=True)
    def get(self, request):
        token = request.query_params.get("token", "")
        feed = (
            by_secret(CalendarFeedToken)
            .filter(token_hash=hash_token(token))
            .select_related("user")
            .first()
        )
        if feed is None:
            return HttpResponse(status=401)
        lab = get_lab_or_404(feed.user, feed.lab_id)  # 404 once they have left or are deactivated
        mine = request.query_params.get("mine") == "1"
        today = timezone.localdate()  # UTC: a feed has no session; the window is weeks wide
        items = build_calendar(feed.user, lab, today - FEED_PAST, today + FEED_FUTURE, mine=mine)
        # D244: a subscribed calendar copies this to another company, so funding never goes
        items = [i for i in items if i["kind"] != "funding"]
        body = render_ics(f"{lab.name} ({'mine' if mine else 'lab'})", items)
        return HttpResponse(
            body,
            content_type="text/calendar; charset=utf-8",
            headers={"Cache-Control": "private, no-store"},
        )
