from rest_framework import serializers

from core.serializers import UserSerializer
from integrations import registry
from integrations.models import TARGET_FIELDS, ConnectedAccount, ExternalLink


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


class ProviderAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    external_email = serializers.CharField()


class ProviderSerializer(serializers.Serializer):
    """One registry entry plus the requester's own account there. Built from a dict."""

    name = serializers.CharField()
    label = serializers.CharField()
    auth_type = serializers.CharField()
    icon = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    configured = serializers.BooleanField()
    public_config = serializers.DictField(child=serializers.CharField())
    account = ProviderAccountSerializer(allow_null=True)


class PickerTokenSerializer(serializers.Serializer):
    """D70: the one response that carries an access token."""

    access_token = serializers.CharField()
    expires_in = serializers.IntegerField()
    scope = serializers.CharField()


class ConnectInputSerializer(serializers.Serializer):
    scopes = serializers.ListField(child=serializers.CharField(), required=False)


class ConnectOutputSerializer(serializers.Serializer):
    authorization_url = serializers.CharField()


class ExternalLinkInputSerializer(serializers.Serializer):
    """`url`, `title` and `mime_type` are only used by link_only providers; for the others
    the provider is asked for them."""

    provider = serializers.CharField(max_length=40)
    external_id = serializers.CharField(max_length=255)
    url = serializers.URLField(max_length=2000, required=False)
    title = serializers.CharField(max_length=500, required=False)
    mime_type = serializers.CharField(max_length=255, required=False, allow_blank=True)
    document = serializers.UUIDField(required=False)
    dataset = serializers.UUIDField(required=False)
    analysis = serializers.UUIDField(required=False)
    result = serializers.UUIDField(required=False)
    manuscript = serializers.UUIDField(required=False)

    def validate(self, attrs):
        provider = registry.PROVIDERS.get(attrs["provider"])
        if provider is not None and not provider.valid_external_id(attrs["external_id"]):
            raise serializers.ValidationError({"external_id": "This is not a valid item id."})
        if sum(attrs.get(f) is not None for f in TARGET_FIELDS) > 1:
            raise serializers.ValidationError("Link to one item at most.")
        return attrs


class ExternalLinkSerializer(serializers.ModelSerializer):
    linked_by = UserSerializer(read_only=True)
    provider_label = serializers.SerializerMethodField()
    changed_since_linked = serializers.BooleanField(read_only=True)
    linker_connection_status = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)  # ok | changed | unavailable
    check_blocked = serializers.SerializerMethodField()
    version_note = serializers.SerializerMethodField()

    class Meta:
        model = ExternalLink
        fields = [
            "id",
            "project",
            *TARGET_FIELDS,
            "provider",
            "provider_label",
            "external_id",
            "url",
            "title",
            "mime_type",
            "linked_by",
            "linked_modified_at",
            "linked_version",
            "linked_checksum",
            "remote_modified_at",
            "remote_version",
            "remote_checksum",
            "last_checked_at",
            "unavailable_since",
            "changed_since_linked",
            "status",
            "check_blocked",
            "version_note",
            "linker_connection_status",
            "created_at",
        ]
        read_only_fields = fields

    def get_provider_label(self, obj) -> str:
        provider = registry.PROVIDERS.get(obj.provider)
        return provider.label if provider else obj.provider

    def get_linker_connection_status(self, obj) -> str | None:
        return obj.connected_account.status if obj.connected_account_id else None

    def get_check_blocked(self, obj) -> str:
        """Why a freshness check can't run: "" when it can."""
        if obj.connected_account_id and obj.connected_account.status != "active":
            return "linker_inactive"
        return ""

    def get_version_note(self, obj) -> str:
        """Set on a just-created dataset link: copied | same | kept | none (D76)."""
        return getattr(obj, "version_note", "")
