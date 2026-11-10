"""Inputs are plain serializers (D33); the AI tools validate through the same ones."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from documents.serializers import AttachmentSerializer
from integrations.providers._refs import clean_doi
from papers import services
from papers.models import Paper, PaperNote
from provenance.models import validate_web_url

MAX_NOTE = 20_000
MAX_ABSTRACT = 20_000


class PaperInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500, validators=[no_control_chars])
    authors = serializers.ListField(
        child=serializers.CharField(max_length=200, validators=[no_control_chars]),
        max_length=200,
        required=False,
    )
    year = serializers.IntegerField(min_value=1000, max_value=2100, allow_null=True, required=False)
    venue = serializers.CharField(
        max_length=300, allow_blank=True, required=False, validators=[no_control_chars]
    )
    doi = serializers.CharField(max_length=200, allow_blank=True, required=False)
    url = serializers.CharField(
        max_length=500, allow_blank=True, required=False, validators=[validate_web_url]
    )
    abstract = serializers.CharField(max_length=MAX_ABSTRACT, allow_blank=True, required=False)

    def validate_doi(self, value):
        """D95, but a pasted doi.org link or `doi:` form is accepted and stored bare."""
        if not value.strip():
            return ""
        doi = clean_doi(value)
        if not doi:
            raise serializers.ValidationError("Enter a DOI like 10.1234/abcd.")
        return doi


class NoteInputSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=MAX_NOTE)


class PaperNoteSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = PaperNote
        fields = ["id", "paper", "author", "body", "created_at", "edited_at"]
        read_only_fields = fields


class PaperSerializer(serializers.ModelSerializer):
    authors = serializers.ListField(child=serializers.CharField(), read_only=True)
    added_by = UserSerializer(read_only=True)
    has_pdf = serializers.BooleanField(read_only=True)
    note_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Paper
        fields = [
            "id",
            "title",
            "authors",
            "year",
            "venue",
            "doi",
            "url",
            "added_by",
            "created_at",
            "has_pdf",
            "note_count",
        ]
        read_only_fields = fields


class PaperDetailSerializer(PaperSerializer):
    notes = serializers.SerializerMethodField()
    pdf = serializers.SerializerMethodField()

    class Meta(PaperSerializer.Meta):
        fields = [*PaperSerializer.Meta.fields, "abstract", "notes", "pdf"]
        read_only_fields = fields

    @extend_schema_field(PaperNoteSerializer(many=True))
    def get_notes(self, obj):
        qs = obj.notes.select_related("author").order_by("created_at", "id")
        return PaperNoteSerializer(qs, many=True).data

    @extend_schema_field(AttachmentSerializer(allow_null=True))
    def get_pdf(self, obj):
        pdf = services.live_pdf(obj)
        return AttachmentSerializer(pdf).data if pdf else None


class PaperCitationSerializer(serializers.Serializer):
    apa = serializers.CharField()
    mla = serializers.CharField()
    chicago = serializers.CharField()
    bibtex = serializers.CharField()


class PaperDoiLookupSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    title = serializers.CharField(required=False)
    authors = serializers.ListField(child=serializers.CharField(), required=False)
    year = serializers.IntegerField(allow_null=True, required=False)
    venue = serializers.CharField(required=False)
    doi = serializers.CharField(required=False)
    url = serializers.CharField(required=False)
    abstract = serializers.CharField(required=False)


class ZoteroItemSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()


class ZoteroImportSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.CharField(max_length=40), allow_empty=False, max_length=20
    )
