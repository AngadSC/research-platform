from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.permissions import can_view_ethics_files, visible_projects
from core.serializers import UserSerializer, no_control_chars
from documents.serializers import AttachmentSerializer
from ethics.models import ApprovalStatus, EthicsApproval

# Output serializers are read-only; inputs are plain Serializers (D33).


class ProjectRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class EthicsApprovalSerializer(serializers.ModelSerializer):
    """D48: `projects` lists only the projects the requester can see, and `attachments` is empty
    unless the requester may open the files."""

    created_by = UserSerializer(read_only=True)
    projects = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    can_view_files = serializers.SerializerMethodField()

    class Meta:
        model = EthicsApproval
        fields = [
            "id",
            "approval_number",
            "board",
            "title",
            "approval_date",
            "expiry_date",
            "status",
            "restricted",
            "projects",
            "attachments",
            "can_view_files",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _visible(self) -> set:
        if "visible_project_ids" not in self.context:
            request = self.context["request"]
            self.context["visible_project_ids"] = set(
                visible_projects(request.user, request.lab).values_list("pk", flat=True)
            )
        return self.context["visible_project_ids"]

    @extend_schema_field(ProjectRefSerializer(many=True))
    def get_projects(self, obj):
        visible = self._visible()
        return ProjectRefSerializer(
            [p for p in obj.projects.all() if p.pk in visible], many=True
        ).data

    def get_can_view_files(self, obj) -> bool:
        return can_view_ethics_files(self.context["request"].user, obj, self._visible())

    @extend_schema_field(AttachmentSerializer(many=True))
    def get_attachments(self, obj):
        if not self.get_can_view_files(obj):
            return []
        live = [a for a in obj.attachments.all() if a.deleted_at is None]
        return AttachmentSerializer(sorted(live, key=lambda a: a.created_at), many=True).data


class EthicsApprovalInputSerializer(serializers.Serializer):
    approval_number = serializers.CharField(max_length=100, validators=[no_control_chars])
    board = serializers.CharField(max_length=200, validators=[no_control_chars])
    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    projects = serializers.ListField(child=serializers.UUIDField(), required=False)
    approval_date = serializers.DateField()
    expiry_date = serializers.DateField()
    status = serializers.ChoiceField(choices=ApprovalStatus.choices, required=False)
    restricted = serializers.BooleanField(required=False)
