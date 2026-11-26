import math

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from monitoring.models import SYMBOL, AlertKind, Sensor, SensorAlert, Unit
from monitoring.services import VALUE_RANGE, member_ids


def _finite(value):
    if not math.isfinite(value):
        raise serializers.ValidationError("Enter a number.")


def _number(**kw):
    lo, hi = VALUE_RANGE
    return serializers.FloatField(min_value=lo, max_value=hi, validators=[_finite], **kw)


class PointSerializer(serializers.Serializer):
    t = serializers.DateTimeField()
    min = serializers.FloatField()
    max = serializers.FloatField()
    avg = serializers.FloatField()


class ItemRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class SensorAlertSerializer(serializers.ModelSerializer):
    acknowledged_by = UserSerializer(read_only=True)

    class Meta:
        model = SensorAlert
        fields = [
            "id",
            "kind",
            "value",
            "peak",
            "started_at",
            "ended_at",
            "acknowledged_by",
            "acknowledged_at",
            "note",
        ]
        read_only_fields = fields


STATUS = serializers.ChoiceField(
    choices=["ok", "out_of_range", "silent", "waiting", "paused"],
    help_text="waiting: no reading yet; paused: not active.",
)


class SensorSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()
    recipients = serializers.SerializerMethodField(
        help_text="The people picked on the sensor who are still in the lab."
    )
    unit_symbol = serializers.SerializerMethodField()
    has_token = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    alert = serializers.SerializerMethodField(
        help_text="The latest alert still open or not yet acknowledged."
    )
    series = serializers.SerializerMethodField(
        help_text="The last 24 hours in 20-minute steps (list) or 7 days in hours (detail)."
    )

    class Meta:
        model = Sensor
        fields = [
            "id",
            "name",
            "item",
            "unit",
            "unit_symbol",
            "low_limit",
            "high_limit",
            "silent_after_minutes",
            "recipients",
            "active",
            "has_token",
            "token_created_at",
            "last_value",
            "last_at",
            "status",
            "alert",
            "series",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(ItemRefSerializer(allow_null=True))
    def get_item(self, s):
        return {"id": s.item.pk, "name": s.item.name} if s.item else None

    @extend_schema_field(UserSerializer(many=True))
    def get_recipients(self, s):
        # D383: someone who left the lab is not shown (name and email) to the people who stay
        members = self.__dict__.setdefault("_members", {})
        if s.lab_id not in members:
            members[s.lab_id] = member_ids(s.lab_id)
        kept = [u for u in s.recipients.all() if u.is_active and u.pk in members[s.lab_id]]
        return UserSerializer(kept, many=True).data

    def get_unit_symbol(self, s) -> str:
        return SYMBOL.get(s.unit, "").strip()

    def get_has_token(self, s) -> bool:
        return s.token_hash is not None

    def _attention(self, s):
        return getattr(s, "attention", [])

    @extend_schema_field(STATUS)
    def get_status(self, s):
        if not s.active:
            return "paused"
        if s.last_at is None:
            return "waiting"
        kinds = {a.kind for a in self._attention(s) if a.ended_at is None}
        if AlertKind.SILENT in kinds:
            return "silent"
        return "out_of_range" if kinds else "ok"

    @extend_schema_field(SensorAlertSerializer(allow_null=True))
    def get_alert(self, s):
        alerts = self._attention(s)
        return SensorAlertSerializer(alerts[0]).data if alerts else None

    @extend_schema_field(PointSerializer(many=True))
    def get_series(self, s):
        return PointSerializer(self.context.get("series", {}).get(s.pk, []), many=True).data


class SensorDetailSerializer(SensorSerializer):
    history = serializers.SerializerMethodField(help_text="The last 50 alerts, newest first.")

    class Meta(SensorSerializer.Meta):
        fields = [*SensorSerializer.Meta.fields, "history"]
        read_only_fields = fields

    @extend_schema_field(SensorAlertSerializer(many=True))
    def get_history(self, s):
        return SensorAlertSerializer(self.context.get("history", []), many=True).data


class SensorInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    item = serializers.UUIDField(allow_null=True, required=False)
    unit = serializers.ChoiceField(choices=Unit.choices, required=False)
    low_limit = _number(allow_null=True, required=False)
    high_limit = _number(allow_null=True, required=False)
    silent_after_minutes = serializers.IntegerField(
        min_value=5, max_value=7 * 24 * 60, required=False
    )
    recipients = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    active = serializers.BooleanField(required=False)


class SensorTokenSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Shown only now. Only its SHA-256 is kept.")
    token_created_at = serializers.DateTimeField()


class TestReadingSerializer(serializers.Serializer):
    value = _number()


class AcknowledgeSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, allow_blank=True, required=False, default="")
