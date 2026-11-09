import re
import unicodedata

from django.utils.dateparse import parse_datetime
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
# Saved links: key -> (most entries, keys each entry carries).
PREFERENCE_LINKS = {
    "pins": (20, {"url", "label"}),
    "recents": (12, {"url", "label", "kind", "at"}),
}
RECENT_KINDS = ("project", "document", "record", "approval")
# A path on this site. Browsers read "/\x" and "/<tab>/x" as "//x", which leaves the site.
LOCAL_URL = re.compile(r"/(?![/\\])[^\s\\]*")


def _valid_link(item, keys) -> bool:
    if not isinstance(item, dict) or set(item) != keys:
        return False
    url, label = item["url"], item["label"]
    if not (isinstance(url, str) and isinstance(label, str)):
        return False
    if len(url) > 500 or not 0 < len(label) <= 300 or not LOCAL_URL.fullmatch(url):
        return False
    try:
        no_control_chars(url)
        no_control_chars(label)
    except serializers.ValidationError:
        return False
    if "kind" not in keys:
        return True
    at = item["at"]
    try:
        return (
            item["kind"] in RECENT_KINDS
            and isinstance(at, str)
            and len(at) <= 40
            and parse_datetime(at) is not None
        )
    except ValueError:  # parse_datetime raises on a well-formed but impossible date
        return False


class MeSerializer(UserSerializer):
    """`/api/me/` only: the user's own preferences never appear in nested user objects."""

    preferences = serializers.JSONField(required=False)

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "preferences"]

    def validate_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        for key, val in value.items():
            if key in PREFERENCE_LINKS:
                cap, keys = PREFERENCE_LINKS[key]
                ok = (
                    isinstance(val, list)
                    and len(val) <= cap
                    and all(_valid_link(item, keys) for item in val)
                )
            else:
                ok = val in PREFERENCE_CHOICES.get(key, ())
            if not ok:
                raise serializers.ValidationError(f"Unsupported preference: {key}.")
        # ponytail: concurrent PATCHes can overwrite each other's key; lock the row if that bites.
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
