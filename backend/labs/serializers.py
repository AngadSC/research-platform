from rest_framework import serializers

from core.models import Institution
from core.permissions import LAB_ROLE_PERMS, lab_role
from core.serializers import UserSerializer, no_control_chars
from labs.models import Invite, Lab, LabMembership, LabRole


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ["id", "name"]


class LabSerializer(serializers.ModelSerializer):
    institution = InstitutionSerializer(read_only=True)
    my_role = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Lab
        fields = ["id", "name", "institution", "my_role", "my_permissions"]
        read_only_fields = ["id"]
        extra_kwargs = {"name": {"validators": [no_control_chars]}}

    def get_my_role(self, lab) -> str | None:
        return lab_role(self.context["request"].user, lab)

    def get_my_permissions(self, lab) -> list[str]:
        role = self.get_my_role(lab)
        return sorted(p.value for p in LAB_ROLE_PERMS.get(role, ()))


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = LabMembership
        fields = ["id", "user", "role", "created_at"]
        read_only_fields = ["id", "user", "created_at"]


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=LabRole.choices)


class InviteSerializer(serializers.ModelSerializer):
    invited_by = UserSerializer(read_only=True)

    class Meta:
        model = Invite
        fields = ["id", "email", "role", "expires_at", "created_at", "invited_by"]
        read_only_fields = fields


class InviteCreateSerializer(RoleSerializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class InvitePreviewSerializer(serializers.Serializer):
    lab_name = serializers.CharField()
    role = serializers.CharField()
    email = serializers.EmailField()
