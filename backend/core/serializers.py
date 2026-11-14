import re
import unicodedata
import zoneinfo

from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from core import avatars
from core.middleware import canonical_zone
from core.models import Notification, User
from core.notifications import live_body, live_title, notification_url


def no_control_chars(value):
    """Reject newlines and other control characters (they break mail headers and log lines)."""
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value):
        raise serializers.ValidationError("Control characters are not allowed.")
    return value


def _sane_datetime(value):
    if not 1900 <= value.year <= 2200:
        raise serializers.ValidationError("Enter a date between the years 1900 and 2200.")


class SaneDateTimeField(serializers.DateTimeField):
    """Every datetime a person can write. Near year 1 or 9999 converting to a viewer's time zone
    overflows, which would break the list for everyone else. Model datetimes use it too
    (core.apps)."""

    default_validators = [_sane_datetime]


class UserSerializer(serializers.ModelSerializer):
    # Both come from columns on the user row, so nesting this costs no extra query (D258).
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "pronouns", "avatar_url"]
        read_only_fields = ["id", "email"]
        extra_kwargs = {
            "display_name": {"validators": [no_control_chars]},
            "pronouns": {"validators": [no_control_chars]},
        }

    def get_avatar_url(self, user) -> str | None:
        return avatars.url(user)


# D125: personal UI settings. Unknown keys and values are rejected; PATCH merges.
PREFERENCE_CHOICES = {
    "theme": ("light", "dark", "system"),
    "task_view": ("board", "list"),
    # D291: the browser's own zone, sent by the app on its own (never typed in).
    "time_zone": frozenset(zoneinfo.available_timezones()),
}
# Saved links: key -> (most entries, keys each entry carries).
PREFERENCE_LINKS = {
    "pins": (20, {"url", "label"}),
    "recents": (12, {"url", "label", "kind", "at"}),
}
# The order a person arranged their sidebar in: the links' paths inside a lab, not full URLs.
PREFERENCE_ORDERS = ("sidebar_main", "sidebar_admin")
MAX_ORDER_ITEMS = 40
ORDER_ITEM = re.compile(r"[a-z0-9][a-z0-9/_-]{0,59}")
RECENT_KINDS = ("project", "document", "record", "approval")
# A person's own colour themes (D224). lib/customTheme.ts applies the same contrast rule.
MAX_CUSTOM_THEMES = 10
CUSTOM_THEME_KEYS = {"id", "name", "background", "text", "accent"}
CUSTOM_THEME_ID = re.compile(r"[a-z0-9]{1,20}")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
# 6:1 on the plain background keeps text at 4.5:1 (WCAG AA) on the tinted panels made from it.
MIN_CONTRAST = 6
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


def _luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _valid_custom_theme(item) -> bool:
    if not isinstance(item, dict) or set(item) != CUSTOM_THEME_KEYS:
        return False
    if not all(isinstance(v, str) for v in item.values()):
        return False
    colors = (item["background"], item["text"], item["accent"])
    if not CUSTOM_THEME_ID.fullmatch(item["id"]) or not all(HEX_COLOR.fullmatch(c) for c in colors):
        return False
    if not 0 < len(item["name"].strip()) <= 40:
        return False
    try:
        no_control_chars(item["name"])
    except serializers.ValidationError:
        return False
    return (
        _contrast(item["text"], item["background"]) >= MIN_CONTRAST
        and _contrast(item["accent"], item["background"]) >= MIN_CONTRAST
    )


class MeSerializer(UserSerializer):
    """`/api/me/` only: the user's own preferences never appear in nested user objects."""

    preferences = serializers.JSONField(required=False)
    bio = serializers.CharField(max_length=500, allow_blank=True, required=False)

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "bio", "preferences"]

    def validate_bio(self, value):
        # Newlines are fine in a bio; other control characters are not.
        no_control_chars(value.replace("\n", "").replace("\r", "").replace("\t", ""))
        return value

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
            elif key in PREFERENCE_ORDERS:
                ok = (
                    isinstance(val, list)
                    and len(val) <= MAX_ORDER_ITEMS
                    and len(set(map(str, val))) == len(val)
                    and all(isinstance(v, str) and ORDER_ITEM.fullmatch(v) for v in val)
                )
            elif key == "custom_themes":
                ok = (
                    isinstance(val, list)
                    and len(val) <= MAX_CUSTOM_THEMES
                    and all(_valid_custom_theme(item) for item in val)
                    and len({item["id"] for item in val}) == len(val)
                )
            elif key == "theme" and isinstance(val, str) and val.startswith("custom:"):
                ok = True  # checked below, against the list as it will be saved
            else:
                ok = not isinstance(val, (list, dict)) and val in PREFERENCE_CHOICES.get(key, ())
            if not ok:
                raise serializers.ValidationError(f"Unsupported preference: {key}.")
        if "time_zone" in value:
            value = {**value, "time_zone": canonical_zone(value["time_zone"])}
        # MeView locks the user row, so two PATCHes merge instead of overwriting each other.
        merged = {**(self.instance.preferences if self.instance else {}), **value}
        theme = merged.get("theme", "")
        if theme.startswith("custom:") and theme[7:] not in {
            item["id"] for item in merged.get("custom_themes", [])
        }:
            raise serializers.ValidationError("Unsupported preference: theme.")
        return merged


class NotificationSerializer(serializers.ModelSerializer):
    """`title` and `body` are as they read today (core/notifications.py); `url` is the page the
    notification is about."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "body",
            "target_type",
            "target_id",
            "url",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_url(self, n) -> str:
        return notification_url(n, self.context["request"].user)

    def to_representation(self, n):
        data = super().to_representation(n)
        data["title"], data["body"] = live_title(n), live_body(n)
        return data
