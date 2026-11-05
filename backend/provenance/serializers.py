import re

from django.db.models import Prefetch
from rest_framework import serializers

from core.permissions import Perm, can
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
    FundingRecord,
    FundingStatus,
    LineageKind,
    ManuscriptLink,
    ManuscriptStatus,
    RecruitmentEntry,
    RecruitmentPlan,
    RecruitmentStatus,
    Result,
    ReviewItem,
    ReviewStatus,
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


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
MAX_REFERENCES = 50


class ReferenceSerializer(serializers.Serializer):
    """D95: a title is required; url is http(s) only; doi looks like 10.1234/abc."""

    title = serializers.CharField(max_length=300, validators=[no_control_chars])
    url = serializers.CharField(
        max_length=500, allow_blank=True, required=False, validators=[validate_web_url]
    )
    doi = serializers.RegexField(
        DOI_RE,
        max_length=200,
        allow_blank=True,
        required=False,
        error_messages={"invalid": "Enter a DOI like 10.1234/abcd."},
    )


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


class FundingSerializer(serializers.ModelSerializer):
    """D133: `amount` and `currency` are null for anyone who is not a project lead."""

    holder = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    attachment = AttachmentRefSerializer(read_only=True)

    class Meta:
        model = FundingRecord
        fields = [
            "id",
            "project",
            "funder",
            "program",
            "award_number",
            "amount",
            "currency",
            "start_date",
            "end_date",
            "status",
            "holder",
            "notes",
            "attachment",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = self.context["request"].user
        if not self.context.setdefault("_funding_lead", {}).setdefault(
            instance.project_id, can(user, Perm.EDIT_PROJECT, instance.project)
        ):
            data["amount"] = data["currency"] = None
        return data


class ReviewItemSerializer(serializers.ModelSerializer):
    reviewer = UserSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = ReviewItem
        fields = [
            "id",
            "project",
            "title",
            "reviewer",
            "status",
            "due_date",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RecruitmentEntrySerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = RecruitmentEntry
        fields = [
            "id",
            "project",
            "entry_date",
            "status",
            "count",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RecruitmentPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecruitmentPlan
        fields = ["target_enrolment", "notes"]
        read_only_fields = fields


OUTPUT = {
    "dataset": DatasetSerializer,
    "analysis": AnalysisSerializer,
    "result": ResultSerializer,
    "decision": DecisionSerializer,
    "manuscript": ManuscriptSerializer,
    "funding": FundingSerializer,
    "review": ReviewItemSerializer,
    "recruitment": RecruitmentEntrySerializer,
}
PLURAL = {
    "dataset": "datasets",
    "analysis": "analyses",
    "result": "results",
    "decision": "decisions",
    "manuscript": "manuscripts",
    "funding": "funding",
    "review": "review_items",
    "recruitment": "recruitment_entries",
}
SELECT = {
    "dataset": ("controlled_by", "created_by", "previous_version"),
    "analysis": ("ran_by", "code_attachment"),
    "result": ("created_by", "analysis"),
    "decision": ("decided_by",),
    "manuscript": ("created_by",),
    "funding": ("holder", "created_by", "attachment", "project"),
    "review": ("reviewer", "created_by"),
    "recruitment": ("created_by",),
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
    "funding": (),
    "review": (),
    "recruitment": (),
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
    references = ReferenceSerializer(many=True, required=False, max_length=MAX_REFERENCES)
    analyses = _ids()
    results = _ids()
    datasets = _ids()


class ManuscriptInputSerializer(serializers.Serializer):
    title = _text(300)
    url = serializers.CharField(max_length=200, validators=[validate_web_url])
    status = serializers.ChoiceField(choices=ManuscriptStatus.choices, required=False)
    results = _ids()


EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def no_email(value):
    """D136: a cheap guard, not a filter. Names cannot be detected; an address can."""
    if EMAIL_RE.search(value):
        raise serializers.ValidationError(
            "Don't enter names or identifying details here (that looks like an email address)."
        )


class FundingInputSerializer(serializers.Serializer):
    funder = _text(200)
    program = serializers.CharField(max_length=300, allow_blank=True, required=False)
    award_number = serializers.CharField(max_length=100, allow_blank=True, required=False)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    currency = serializers.RegexField(r"^[A-Z]{3}$", required=False)
    start_date = serializers.DateField(allow_null=True, required=False)
    end_date = serializers.DateField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=FundingStatus.choices, required=False)
    holder = serializers.UUIDField(allow_null=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)
    attachment = serializers.UUIDField(allow_null=True, required=False)


class ReviewItemInputSerializer(serializers.Serializer):
    title = _text(300)
    reviewer = serializers.UUIDField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=ReviewStatus.choices, required=False)
    due_date = serializers.DateField(allow_null=True, required=False)
    notes = serializers.CharField(allow_blank=True, required=False)


class RecruitmentEntryInputSerializer(serializers.Serializer):
    entry_date = serializers.DateField()
    status = serializers.ChoiceField(choices=RecruitmentStatus.choices)
    count = serializers.IntegerField(min_value=0, max_value=1_000_000)
    notes = serializers.CharField(
        max_length=500, allow_blank=True, required=False, validators=[no_control_chars, no_email]
    )


class RecruitmentPlanInputSerializer(serializers.Serializer):
    target_enrolment = serializers.IntegerField(
        min_value=0, max_value=1_000_000, allow_null=True, required=False
    )
    notes = serializers.CharField(
        allow_blank=True, required=False, max_length=5000, validators=[no_email]
    )


INPUT = {
    "dataset": DatasetInputSerializer,
    "analysis": AnalysisInputSerializer,
    "result": ResultInputSerializer,
    "decision": DecisionInputSerializer,
    "manuscript": ManuscriptInputSerializer,
    "funding": FundingInputSerializer,
    "review": ReviewItemInputSerializer,
    "recruitment": RecruitmentEntryInputSerializer,
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
    funding = FundingSerializer(many=True)
    review_items = ReviewItemSerializer(many=True)
    recruitment_entries = RecruitmentEntrySerializer(many=True)
    recruitment_plan = RecruitmentPlanSerializer()
