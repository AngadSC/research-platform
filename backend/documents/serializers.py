from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from documents import services
from documents.models import Attachment, Document, DocumentRevision, Folder

NOTICE = "Do not upload participant identifiers. Upload only anonymized or aggregate data."


class DocumentListSerializer(serializers.ModelSerializer):
    updated_by = UserSerializer(read_only=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "project",
            "folder",
            "title",
            "embed_url",
            "version",
            "updated_by",
            "retain_until",
            "retention_note",
            "contains_participant_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DocumentSerializer(DocumentListSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta(DocumentListSerializer.Meta):
        fields = [*DocumentListSerializer.Meta.fields, "content", "created_by", "embed_open_url"]
        read_only_fields = fields


class FolderRefMixin(serializers.Serializer):
    """The view resolves it inside the project; an unknown id is a 400 either way."""

    folder = serializers.UUIDField(allow_null=True, required=False)


class DocumentCreateSerializer(FolderRefMixin):
    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    content = serializers.JSONField(default=list, validators=[services.validate_content])
    embed_url = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    contains_participant_data = serializers.BooleanField(default=False)


class DocumentSaveSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    content = serializers.JSONField(validators=[services.validate_content])
    base_version = serializers.IntegerField(min_value=1)
    autosave = serializers.BooleanField(default=False)
    # Changing retention needs view_retention (D55); the service checks it.
    retain_until = serializers.DateField(allow_null=True, required=False)
    retention_note = serializers.CharField(allow_blank=True, required=False)


class ItemMoveSerializer(serializers.Serializer):
    """`folder: null` moves the item to the project's top level."""

    folder = serializers.UUIDField(allow_null=True)


class FolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Folder
        fields = [
            "id",
            "project",
            "parent",
            "name",
            "contains_participant_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FolderCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    parent = serializers.UUIDField(allow_null=True, required=False)


class FolderUpdateSerializer(serializers.Serializer):
    """Rename, tick or clear "Contains participant data", or both."""

    name = serializers.CharField(max_length=200, validators=[no_control_chars], required=False)
    contains_participant_data = serializers.BooleanField(required=False)


class ParticipantFlagSerializer(serializers.Serializer):
    contains_participant_data = serializers.BooleanField()


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
            "folder",
            "original_filename",
            "content_type",
            "size_bytes",
            "sha256",
            "uploaded_by",
            "notice_acknowledged_at",
            "created_at",
            "drive_file_id",
            "external_url",
            "contains_participant_data",
            "source",
        ]
        read_only_fields = fields


class AttachmentUploadSerializer(FolderRefMixin):
    """A file, or (D257) a Google Drive file id from the Picker. Exactly one."""

    file = serializers.FileField(required=False)
    drive_file_id = serializers.CharField(max_length=255, required=False)
    acknowledged_notice = serializers.BooleanField(default=False)
    pi_only = serializers.BooleanField(default=False)  # D244: honoured on project files only
    contains_participant_data = serializers.BooleanField(default=False)  # VISION A3

    def validate(self, data):
        data = super().validate(data)
        has_file, has_drive = "file" in data, bool(data.get("drive_file_id"))
        if has_file == has_drive:
            raise serializers.ValidationError({"file": "Choose a file, or a file from Drive."})
        if has_file and not data["acknowledged_notice"]:
            # Only an upload stores anything here; a Drive link stores a pointer (D64, D257).
            raise serializers.ValidationError(
                {"acknowledged_notice": f"You must acknowledge the upload notice. {NOTICE}"}
            )
        return data
