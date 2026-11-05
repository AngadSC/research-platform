from rest_framework import serializers

from core.serializers import UserSerializer
from integrations.models import ConnectedAccount


class ConnectedAccountSerializer(serializers.ModelSerializer):
    """Explicit read-only fields: token columns are never listed (ARCHITECTURE section 9)."""

    user = UserSerializer(read_only=True)

    class Meta:
        model = ConnectedAccount
        fields = [
            "id",
            "provider",
            "user",
            "external_email",
            "granted_scopes",
            "status",
            "connected_at",
            "last_used_at",
        ]
        read_only_fields = fields
