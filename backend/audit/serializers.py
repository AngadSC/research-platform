from rest_framework import serializers

from audit.models import AuditAction, AuditEvent
from audit.services import person_id
from core.serializers import UserSerializer
from labs.models import LAB_ROLE_WORDS

ROLE_WORDS = LAB_ROLE_WORDS | {"lead": "Lead", "contributor": "Contributor"}
MEMBERSHIP_TARGETS = ("labs.LabMembership", "projects.ProjectMembership")
# Reads, left out when the log shows changes only. Exports stay in: they copy data out.
READ_ACTIONS = (
    AuditAction.DOCUMENT_VIEWED,
    AuditAction.ATTACHMENT_DOWNLOADED,
    AuditAction.HANDOVER_GENERATED,
    AuditAction.AUDIT_LOG_VIEWED,
    AuditAction.INTEGRATION_SEARCHED,
    AuditAction.INTEGRATION_PICKER_TOKEN,
)


class AuditEventSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)  # null for system events
    target_label = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source="occurred_at", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "target_id",
            "target_label",
            "created_at",
            "metadata",
        ]
        read_only_fields = fields

    def get_target_label(self, e) -> str:
        """Plain words naming who and where, for membership and handover events, which store
        only ids. Without `label_context` in the context this is the stored label."""
        ctx = self.context
        if e.target_type == "documents.Attachment" and e.target_id in ctx.get("hidden_files", ()):
            return "A file only PIs can open"
        pid = person_id(e)
        if "names" not in ctx or pid is None:
            return e.target_repr
        if e.target_type not in MEMBERSHIP_TARGETS and e.action != AuditAction.HANDOVER_GENERATED:
            return e.target_repr
        m = e.metadata
        label = ctx["names"].get(str(pid), "Someone")
        if "old_role" in m and "new_role" in m:
            label += f" ({ROLE_WORDS.get(m['old_role'], m['old_role'])} to "
            label += f"{ROLE_WORDS.get(m['new_role'], m['new_role'])})"
        elif "role" in m:
            label += f" ({ROLE_WORDS.get(m['role'], m['role'])})"
        if project := ctx["projects"].get(e.project_id):
            label += f" in {project}"
        return label


class AuditFilterSerializer(serializers.Serializer):
    actor = serializers.UUIDField(required=False)
    action = serializers.ChoiceField(
        choices=AuditEvent._meta.get_field("action").choices, required=False
    )
    target_type = serializers.CharField(required=False)
    target_id = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    changes_only = serializers.BooleanField(
        required=False, default=False, help_text="Leave out views, downloads and other reads."
    )
