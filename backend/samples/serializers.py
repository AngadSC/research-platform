"""Inputs are plain (D33); ids are resolved, and checked against the lab, in services.py."""

import re

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import UserSerializer, no_control_chars
from samples.models import (
    MAX_SIDE,
    Sample,
    SampleKind,
    SampleStatus,
    StorageBox,
    StorageKind,
    StorageUnit,
    Tube,
)

BASES = re.compile(r"^[ACGTUNRYKMSWBDHVI]*$")


def primer_tm(seq: str) -> float | None:
    """Rough melting temperature: the Wallace rule under 14 bases, else the basic GC formula.
    None for an empty sequence or one with ambiguous bases."""
    s = seq.upper()
    gc = s.count("G") + s.count("C")
    at = s.count("A") + s.count("T") + s.count("U")
    if not s or gc + at != len(s):
        return None
    if len(s) < 14:
        return float(2 * at + 4 * gc)
    return round(64.9 + 41 * (gc - 16.4) / len(s), 1)


def _text(n, **kw):
    return serializers.CharField(
        max_length=n, allow_blank=True, required=False, validators=[no_control_chars], **kw
    )


class SampleRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sample
        fields = ["id", "code", "name", "kind"]
        read_only_fields = fields


class TubeSampleSerializer(serializers.ModelSerializer):
    """A tube where it sits: for a sample's own list and for "where is P0012"."""

    position = serializers.CharField(read_only=True)
    owner = UserSerializer(read_only=True)
    box = serializers.UUIDField(source="box_id", read_only=True)
    box_name = serializers.CharField(source="box.name", read_only=True)
    unit = serializers.UUIDField(source="box.unit_id", read_only=True)
    unit_name = serializers.CharField(source="box.unit.name", read_only=True)

    class Meta:
        model = Tube
        fields = [
            "id",
            "box",
            "box_name",
            "unit",
            "unit_name",
            "row",
            "col",
            "position",
            "label",
            "amount",
            "stored_on",
            "owner",
        ]
        read_only_fields = fields


class SampleSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    tm = serializers.SerializerMethodField(help_text="Primer melting temperature, °C (rough).")
    tubes = TubeSampleSerializer(many=True, read_only=True)

    def get_tm(self, s) -> float | None:
        return primer_tm(s.sequence) if s.kind == SampleKind.PRIMER else None

    class Meta:
        model = Sample
        fields = [
            "id",
            "kind",
            "code",
            "name",
            "description",
            "owner",
            "status",
            "backbone",
            "insert",
            "resistance",
            "tag",
            "species",
            "genotype",
            "sequence",
            "tm",
            "concentration",
            "buffer",
            "made_on",
            "tubes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProjectRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class SampleFileSerializer(serializers.Serializer):
    """An upload on the sample (`on_sample`) or a project file linked to it."""

    id = serializers.UUIDField()
    name = serializers.CharField(source="original_filename")
    content_type = serializers.CharField()
    size_bytes = serializers.IntegerField()
    from_drive = serializers.BooleanField()
    uploaded_by = UserSerializer()
    created_at = serializers.DateTimeField()
    on_sample = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()

    def get_on_sample(self, a) -> bool:
        return a.sample_id is not None

    @extend_schema_field(ProjectRefSerializer(allow_null=True))
    def get_project(self, a):
        return {"id": a.project.pk, "name": a.project.name} if a.project_id else None


class SampleDetailSerializer(SampleSerializer):
    """The view passes what the reader may see in the context; nothing here queries."""

    parents = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()

    @extend_schema_field(SampleRefSerializer(many=True))
    def get_parents(self, s):
        return SampleRefSerializer(self.context["parents"], many=True).data

    @extend_schema_field(SampleRefSerializer(many=True))
    def get_children(self, s):
        return SampleRefSerializer(self.context["children"], many=True).data

    @extend_schema_field(ProjectRefSerializer(many=True))
    def get_projects(self, s):
        return ProjectRefSerializer(self.context["projects"], many=True).data

    @extend_schema_field(SampleFileSerializer(many=True))
    def get_files(self, s):
        return SampleFileSerializer(self.context["files"], many=True).data

    class Meta(SampleSerializer.Meta):
        fields = [*SampleSerializer.Meta.fields, "parents", "children", "projects", "files"]
        read_only_fields = fields


class SampleInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SampleKind.choices)
    code = serializers.CharField(
        max_length=32, required=False, help_text="Left out on create: the next free code."
    )
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    description = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    owner = serializers.UUIDField(allow_null=True, required=False)
    status = serializers.ChoiceField(choices=SampleStatus.choices, required=False)
    backbone = _text(200)
    insert = _text(200)
    resistance = _text(200)
    tag = _text(200)
    species = _text(200)
    genotype = _text(500)
    sequence = _text(500, help_text="5' to 3'. Spaces are dropped.")
    concentration = _text(64)
    buffer = _text(200)
    made_on = serializers.DateField(allow_null=True, required=False)
    parents = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=50)
    projects = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=50)
    linked_files = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=50
    )

    def validate_code(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]*", value):
            raise serializers.ValidationError("Use letters, numbers, dots and dashes, like P0012.")
        return value

    def validate_sequence(self, value):
        value = re.sub(r"\s+", "", value).upper()
        if not BASES.fullmatch(value):
            raise serializers.ValidationError("Use only base letters (A, C, G, T, and N).")
        return value


class TubeSerializer(serializers.ModelSerializer):
    """A tube in a box grid."""

    position = serializers.CharField(read_only=True)
    owner = UserSerializer(read_only=True)
    sample = SampleRefSerializer(read_only=True)

    class Meta:
        model = Tube
        fields = [
            "id",
            "box",
            "row",
            "col",
            "position",
            "sample",
            "label",
            "amount",
            "stored_on",
            "owner",
        ]
        read_only_fields = fields


class TubeInputSerializer(serializers.Serializer):
    box = serializers.UUIDField()
    row = serializers.IntegerField(min_value=1, max_value=MAX_SIDE)
    col = serializers.IntegerField(min_value=1, max_value=MAX_SIDE)
    sample = serializers.UUIDField()
    label = _text(100)
    amount = _text(64)
    stored_on = serializers.DateField(allow_null=True, required=False)
    owner = serializers.UUIDField(
        allow_null=True, required=False, help_text="Who holds it; you, when left out on place."
    )


class BoxSerializer(serializers.ModelSerializer):
    filled = serializers.IntegerField(read_only=True, help_text="Tubes in the box.")

    class Meta:
        model = StorageBox
        fields = ["id", "unit", "name", "rows", "cols", "shelf", "filled"]
        read_only_fields = fields


class BoxDetailSerializer(BoxSerializer):
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    tubes = TubeSerializer(many=True, read_only=True)

    class Meta(BoxSerializer.Meta):
        fields = [*BoxSerializer.Meta.fields, "unit_name", "tubes"]
        read_only_fields = fields


class BoxInputSerializer(serializers.Serializer):
    unit = serializers.UUIDField()
    name = serializers.CharField(max_length=100, validators=[no_control_chars])
    rows = serializers.IntegerField(min_value=1, max_value=MAX_SIDE, required=False)
    cols = serializers.IntegerField(min_value=1, max_value=MAX_SIDE, required=False)
    shelf = _text(100)


class EquipmentRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class UnitSerializer(serializers.ModelSerializer):
    equipment = EquipmentRefSerializer(read_only=True, allow_null=True)
    boxes = BoxSerializer(many=True, read_only=True)

    class Meta:
        model = StorageUnit
        fields = ["id", "name", "kind", "temperature", "location", "equipment", "boxes"]
        read_only_fields = fields


class UnitInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, validators=[no_control_chars])
    kind = serializers.ChoiceField(choices=StorageKind.choices, required=False)
    temperature = _text(32)
    location = _text(200)
    equipment = serializers.UUIDField(allow_null=True, required=False)


class SampleImportInputSerializer(serializers.Serializer):
    file = serializers.FileField()
    commit = serializers.BooleanField(required=False, default=False)  # false means preview only


class SampleImportRowSerializer(serializers.Serializer):
    row = serializers.IntegerField(help_text="The line in the file (the header is line 1).")
    code = serializers.CharField(help_text="The code it gets; suggested when the file has none.")
    kind = serializers.CharField()
    name = serializers.CharField()
    errors = serializers.DictField(child=serializers.CharField())


class SampleImportResultSerializer(serializers.Serializer):
    rows = SampleImportRowSerializer(many=True)
    valid = serializers.IntegerField()
    invalid = serializers.IntegerField()
    imported = serializers.IntegerField(help_text="Entries added; 0 for a preview.")
    ignored_columns = serializers.ListField(child=serializers.CharField())
