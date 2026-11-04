from django.db.models import Prefetch
from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from documents.models import Attachment, Document
from documents.serializers import (
    AttachmentSerializer,
    DocumentSerializer,
)
from projects.serializers import DeadlineSerializer, ProjectSerializer, TaskSerializer
from provenance.models import (
    Analysis,
    DatasetRecord,
    Decision,
    LineageKind,
    ManuscriptLink,
    ManuscriptStatus,
    Result,
    validate_checksum,
    validate_commit,
    validate_web_url,
)

# Output serializers are read-only. Inputs are plain Serializers, so DRF adds no unique
# validators that would query unscoped (D33). Link inputs are bare UUIDs that
# provenance.services resolves inside the one project.

# ---------------------------------------------------------------- compact refs (nested output)


class DatasetRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRecord
        fields = ["id", "name", "version_label"]
        read_only_fields = fields


class AnalysisRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = ["id", "title"]
        read_only_fields = fields


class ResultRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ["id", "title"]
        read_only_fields = fields


class ManuscriptRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManuscriptLink
        fields = ["id", "title", "status"]
        read_only_fields = fields


class DocumentRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title"]
        read_only_fields = fields


class AttachmentRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ["id", "original_filename", "content_type", "size_bytes"]
        read_only_fields = fields


class ReferenceSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=300, allow_blank=True, required=False, validators=[no_control_chars]
    )
    url = serializers.CharField(
        max_length=500, allow_blank=True, required=False, validators=[validate_web_url]
    )
    doi = serializers.CharField(max_length=200, allow_blank=True, required=False)


# ---------------------------------------------------------------- output


class DatasetSerializer(serializers.ModelSerializer):
    controlled_by = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    previous_version = DatasetRefSerializer(read_only=True)
    analyses = AnalysisRefSerializer(many=True, read_only=True)

    class Meta:
        model = DatasetRecord
        fields = [
            "id",
            "project",
            "name",
            "location_text",
            "location_url",
            "controlled_by",
            "access_notes",
            "version_label",
            "checksum",
            "previous_version",
            "analyses",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AnalysisSerializer(serializers.ModelSerializer):
    ran_by = UserSerializer(read_only=True)
    code_attachment = AttachmentRefSerializer(read_only=True)
    datasets = DatasetRefSerializer(many=True, read_only=True)
    results = ResultRefSerializer(many=True, read_only=True)

    class Meta:
        model = Analysis
        fields = [
            "id",
            "project",
            "title",
            "description",
            "code_repo_url",
            "code_commit",
            "code_attachment",
            "datasets",
            "results",
            "ran_by",
            "ran_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ResultSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    analysis = AnalysisRefSerializer(read_only=True)
    attachments = AttachmentRefSerializer(many=True, read_only=True)
    manuscripts = ManuscriptRefSerializer(many=True, read_only=True)

    class Meta:
        model = Result
        fields = [
            "id",
            "project",
            "title",
            "summary",
            "analysis",
            "attachments",
            "manuscripts",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DecisionSerializer(serializers.ModelSerializer):
    decided_by = UserSerializer(read_only=True)
    supporting_documents = DocumentRefSerializer(many=True, read_only=True)
    supporting_attachments = AttachmentRefSerializer(many=True, read_only=True)
    analyses = AnalysisRefSerializer(many=True, read_only=True)
    results = ResultRefSerializer(many=True, read_only=True)
    datasets = DatasetRefSerializer(many=True, read_only=True)
    references = ReferenceSerializer(many=True, read_only=True)

    class Meta:
        model = Decision
        fields = [
            "id",
            "project",
            "title",
            "rationale",
            "decided_on",
            "decided_by",
            "supporting_documents",
            "supporting_attachments",
            "references",
            "analyses",
            "results",
            "datasets",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ManuscriptSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    results = ResultRefSerializer(many=True, read_only=True)

    class Meta:
        model = ManuscriptLink
        fields = [
            "id",
            "project",
            "title",
            "url",
            "status",
            "results",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


OUTPUT = {
    "dataset": DatasetSerializer,
    "analysis": AnalysisSerializer,
    "result": ResultSerializer,
    "decision": DecisionSerializer,
    "manuscript": ManuscriptSerializer,
}
PLURAL = {
    "dataset": "datasets",
    "analysis": "analyses",
    "result": "results",
    "decision": "decisions",
    "manuscript": "manuscripts",
}
SELECT = {
    "dataset": ("controlled_by", "created_by", "previous_version"),
    "analysis": ("ran_by", "code_attachment"),
    "result": ("created_by", "analysis"),
    "decision": ("decided_by",),
    "manuscript": ("created_by",),
}
PREFETCH = {  # plain names, or (name, model) for soft-deletable targets (hidden once deleted)
    "dataset": ("analyses",),
    "analysis": ("datasets", "results"),
    "result": (("attachments", Attachment), "manuscripts"),
    "decision": (
        ("supporting_documents", Document),
        ("supporting_attachments", Attachment),
        "analyses",
        "results",
        "datasets",
    ),
    "manuscript": ("results",),
}


def queryset(kind, project, user):
    """The project's rows of `kind` with every nested read prefetched: no per-row queries."""
    from provenance.services import SPECS

    prefetch = [
        (
            Prefetch(
                p[0],
                queryset=p[1]
                .objects.visible_to(user, project.lab_id)
                .filter(deleted_at__isnull=True),
            )
            if isinstance(p, tuple)
            else p
        )
        for p in PREFETCH[kind]
    ]
    return (
        SPECS[kind]
        .model.objects.visible_to(user, project.lab_id)
        .filter(project=project)
        .select_related(*SELECT[kind])
        .prefetch_related(*prefetch)
        .order_by("-created_at", "id")
    )


# ---------------------------------------------------------------- input


def _ids():
    return serializers.ListField(child=serializers.UUIDField(), required=False, max_length=200)


def _text(n):
    return serializers.CharField(max_length=n, validators=[no_control_chars])


def _web_url():
    return serializers.CharField(
        max_length=200, allow_blank=True, required=False, validators=[validate_web_url]
    )


class DatasetInputSerializer(serializers.Serializer):
    name = _text(200)
    version_label = _text(100)
    location_text = serializers.CharField(allow_blank=True, required=False)
    location_url = _web_url()
    controlled_by = serializers.UUIDField(allow_null=True, required=False)
    access_notes = serializers.CharField(allow_blank=True, required=False)
    checksum = serializers.CharField(
        max_length=140, allow_blank=True, required=False, validators=[validate_checksum]
    )
    previous_version = serializers.UUIDField(allow_null=True, required=False)


class AnalysisInputSerializer(serializers.Serializer):
    title = _text(300)
    description = serializers.CharField(allow_blank=True, required=False)
    code_repo_url = _web_url()
    code_commit = serializers.CharField(
        max_length=40, allow_blank=True, required=False, validators=[validate_commit]
    )
    code_attachment = serializers.UUIDField(allow_null=True, required=False)
    datasets = _ids()
    ran_by = serializers.UUIDField(required=False)
    ran_at = serializers.DateTimeField(required=False)


class ResultInputSerializer(serializers.Serializer):
    title = _text(300)
    summary = serializers.CharField(allow_blank=True, required=False)
    analysis = serializers.UUIDField()
    attachments = _ids()


class DecisionInputSerializer(serializers.Serializer):
    title = _text(300)
    rationale = serializers.CharField(allow_blank=True, required=False)
    decided_on = serializers.DateField(required=False)
    decided_by = serializers.UUIDField(required=False)
    supporting_documents = _ids()
    supporting_attachments = _ids()
    references = ReferenceSerializer(many=True, required=False)
    analyses = _ids()
    results = _ids()
    datasets = _ids()


class ManuscriptInputSerializer(serializers.Serializer):
    title = _text(300)
    url = serializers.CharField(max_length=200, validators=[validate_web_url])
    status = serializers.ChoiceField(choices=ManuscriptStatus.choices, required=False)
    results = _ids()


INPUT = {
    "dataset": DatasetInputSerializer,
    "analysis": AnalysisInputSerializer,
    "result": ResultInputSerializer,
    "decision": DecisionInputSerializer,
    "manuscript": ManuscriptInputSerializer,
}

# ---------------------------------------------------------------- lineage and export


class LineageNodeSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.ChoiceField(choices=LineageKind.choices)
    label = serializers.CharField()
    subtitle = serializers.CharField()
    href_id = serializers.UUIDField()
    meta = serializers.DictField()


class LineageEdgeSerializer(serializers.Serializer):
    id = serializers.CharField()
    source = serializers.CharField()
    target = serializers.CharField()
    kind = serializers.ChoiceField(choices=LineageKind.choices)


class LineageSerializer(serializers.Serializer):
    nodes = LineageNodeSerializer(many=True)
    edges = LineageEdgeSerializer(many=True)


class ExportSerializer(serializers.Serializer):
    exported_at = serializers.DateTimeField()
    project = ProjectSerializer()
    tasks = TaskSerializer(many=True)
    deadlines = DeadlineSerializer(many=True)
    documents = DocumentSerializer(many=True)
    attachments = AttachmentSerializer(many=True)
    datasets = DatasetSerializer(many=True)
    analyses = AnalysisSerializer(many=True)
    results = ResultSerializer(many=True)
    decisions = DecisionSerializer(many=True)
    manuscripts = ManuscriptSerializer(many=True)
