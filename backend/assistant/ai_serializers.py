"""Serializers for the in-app assistant (D187-D192). Explicit field lists: no key, ciphertext or
system prompt is ever serialized."""

from rest_framework import serializers

from assistant.ai import catalog
from assistant.models import Conversation, Provider
from labs.models import AiPolicy


class KeyStatusSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=Provider.choices)
    label = serializers.CharField()
    saved = serializers.BooleanField()
    last4 = serializers.CharField(help_text="Last 4 characters of the saved key; empty if none.")
    updated_at = serializers.DateTimeField(allow_null=True)
    refusal_fallback = serializers.BooleanField()


class KeySaveSerializer(serializers.Serializer):
    api_key = serializers.CharField(max_length=500, write_only=True, trim_whitespace=False)


class KeyUpdateSerializer(serializers.Serializer):
    refusal_fallback = serializers.BooleanField()


class ModelInfoSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    input = serializers.FloatField(help_text="USD per million input tokens (list price).")
    output = serializers.FloatField(help_text="USD per million output tokens (list price).")


class ProviderConfigSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=Provider.choices)
    label = serializers.CharField()
    default_model = serializers.CharField()
    has_key = serializers.BooleanField()
    models = ModelInfoSerializer(many=True)


class AssistantConfigSerializer(serializers.Serializer):
    ai_policy = serializers.ChoiceField(choices=AiPolicy.choices)
    can_use = serializers.BooleanField()
    providers = ProviderConfigSerializer(many=True)
    privacy_notice = serializers.CharField()


class PolicySerializer(serializers.Serializer):
    ai_policy = serializers.ChoiceField(choices=AiPolicy.choices)


class ConversationSerializer(serializers.ModelSerializer):
    project = serializers.UUIDField(source="project_id", allow_null=True)

    class Meta:
        model = Conversation
        fields = ["id", "project", "provider", "model", "title", "created_at", "updated_at"]
        read_only_fields = fields


class ConversationCreateSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=Provider.choices)
    model = serializers.CharField(max_length=40, required=False, allow_blank=True)
    project = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs["model"] = attrs.get("model") or catalog.DEFAULT_MODEL[attrs["provider"]]
        if attrs["model"] not in catalog.model_ids(attrs["provider"]):
            raise serializers.ValidationError({"model": "Choose one of the listed models."})
        return attrs


class UsageSerializer(serializers.Serializer):
    input_tokens = serializers.IntegerField(required=False)
    output_tokens = serializers.IntegerField(required=False)
    cache_read_tokens = serializers.IntegerField(required=False)
    cache_write_tokens = serializers.IntegerField(required=False)


class RefusalSerializer(serializers.Serializer):
    category = serializers.CharField(allow_null=True, required=False)
    explanation = serializers.CharField(allow_null=True, required=False)
    recommended_model = serializers.CharField(allow_null=True, required=False)


class TimelineItemSerializer(serializers.Serializer):
    """One row of the chat: kind `user`, `assistant`, `tool` or `usage` (tokens spent on turns
    that produced no text). Only the fields of that kind are set."""

    id = serializers.CharField()
    kind = serializers.CharField(help_text="user, assistant, tool or usage")
    text = serializers.CharField(required=False)
    model = serializers.CharField(required=False, help_text="The model that answered.")
    usage = UsageSerializer(required=False)
    stop_reason = serializers.CharField(required=False)
    fallback = serializers.BooleanField(required=False)
    refusal = RefusalSerializer(required=False, allow_null=True)
    truncated = serializers.BooleanField(required=False)
    call_id = serializers.CharField(required=False)
    name = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    write = serializers.BooleanField(required=False)
    arguments = serializers.DictField(required=False)
    status = serializers.CharField(
        required=False, help_text="Tool rows: running, pending, done, error or declined."
    )


class PreviewSerializer(serializers.Serializer):
    label = serializers.CharField()
    text = serializers.CharField()


class PendingCallSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    title = serializers.CharField()
    arguments = serializers.DictField()
    resolved = serializers.DictField(
        child=serializers.CharField(), help_text="Names for the ids: lab, project, task, person."
    )
    preview = PreviewSerializer(many=True, help_text="The text that will be posted.")


class ConversationDetailSerializer(ConversationSerializer):
    items = TimelineItemSerializer(many=True, read_only=True)
    pending = PendingCallSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = [*ConversationSerializer.Meta.fields, "items", "pending"]
        read_only_fields = fields


class MessageInputSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=catalog.MAX_TEXT)


class ApprovalDecisionSerializer(serializers.Serializer):
    decisions = serializers.DictField(
        child=serializers.BooleanField(),
        help_text="Tool call id -> true to approve, false to decline. Every waiting call.",
    )
