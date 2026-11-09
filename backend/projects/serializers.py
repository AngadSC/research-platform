from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.permissions import PROJECT_PERMS, Perm, can, project_role
from core.serializers import UserSerializer, no_control_chars
from projects.models import (
    ChatMessage,
    DeadlinePriority,
    Project,
    ProjectColor,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    ProjectStatus,
    Task,
    TaskPost,
    TaskStatus,
)

# Output serializers are read-only. Inputs are plain Serializers, so DRF adds no unique
# validators that would query unscoped (D33).


class ProjectSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    last_activity_by = UserSerializer(read_only=True)
    my_project_role = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "color",
            "description",
            "status",
            "start_date",
            "retain_until",
            "retention_note",
            "created_by",
            "created_at",
            "updated_at",
            "last_activity_at",
            "last_activity_by",
            "my_project_role",
            "my_permissions",
        ]
        read_only_fields = fields

    def get_my_project_role(self, project) -> str | None:
        return project_role(self.context["request"].user, project)

    def get_my_permissions(self, project) -> list[str]:
        user = self.context["request"].user
        perms = PROJECT_PERMS | {Perm.DELETE_PROJECT, Perm.VIEW_RETENTION}
        return sorted(p.value for p in perms if can(user, p, project))


class ProjectInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    color = serializers.ChoiceField(choices=ProjectColor.choices, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    status = serializers.ChoiceField(choices=ProjectStatus.choices, required=False)
    start_date = serializers.DateField(allow_null=True, required=False)
    retain_until = serializers.DateField(allow_null=True, required=False)
    retention_note = serializers.CharField(allow_blank=True, required=False)


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ["id", "project", "user", "role", "created_at"]
        read_only_fields = fields


class ProjectMembershipCreateSerializer(serializers.Serializer):
    user = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ProjectRole.choices)


class ProjectMembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=ProjectRole.choices)


class DeadlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectDeadline
        fields = [
            "id",
            "project",
            "title",
            "due_date",
            "done",
            "priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DeadlineInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, validators=[no_control_chars])
    due_date = serializers.DateField()
    done = serializers.BooleanField(required=False)
    priority = serializers.ChoiceField(choices=DeadlinePriority.choices, required=False)


class TaskDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    version = serializers.IntegerField()


class TaskAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    original_filename = serializers.CharField()
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()


class TaskSerializer(serializers.ModelSerializer):
    assignee = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    documents = serializers.SerializerMethodField()
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    post_count = serializers.SerializerMethodField()

    @extend_schema_field(TaskDocumentSerializer(many=True))
    def get_documents(self, obj):
        docs = [d for d in obj.documents.all() if d.deleted_at is None]
        return TaskDocumentSerializer(docs, many=True).data

    def get_post_count(self, obj) -> int:
        n = getattr(obj, "post_count", None)  # annotated by the views; avoids a query per task
        return n if n is not None else obj.posts.count()

    class Meta:
        model = Task
        fields = [
            "id",
            "project",
            "title",
            "description",
            "assignee",
            "due_date",
            "status",
            "position",
            "created_by",
            "documents",
            "attachments",
            "post_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TaskInputSerializer(serializers.Serializer):
    """`status` + `position` also reorder: the task lands at that index of that column."""

    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    description = serializers.CharField(allow_blank=True, required=False)
    assignee = serializers.UUIDField(allow_null=True, required=False)
    due_date = serializers.DateField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=TaskStatus.choices, required=False)
    position = serializers.IntegerField(min_value=0, required=False)


class TaskFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TaskStatus.choices, required=False)
    assignee = serializers.UUIDField(required=False)


class RetentionItemSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["project", "document"])
    id = serializers.UUIDField()
    name = serializers.CharField()
    project_id = serializers.UUIDField()
    project_name = serializers.CharField()
    retain_until = serializers.DateField()
    retention_note = serializers.CharField(allow_blank=True)
    deleted_at = serializers.DateTimeField(allow_null=True)


# ---------------------------------------------------------------- handover (Phase 6)


class HandoverProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class HandoverItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    project = HandoverProjectSerializer(allow_null=True)
    href = serializers.CharField()
    reason = serializers.CharField()


class HandoverSectionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    items = HandoverItemSerializer(many=True)


class HandoverPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    membership_id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.CharField()


class HandoverSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    person = HandoverPersonSerializer()
    project = HandoverProjectSerializer(allow_null=True)
    no_other_owner = HandoverItemSerializer(many=True)
    sections = HandoverSectionSerializer(many=True)


class ChatMessageSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "author", "body", "created_at"]
        read_only_fields = fields


class ChatMessageInputSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)  # newlines are fine in a message


class ChatMessageFilterSerializer(serializers.Serializer):
    before = serializers.DateTimeField(required=False)


class ChatReadInputSerializer(serializers.Serializer):
    last_read_at = serializers.DateTimeField()


class ChatUnreadSerializer(serializers.Serializer):
    project = serializers.UUIDField()
    count = serializers.IntegerField()


class TaskPostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = TaskPost
        fields = ["id", "task", "author", "body", "edited_at", "created_at"]
        read_only_fields = fields


class TaskPostInputSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)


class TaskLinkInputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
