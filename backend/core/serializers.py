import unicodedata

from rest_framework import serializers

from core.models import Notification, User


def no_control_chars(value):
    """Reject newlines and other control characters (they break mail headers and log lines)."""
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value):
        raise serializers.ValidationError("Control characters are not allowed.")
    return value


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name"]
        read_only_fields = ["id", "email"]
        extra_kwargs = {"display_name": {"validators": [no_control_chars]}}


# D125: personal UI settings. Unknown keys and values are rejected; PATCH merges.
PREFERENCE_CHOICES = {
    "theme": ("light", "dark", "system"),
    "task_view": ("board", "list"),
}


class MeSerializer(UserSerializer):
    """`/api/me/` only: the user's own preferences never appear in nested user objects."""

    preferences = serializers.JSONField(required=False)

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "preferences"]

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        for key, val in value.items():
            if val not in PREFERENCE_CHOICES.get(key, ()):
                raise serializers.ValidationError(f"Unsupported preference: {key}.")
        return {**(self.instance.preferences if self.instance else {}), **value}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "body",
            "target_type",
            "target_id",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
