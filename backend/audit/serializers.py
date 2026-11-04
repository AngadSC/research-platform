from rest_framework import serializers

from audit.models import AuditEvent
from core.serializers import UserSerializer


class AuditEventSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)  # null for system events
    target_label = serializers.CharField(source="target_repr", read_only=True)
    created_at = serializers.DateTimeField(source="occurred_at", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "target_id",
            "target_label",
            "ip",
            "created_at",
            "metadata",
        ]
        read_only_fields = fields


class AuditFilterSerializer(serializers.Serializer):
    actor = serializers.UUIDField(required=False)
    action = serializers.ChoiceField(
        choices=AuditEvent._meta.get_field("action").choices, required=False
    )
    target_type = serializers.CharField(required=False)
    target_id = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
