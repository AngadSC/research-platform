from rest_framework import serializers

from participants.models import (
    AnalysisSet,
    Category,
    CellStatus,
    CellTask,
    Component,
    ComponentFile,
    EnrolmentStatus,
    FileRole,
    ImportRun,
    InclusionRule,
    LinkState,
    Participant,
    ParticipantComponent,
    ParticipantEvent,
    StatusReason,
)

TEXT_FIELDS = ("group", "cohort", "notes", "note", "name", "label", "title", "version_label")


class ReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusReason
        fields = ["id", "label", "kind", "active"]
        read_only_fields = fields


class ReasonInputSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=100)
    kind = serializers.ChoiceField(choices=StatusReason._meta.get_field("kind").choices)
    active = serializers.BooleanField(required=False)


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = [
            "id",
            "code",
            "group",
            "cohort",
            "enrolment_status",
            "enrolled_on",
            "completed_on",
            "notes",
            "archived_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ParticipantInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40)
    group = serializers.CharField(max_length=100, required=False, allow_blank=True)
    cohort = serializers.CharField(max_length=100, required=False, allow_blank=True)
    enrolment_status = serializers.ChoiceField(choices=EnrolmentStatus.choices, required=False)
    enrolled_on = serializers.DateField(required=False, allow_null=True)
    completed_on = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ParticipantBulkSerializer(serializers.Serializer):
    """Many coded participants at once: pasted codes, or full rows."""

    codes = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, max_length=500
    )
    participants = ParticipantInputSerializer(many=True, required=False, max_length=500)
    group = serializers.CharField(max_length=100, required=False, allow_blank=True)
    cohort = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ComponentSerializer(serializers.ModelSerializer):
    applies_to_groups = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Component
        fields = [
            "id",
            "name",
            "key",
            "category",
            "required",
            "applies_to_groups",
            "order",
            "expected_per_participant",
            "template_origin",
            "sensitive",
            "archived_at",
        ]
        read_only_fields = fields


class ComponentInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    key = serializers.SlugField(max_length=60, required=False)
    category = serializers.ChoiceField(choices=Category.choices, required=False)
    required = serializers.BooleanField(required=False)
    applies_to_groups = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=50
    )
    order = serializers.IntegerField(min_value=0, max_value=10000, required=False)
    expected_per_participant = serializers.IntegerField(min_value=1, max_value=50, required=False)
    sensitive = serializers.BooleanField(required=False)


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentFile
        fields = [
            "id",
            "provider",
            "url",
            "external_id",
            "title",
            "mime_type",
            "last_modified_remote",
            "last_checked_at",
            "link_state",
            "role",
            "version_label",
        ]
        read_only_fields = fields


class FileInputSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=1000)
    title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=FileRole.choices, required=False)
    version_label = serializers.CharField(max_length=100, required=False, allow_blank=True)
    link_state = serializers.ChoiceField(choices=LinkState.choices, required=False)


class CellTaskSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="task_id", read_only=True)
    title = serializers.CharField(source="task.title", read_only=True)
    status = serializers.CharField(source="task.status", read_only=True)
    assignee = serializers.UUIDField(source="task.assignee_id", read_only=True, allow_null=True)
    due_date = serializers.DateField(source="task.due_date", read_only=True)

    class Meta:
        model = CellTask
        fields = ["id", "title", "status", "assignee", "due_date"]
        read_only_fields = fields


class CellSerializer(serializers.ModelSerializer):
    files = FileSerializer(many=True, read_only=True)
    tasks = CellTaskSerializer(source="task_links", many=True, read_only=True)
    participant = serializers.UUIDField(source="participant_id", read_only=True)
    component = serializers.UUIDField(source="component_id", read_only=True)
    reason = serializers.UUIDField(source="reason_id", read_only=True, allow_null=True)
    owner = serializers.UUIDField(source="owner_id", read_only=True, allow_null=True)
    decision = serializers.UUIDField(source="decision_id", read_only=True, allow_null=True)
    suggested_status = serializers.SerializerMethodField()
    changed_since_verified = serializers.SerializerMethodField()

    class Meta:
        model = ParticipantComponent
        fields = [
            "id",
            "participant",
            "component",
            "status",
            "reason",
            "owner",
            "decision",
            "due_date",
            "collected_on",
            "note",
            "files",
            "tasks",
            "suggested_status",
            "verified_at",
            "changed_since_verified",
            "updated_at",
        ]
        read_only_fields = fields

    def get_changed_since_verified(self, cell) -> bool:
        """A linked document was edited after the cell was confirmed complete. Never reverts it."""
        if cell.status != CellStatus.COMPLETE or cell.verified_at is None:
            return False
        return any(
            f.last_modified_remote and f.last_modified_remote > cell.verified_at
            for f in cell.files.all()
        )

    def get_suggested_status(self, cell) -> str | None:
        """A link in a cell nobody has started: suggest In progress. Never applied by itself."""
        if cell.status == CellStatus.NOT_STARTED and cell.files.all():
            return CellStatus.IN_PROGRESS
        return None


class CellInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=CellStatus.choices, required=False)
    reason = serializers.UUIDField(required=False, allow_null=True)
    owner = serializers.UUIDField(required=False, allow_null=True)
    decision = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    collected_on = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    verified = serializers.BooleanField(required=False)  # "I checked it again"


class EventSerializer(serializers.ModelSerializer):
    component = serializers.UUIDField(source="component_id", read_only=True, allow_null=True)
    actor = serializers.UUIDField(source="actor_id", read_only=True, allow_null=True)

    class Meta:
        model = ParticipantEvent
        fields = ["id", "component", "actor", "action", "from_value", "to_value", "created_at"]
        read_only_fields = fields


class ParticipantImportMappingSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=200)
    group = serializers.CharField(max_length=200, required=False, allow_blank=True)
    cohort = serializers.CharField(max_length=200, required=False, allow_blank=True)
    enrolment_status = serializers.CharField(max_length=200, required=False, allow_blank=True)
    components = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(max_length=200)),
        required=False,
        max_length=80,
    )


class ParticipantImportPreviewInputSerializer(serializers.Serializer):
    csv = serializers.CharField(max_length=1_100_000)


class ParticipantImportInputSerializer(serializers.Serializer):
    csv = serializers.CharField(max_length=1_100_000)
    mapping = ParticipantImportMappingSerializer()
    dry_run = serializers.BooleanField(default=True)
    source = serializers.ChoiceField(choices=["csv", "sheet"], default="csv")


class ParticipantImportRunSerializer(serializers.ModelSerializer):
    can_undo = serializers.SerializerMethodField()

    class Meta:
        model = ImportRun
        fields = ["id", "source", "summary", "undone_at", "created_at", "can_undo"]
        read_only_fields = fields

    def get_can_undo(self, run) -> bool:
        return run.undone_at is None and run.pk == self.context.get("latest")


class MatchFileSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=300)
    url = serializers.URLField(max_length=1000)
    title = serializers.CharField(max_length=300, required=False, allow_blank=True)


class ParticipantMatchInputSerializer(serializers.Serializer):
    files = MatchFileSerializer(many=True, max_length=500)
    pattern = serializers.CharField(max_length=100, default="P-{number}_{component}")


class AttachItemSerializer(serializers.Serializer):
    participant = serializers.UUIDField()
    component = serializers.UUIDField()
    url = serializers.URLField(max_length=1000)
    title = serializers.CharField(max_length=300, required=False, allow_blank=True)


class ParticipantAttachInputSerializer(serializers.Serializer):
    items = AttachItemSerializer(many=True, max_length=500)


class TaskCellSerializer(serializers.Serializer):
    participant = serializers.UUIDField()
    component = serializers.UUIDField()


class TaskGapsInputSerializer(serializers.Serializer):
    cells = TaskCellSerializer(many=True, min_length=1, max_length=500)
    mode = serializers.ChoiceField(choices=["cell", "participant", "component"], default="cell")
    assignee = serializers.UUIDField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)


class RuleSpecSerializer(serializers.Serializer):
    requires = serializers.ListField(child=serializers.SlugField(), max_length=60, required=False)
    groups = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=50
    )
    exclude_enrolment = serializers.ListField(
        child=serializers.ChoiceField(choices=EnrolmentStatus.choices), required=False
    )


class RuleSerializer(serializers.ModelSerializer):
    spec = RuleSpecSerializer(read_only=True)

    class Meta:
        model = InclusionRule
        fields = ["id", "name", "description", "version", "spec", "archived_at", "updated_at"]
        read_only_fields = fields


class RuleInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    spec = RuleSpecSerializer(required=False)


class SetSerializer(serializers.ModelSerializer):
    rule = serializers.UUIDField(source="rule_id", read_only=True, allow_null=True)
    analysis = serializers.UUIDField(source="analysis_id", read_only=True, allow_null=True)
    supersedes = serializers.UUIDField(source="supersedes_id", read_only=True, allow_null=True)
    size = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisSet
        fields = [
            "id",
            "name",
            "rule",
            "rule_version",
            "size",
            "locked_at",
            "analysis",
            "supersedes",
        ]
        read_only_fields = fields

    def get_size(self, obj) -> int:
        return len(obj.participant_ids)


class SetInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    rule = serializers.UUIDField()


class SetPatchSerializer(serializers.Serializer):
    analysis = serializers.UUIDField(allow_null=True)
