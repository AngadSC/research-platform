import uuid
from datetime import timedelta

from django.db.models import Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, negotiation, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.auth import recent_auth_required
from core.permissions import Perm
from core.views import LabScopedViewMixin
from monitoring import services as svc
from monitoring.models import Sensor, SensorAlert
from monitoring.serializers import (
    AcknowledgeSerializer,
    SensorAlertSerializer,
    SensorDetailSerializer,
    SensorInputSerializer,
    SensorSerializer,
    SensorTokenSerializer,
    TestReadingSerializer,
)

SPARK = (timedelta(hours=24), timedelta(minutes=20))
WEEK = (timedelta(days=7), timedelta(hours=1))
HISTORY = 50


def _body(serializer_class, request, partial=False):
    ser = serializer_class(data=request.data, partial=partial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


class SensorMixin(LabScopedViewMixin):
    model = Sensor
    serializer_class = SensorSerializer
    pagination_class = None
    lookup_url_kwarg = "sensor_id"
    needs_inventory = True  # D227: monitoring is off with inventory

    def get_queryset(self):
        attention = (
            SensorAlert.objects.visible_to(self.request.user, self.request.lab)
            .filter(Q(ended_at__isnull=True) | Q(acknowledged_at__isnull=True))
            .select_related("acknowledged_by")
            .order_by("-started_at")
        )
        return (
            super()
            .get_queryset()
            .select_related("item")
            .prefetch_related(
                "recipients", Prefetch("alerts", queryset=attention, to_attr="attention")
            )
            .order_by("name", "id")
        )

    def detail(self, sensor, code=status.HTTP_200_OK):
        sensor = self.get_queryset().get(pk=sensor.pk)  # fresh, with its open alerts
        since, step = WEEK
        history = (
            SensorAlert.objects.visible_to(self.request.user, self.request.lab)
            .filter(sensor=sensor)
            .select_related("acknowledged_by")
            .order_by("-started_at")[:HISTORY]
        )
        context = {
            "series": svc.series([sensor.pk], timezone.now() - since, step),
            "history": list(history),
        }
        return Response(SensorDetailSerializer(sensor, context=context).data, status=code)


class SensorListView(SensorMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_INVENTORY}

    @extend_schema(
        parameters=[OpenApiParameter("item", OpenApiTypes.UUID, description="Only this item's")],
        responses=SensorSerializer(many=True),
    )
    def get(self, request, lab_id):
        sensors = self.get_queryset()
        if item := request.query_params.get("item"):
            sensors = sensors.filter(item_id=item) if _is_uuid(item) else sensors.none()
        sensors = list(sensors)
        since, step = SPARK
        context = {"series": svc.series([s.pk for s in sensors], timezone.now() - since, step)}
        return Response(SensorSerializer(sensors, many=True, context=context).data)

    @extend_schema(request=SensorInputSerializer, responses={201: SensorDetailSerializer})
    def post(self, request, lab_id):
        sensor = svc.create_sensor(
            lab=request.lab,
            user=request.user,
            data=_body(SensorInputSerializer, request),
            request=request,
        )
        return self.detail(sensor, status.HTTP_201_CREATED)


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


class SensorDetailView(SensorMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_INVENTORY, "DELETE": Perm.MANAGE_INVENTORY}

    @extend_schema(responses=SensorDetailSerializer)
    def get(self, request, lab_id, sensor_id):
        return self.detail(self.get_object())

    @extend_schema(request=SensorInputSerializer, responses=SensorDetailSerializer)
    def patch(self, request, lab_id, sensor_id):
        sensor = svc.update_sensor(
            self.get_object(),
            user=request.user,
            data=_body(SensorInputSerializer, request, partial=True),
            request=request,
        )
        return self.detail(sensor)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, sensor_id):
        svc.delete_sensor(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SensorTokenView(SensorMixin, generics.GenericAPIView):
    """The device's secret. Making one needs a recent sign-in (D194); it is shown once."""

    perms = {"POST": Perm.MANAGE_INVENTORY, "DELETE": Perm.MANAGE_INVENTORY}

    @extend_schema(request=None, responses={201: SensorTokenSerializer})
    def post(self, request, lab_id, sensor_id):
        sensor = self.get_object()
        stale = recent_auth_required(request)
        if stale:
            return stale
        token = svc.issue_token(sensor, user=request.user, request=request)
        data = {"token": token, "token_created_at": sensor.token_created_at}
        return Response(SensorTokenSerializer(data).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, lab_id, sensor_id):
        svc.revoke_token(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SensorTestReadingView(SensorMixin, generics.GenericAPIView):
    """Check the wiring: a reading that is kept and audited but never judged, so it cannot raise
    or end an alert, change the latest value or show on a chart (D383)."""

    perms = {"POST": Perm.MANAGE_INVENTORY}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensor_test"

    @extend_schema(request=TestReadingSerializer, responses=SensorDetailSerializer)
    def post(self, request, lab_id, sensor_id):
        sensor = self.get_object()
        value = _body(TestReadingSerializer, request)["value"]
        svc.record_test_reading(sensor, value, user=request.user, request=request)
        return self.detail(sensor)


class AlertAcknowledgeView(LabScopedViewMixin, generics.GenericAPIView):
    model = SensorAlert
    serializer_class = SensorAlertSerializer
    lookup_url_kwarg = "sensoralert_id"
    needs_inventory = True
    perms = {"POST": Perm.MANAGE_INVENTORY}

    @extend_schema(request=AcknowledgeSerializer, responses=SensorAlertSerializer)
    def post(self, request, lab_id, sensoralert_id):
        note = _body(AcknowledgeSerializer, request)["note"]
        alert = svc.acknowledge(self.get_object(), user=request.user, note=note, request=request)
        return Response(SensorAlertSerializer(alert).data)


def _error(message, code):
    return JsonResponse({"error": message}, status=code)


MAX_BODY = 4096  # a reading is a few dozen bytes; anything bigger is not a device


class DeviceNegotiation(negotiation.DefaultContentNegotiation):
    """Devices send odd Accept headers, or none, and sometimes the wrong Content-Type: answer in
    JSON whatever they ask, and read a body by its type (JSON or a form), JSON when unsure."""

    def select_parser(self, request, parsers):
        return super().select_parser(request, parsers) or parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class IngestView(APIView):
    """`POST /api/sensors/ingest/` with `Authorization: Bearer <token>` and `{"value": -79.4,
    "at": optional ISO time}`, or `GET ?token=&value=` for devices that can only call a URL
    (Shelly webhooks). The device token is the only credential: no session, no CSRF. It can write
    one reading to its own sensor and read nothing. A token in a URL can end up in proxy and
    router logs, so POST with the header is preferred wherever the device allows it."""

    authentication_classes = []  # a browser session must never stand in for the token
    content_negotiation_class = DeviceNegotiation
    parser_classes = [JSONParser, FormParser]
    perms = {"GET": Perm.PUBLIC, "POST": Perm.PUBLIC}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sensor_ingest"

    @extend_schema(exclude=True)
    def get(self, request):
        return self._take(request, request.query_params)

    @extend_schema(exclude=True)
    def post(self, request):
        return self._take(request, None)

    def _body(self, request):
        """The small body as a dict, or a 400/413 answer. Nothing is parsed before the length
        is known, so a huge or deeply nested body never reaches a parser."""
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return _error("Send a valid Content-Length.", 400)
        if length > MAX_BODY or len(request._request.body) > MAX_BODY:  # no length: read a little
            return _error(f"The body is too large. Send at most {MAX_BODY} bytes.", 413)
        try:
            data = request.data
        except (APIException, RecursionError, ValueError):
            return _error('Send JSON like {"value": -79.4}, or a form.', 400)
        return data if isinstance(data, dict) else {}

    def _take(self, request, data):
        auth = request.headers.get("Authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
        token = token or request.query_params.get("token", "")
        if data is None:  # POST: look the token up from the URL or header before any parsing
            sensor = svc.sensor_for_token(token)
            if token and sensor is None:
                return _error("Unknown or revoked token.", 401)
            data = self._body(request)
            if isinstance(data, JsonResponse):
                return data
            if sensor is None:  # a device that cannot set headers may send it in the body
                token = data.get("token") if isinstance(data.get("token"), str) else ""
                sensor = svc.sensor_for_token(token)
        else:
            sensor = svc.sensor_for_token(token)
        if sensor is None:
            return _error("Unknown or revoked token.", 401)
        if not sensor.lab.inventory_enabled:  # D227
            return _error("Monitoring is turned off for this lab.", 403)
        if not svc.take_slot(sensor):
            return _error(f"Too many readings. At most {svc.RATE_PER_MINUTE} a minute.", 429)
        try:
            value, at = svc.clean_reading(data.get("value"), data.get("at"), timezone.now())
        except ValueError as exc:
            return _error(str(exc), 400)
        svc.record_reading(sensor, value, at)
        return HttpResponse(status=204)
