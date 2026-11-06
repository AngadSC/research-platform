"""Serializers for training (D175-D179). Inputs are plain serializers (D33); ids are resolved
inside the lab by the services."""

from rest_framework import serializers

from core.models import User
from core.serializers import UserSerializer, no_control_chars
from labs.admin_serializers import https_url
from labs.models import LabRole
from training.models import (
    AppliesTo,
    ComplianceStatus,
    TrainingCategory,
    TrainingRecord,
    TrainingRequirement,
)


class TrainingRequirementSerializer(serializers.ModelSerializer):
    projects = serializers.SerializerMethodField()

    class Meta:
        model = TrainingRequirement
        fields = [
            "id",
            "name",
            "category",
            "validity_months",
            "applies_to",
            "roles",
            "projects",
            "url",
            "notes",
        ]
        read_only_fields = fields

    def get_projects(self, obj) -> list[str]:
        return sorted(str(p.pk) for p in obj.projects.all())


class TrainingRequirementInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    category = serializers.ChoiceField(choices=TrainingCategory.choices)
    validity_months = serializers.IntegerField(
        min_value=1, max_value=600, allow_null=True, required=False
    )
    applies_to = serializers.ChoiceField(choices=AppliesTo.choices, required=False)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=LabRole.choices), required=False
    )
    projects = serializers.ListField(child=serializers.UUIDField(), required=False)
    url = serializers.CharField(max_length=500, allow_blank=True, required=False)
    notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)

    def validate_url(self, value):
        return https_url(value) if value else value


class TrainingRecordSerializer(serializers.ModelSerializer):
    requirement = serializers.UUIDField(source="requirement_id")
    requirement_name = serializers.CharField(source="requirement.name")
    user = UserSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)
    has_certificate = serializers.SerializerMethodField()

    class Meta:
        model = TrainingRecord
        fields = [
            "id",
            "requirement",
            "requirement_name",
            "user",
            "completed_on",
            "expires_on",
            "notes",
            "verified_by",
            "verified_at",
            "has_certificate",
            "created_at",
        ]
        read_only_fields = fields

    def get_has_certificate(self, obj) -> bool:
        return any(a.deleted_at is None for a in obj.attachments.all())


class TrainingRecordCreateSerializer(serializers.Serializer):
    requirement = serializers.UUIDField()
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    completed_on = serializers.DateField()
    expires_on = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)


class TrainingRecordUpdateSerializer(serializers.Serializer):
    completed_on = serializers.DateField(required=False)
    expires_on = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)


class TrainingCellSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ComplianceStatus.choices)
    record = serializers.UUIDField(allow_null=True)
    completed_on = serializers.DateField(allow_null=True)
    expires_on = serializers.DateField(allow_null=True)
    days_left = serializers.IntegerField(allow_null=True)
    verified = serializers.BooleanField()


class TrainingComplianceMemberSerializer(serializers.Serializer):
    user = UserSerializer()
    role = serializers.CharField()
    cells = serializers.DictField(
        child=TrainingCellSerializer(allow_null=True)
    )  # key: requirement id


class TrainingComplianceSummarySerializer(serializers.Serializer):
    done = serializers.IntegerField()
    expiring = serializers.IntegerField()
    expired = serializers.IntegerField()
    missing = serializers.IntegerField()


class TrainingComplianceSerializer(serializers.Serializer):
    requirements = TrainingRequirementSerializer(many=True)
    members = TrainingComplianceMemberSerializer(many=True)
    summary = TrainingComplianceSummarySerializer()


class ExpiringItemSerializer(serializers.Serializer):
    user = UserSerializer()
    requirement = TrainingRequirementSerializer()
    status = serializers.ChoiceField(choices=ComplianceStatus.choices)
    expires_on = serializers.DateField()
    days_left = serializers.IntegerField()


class ExpiringSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    count = serializers.IntegerField()
    expired_count = serializers.IntegerField()
    items = ExpiringItemSerializer(many=True)
