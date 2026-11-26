from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from documents.serializers import NOTICE
from instruments.models import InstrumentDropLink, InstrumentFile


class NamedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class SoftwareChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class InstrumentFileSerializer(serializers.ModelSerializer):
    instrument = NamedSerializer(read_only=True)
    project = NamedSerializer(read_only=True)
    dropped_by = UserSerializer(read_only=True)
    filename = serializers.CharField(source="attachment.original_filename", read_only=True)
    size_bytes = serializers.IntegerField(source="attachment.size_bytes", read_only=True)
    contains_participant_data = serializers.BooleanField(
        source="attachment.contains_participant_data", read_only=True
    )
    title = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()

    def get_title(self, obj) -> str:
        return str(obj.summary.get("title") or "")

    def get_kind(self, obj) -> str:
        return str(obj.summary.get("kind") or "")

    class Meta:
        model = InstrumentFile
        fields = [
            "id",
            "instrument",
            "project",
            "attachment",
            "filename",
            "size_bytes",
            "contains_participant_data",
            "software",
            "status",
            "title",
            "kind",
            "uploaded_via",
            "dropped_by",
            "created_at",
        ]
        read_only_fields = fields


class InstrumentFileDetailSerializer(InstrumentFileSerializer):
    summary = serializers.JSONField(read_only=True, help_text="instrument_parsers.parse_file")

    class Meta(InstrumentFileSerializer.Meta):
        fields = [*InstrumentFileSerializer.Meta.fields, "summary"]
        read_only_fields = fields


class DropUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    acknowledged_notice = serializers.BooleanField(default=False)
    contains_participant_data = serializers.BooleanField(default=False)

    def validate_acknowledged_notice(self, value):
        if not value:
            raise serializers.ValidationError(f"You must acknowledge the upload notice. {NOTICE}")
        return value


class DropLinkSerializer(serializers.ModelSerializer):
    project = NamedSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    expired = serializers.SerializerMethodField()

    def get_expired(self, obj) -> bool:
        return obj.expires_at is not None and obj.expires_at <= timezone.now()

    class Meta:
        model = InstrumentDropLink
        fields = [
            "id",
            "label",
            "project",
            "created_by",
            "expires_at",
            "expired",
            "last_used_at",
            "created_at",
        ]
        read_only_fields = fields


class DropLinkCreatedSerializer(DropLinkSerializer):
    url = serializers.SerializerMethodField(help_text="Shown once; only its hash is stored.")

    def get_url(self, obj) -> str:
        return f"{settings.FRONTEND_URL}/drop/{self.context['token']}"

    class Meta(DropLinkSerializer.Meta):
        fields = [*DropLinkSerializer.Meta.fields, "url"]
        read_only_fields = fields


class DropLinkInputSerializer(serializers.Serializer):
    project = serializers.UUIDField()
    label = serializers.CharField(
        max_length=100, allow_blank=True, required=False, validators=[no_control_chars]
    )
    # Never "never": a leaked link must end by itself (D384).
    expires_in_days = serializers.IntegerField(min_value=1, max_value=365, default=90)


class PublicDropSerializer(serializers.Serializer):
    instrument = serializers.CharField()
    project = serializers.CharField()
    max_bytes = serializers.IntegerField()


class PublicDropResultSerializer(serializers.Serializer):
    name = serializers.CharField()
    size_bytes = serializers.IntegerField()
