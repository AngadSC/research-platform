from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from documents import services
from documents.models import Attachment, Document, DocumentRevision

NOTICE = "Do not upload participant identifiers. Upload only anonymized or aggregate data."


class DocumentListSerializer(serializers.ModelSerializer):
    updated_by = UserSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "project",
            "title",
            "version",
            "updated_by",
            "retain_until",
            "retention_note",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DocumentSerializer(DocumentListSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta(DocumentListSerializer.Meta):
        fields = [*DocumentListSerializer.Meta.fields, "content", "created_by"]
        read_only_fields = fields


class DocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    content = serializers.JSONField(default=list, validators=[services.validate_content])


class DocumentSaveSerializer(DocumentCreateSerializer):
    content = serializers.JSONField(validators=[services.validate_content])
    base_version = serializers.IntegerField(min_value=1)
    # Changing retention needs view_retention (D55); the service checks it.
    retain_until = serializers.DateField(allow_null=True, required=False)
    retention_note = serializers.CharField(allow_blank=True, required=False)


class ConflictSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()
    current_version = serializers.IntegerField()
    updated_by = UserSerializer()
    updated_at = serializers.DateTimeField()


class RevisionListSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    restored_from_version = serializers.IntegerField(
        source="restored_from.version", read_only=True, default=None
    )

    class Meta:
        model = DocumentRevision
        fields = ["id", "version", "title", "created_by", "created_at", "restored_from_version"]
        read_only_fields = fields


class RevisionSerializer(RevisionListSerializer):
    class Meta(RevisionListSerializer.Meta):
        fields = [*RevisionListSerializer.Meta.fields, "content"]
        read_only_fields = fields


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = Attachment
        fields = [
            "id",
            "project",
            "ethics_approval",
            "original_filename",
            "content_type",
            "size_bytes",
            "sha256",
            "uploaded_by",
            "notice_acknowledged_at",
            "created_at",
        ]
        read_only_fields = fields


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    acknowledged_notice = serializers.BooleanField(default=False)

    def validate_acknowledged_notice(self, value):
        if not value:
            raise serializers.ValidationError(f"You must acknowledge the upload notice. {NOTICE}")
        return value
