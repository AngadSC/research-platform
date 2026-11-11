from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from integrations import registry, services
from integrations.models import (
    TARGET_FIELDS,
    ConnectedAccount,
    ExternalLink,
    Webhook,
    WebhookKind,
)
from integrations.providers import google_drive
from integrations.webhooks import EVENTS


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
            "instance_url",
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
    instance_url = serializers.CharField()


class ConnectFieldSerializer(serializers.Serializer):
    """One field of an API-key connect form; `secret` fields are write-only (never echoed)."""

    name = serializers.ChoiceField(choices=registry.CONNECT_FIELDS)
    label = serializers.CharField()
    help_text = serializers.CharField()
    required = serializers.BooleanField()
    secret = serializers.BooleanField()


class ProviderSerializer(serializers.Serializer):
    """One registry entry plus the requester's own account there: everything the generic UI
    needs (D80). Built from a dict (`views.provider_entry`)."""

    name = serializers.CharField()
    label = serializers.CharField()
    auth_type = serializers.ChoiceField(choices=[a.value for a in registry.AuthType])
    category = serializers.ChoiceField(choices=[c.value for c in registry.Category])
    icon = serializers.CharField()
    metadata_only = serializers.BooleanField()
    scopes = serializers.ListField(child=serializers.CharField())
    configured = serializers.BooleanField()
    public_config = serializers.DictField(child=serializers.CharField())
    link_targets = serializers.ListField(child=serializers.ChoiceField(choices=registry.TARGETS))
    link_methods = serializers.ListField(
        child=serializers.ChoiceField(choices=registry.LINK_METHODS)
    )
    needs_instance_url = serializers.BooleanField()
    connect_fields = ConnectFieldSerializer(many=True)
    external_id_pattern = serializers.CharField()
    url_pattern = serializers.CharField()
    link_hosts = serializers.ListField(child=serializers.CharField())
    can_check = serializers.BooleanField()  # offers freshness checks (fetch_item)
    task_import = serializers.BooleanField()  # offers importing tasks (D240)
    bundle = serializers.ListField(
        child=serializers.CharField(),
        help_text="Other providers one sign-in also connects (D262), such as Drive and Calendar.",
    )
    bundle_label = serializers.CharField(help_text="What the bundle is called, such as Google.")
    account = ProviderAccountSerializer(allow_null=True)


class PickerTokenSerializer(serializers.Serializer):
    """D70: the one response that carries an access token."""

    access_token = serializers.CharField()
    expires_in = serializers.IntegerField()
    scope = serializers.CharField()


class ConnectInputSerializer(serializers.Serializer):
    """oauth2: optional `scopes`. api_key: the connect form (D81). Secrets are write-only and
    no validation message ever repeats a value."""

    scopes = serializers.ListField(child=serializers.CharField(), required=False)
    api_key = serializers.CharField(write_only=True, required=False, max_length=4096)
    secret = serializers.CharField(write_only=True, required=False, max_length=4096)
    instance_url = serializers.CharField(write_only=True, required=False, max_length=500)


class ConnectOutputSerializer(serializers.Serializer):
    """oauth2: `authorization_url` to send the browser to (`account` null). api_key: the stored
    `account` (`authorization_url` empty)."""

    authorization_url = serializers.CharField(allow_blank=True)
    account = ConnectedAccountSerializer(allow_null=True)


class ExternalLinkInputSerializer(serializers.Serializer):
    """Name the item by `external_id` (picker, search result) or by a pasted `url` the provider
    parses. Everything else about the item is read from the provider server-side (D85); only a
    link_only provider stores the pasted `url` and the person's `title`."""

    provider = serializers.CharField(max_length=40)
    external_id = serializers.CharField(max_length=255, required=False)
    url = serializers.URLField(max_length=2000, required=False)
    title = serializers.CharField(max_length=500, required=False)
    document = serializers.UUIDField(required=False)
    dataset = serializers.UUIDField(required=False)
    analysis = serializers.UUIDField(required=False)
    result = serializers.UUIDField(required=False)
    manuscript = serializers.UUIDField(required=False)
    decision = serializers.UUIDField(required=False)

    def validate(self, attrs):
        provider = registry.PROVIDERS.get(attrs["provider"])
        if not (attrs.get("external_id") or attrs.get("url")):
            raise serializers.ValidationError({"external_id": "Pick an item or paste its link."})
        if (
            provider is not None
            and "external_id" in attrs
            and not provider.valid_external_id(attrs["external_id"])
        ):
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
    editor_url = serializers.SerializerMethodField()

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
            "editor_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_editor_url(self, obj) -> str:
        if obj.provider != google_drive.PROVIDER.name or obj.unavailable_since:
            return ""
        return google_drive.editor_url(obj.mime_type, obj.external_id)

    def get_provider_label(self, obj) -> str:
        provider = registry.PROVIDERS.get(obj.provider)
        return provider.label if provider else obj.provider

    def get_linker_connection_status(self, obj) -> str | None:
        return obj.connected_account.status if obj.connected_account_id else None

    def get_check_blocked(self, obj) -> str:
        """Why a freshness check can't run: "" when it can (linker_inactive |
        linker_access_lost, D78)."""
        return services.check_blocked(obj)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        provider = registry.PROVIDERS.get(instance.provider)
        account = instance.connected_account if instance.connected_account_id else None
        if provider and not provider.link_url_ok(
            instance.url, getattr(account, "instance_host", "")
        ):
            data["url"] = ""  # never hand the browser a link outside the provider's hosts (D78)
        return data

    def get_version_note(self, obj) -> str:
        """Set on a just-created dataset link: copied | same | kept | none (D76)."""
        return getattr(obj, "version_note", "")


class ItemSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    target = serializers.ChoiceField(choices=registry.TARGETS, default="project")


class ItemSearchResultSerializer(serializers.Serializer):
    """A candidate to link (D85). Linking it sends only `id`: the server re-reads the rest."""

    id = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    modified = serializers.DateTimeField(allow_null=True)
    url = serializers.CharField()


class TaskSourceSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class ImportTasksInputSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=64)


class ImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    skipped = serializers.IntegerField()


class WebhookSerializer(serializers.ModelSerializer):
    """Never the address or the secret: `host` says where it goes."""

    events = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Webhook
        fields = [
            "id",
            "name",
            "kind",
            "host",
            "events",
            "is_active",
            "last_attempt_at",
            "last_status",
            "created_at",
        ]
        read_only_fields = fields


class WebhookCreatedSerializer(WebhookSerializer):
    """The only response with the signing secret: it is shown once."""

    secret = serializers.CharField()

    class Meta(WebhookSerializer.Meta):
        fields = [*WebhookSerializer.Meta.fields, "secret"]
        read_only_fields = fields


class WebhookEventSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class WebhookListSerializer(serializers.Serializer):
    events = WebhookEventSerializer(many=True)
    webhooks = WebhookSerializer(many=True)


class WebhookUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False, validators=[no_control_chars])
    events = serializers.ListField(
        child=serializers.ChoiceField(choices=list(EVENTS)),
        allow_empty=False,
        max_length=len(EVENTS),
        required=False,
    )
    is_active = serializers.BooleanField(required=False)


class WebhookCreateSerializer(WebhookUpdateSerializer):
    name = serializers.CharField(max_length=120, validators=[no_control_chars])
    kind = serializers.ChoiceField(choices=WebhookKind.choices)
    url = serializers.CharField(max_length=2000, write_only=True)
    events = serializers.ListField(
        child=serializers.ChoiceField(choices=list(EVENTS)),
        allow_empty=False,
        max_length=len(EVENTS),
    )


class WebhookTestResultSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    status = serializers.IntegerField(allow_null=True)
