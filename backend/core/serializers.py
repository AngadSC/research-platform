import unicodedata

from rest_framework import serializers

from core.models import User


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
