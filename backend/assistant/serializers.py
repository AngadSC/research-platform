"""Explicit field lists: no token, hash or client secret is ever serialized (D162)."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from assistant.models import Access, AIGrant
from assistant.services import PAT_MAX_DAYS


class LabRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class GrantSerializer(serializers.ModelSerializer):
    labs = LabRefSerializer(many=True, read_only=True)
    client_name = serializers.SerializerMethodField()

    class Meta:
        model = AIGrant
        fields = [
            "id",
            "kind",
            "name",
            "client_name",
            "labs",
            "access",
            "created_at",
            "last_used_at",
            "expires_at",
            "revoked_at",
            "revoked_reason",
        ]
        read_only_fields = fields

    def get_client_name(self, grant) -> str:
        return grant.client.name if grant.client_id else ""


class GrantUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    display_name = serializers.CharField()
    email = serializers.EmailField()


class LabGrantSerializer(GrantSerializer):
    """The lab view of a member's grant. `labs` is only the lab being viewed (D203): a manager
    must not learn which other labs the member belongs to."""

    user = GrantUserSerializer(read_only=True)
    labs = serializers.SerializerMethodField()

    @extend_schema_field(LabRefSerializer(many=True))
    def get_labs(self, grant) -> list[dict]:
        lab = self.context["request"].lab
        return (
            [{"id": lab.pk, "name": lab.name}]
            if any(x.pk == lab.pk for x in grant.labs.all())
            else []
        )

    class Meta(GrantSerializer.Meta):
        fields = [*GrantSerializer.Meta.fields, "user"]
        read_only_fields = fields


class PatCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    labs = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=50)
    access = serializers.ChoiceField(choices=Access.choices)
    expires_in_days = serializers.IntegerField(min_value=1, max_value=PAT_MAX_DAYS)


class PatCreatedSerializer(GrantSerializer):
    token = serializers.CharField(read_only=True, help_text="Shown once; only a hash is kept.")

    class Meta(GrantSerializer.Meta):
        fields = [*GrantSerializer.Meta.fields, "token"]
        read_only_fields = fields


class AuthorizeSerializer(serializers.Serializer):
    """The query the MCP client sent to /oauth/authorize, plus the person's decision."""

    response_type = serializers.CharField(required=False, allow_blank=True)
    client_id = serializers.CharField(max_length=255)
    redirect_uri = serializers.CharField(max_length=500)
    code_challenge = serializers.CharField(required=False, allow_blank=True, max_length=128)
    code_challenge_method = serializers.CharField(required=False, allow_blank=True)
    state = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    scope = serializers.CharField(required=False, allow_blank=True, max_length=500)
    resource = serializers.CharField(required=False, allow_blank=True, max_length=500)
    decision = serializers.ChoiceField(choices=["check", "approve", "deny"])
    labs = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=50)
    access = serializers.ChoiceField(choices=Access.choices, required=False)


class ConsentLabSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()


class ConsentClientSerializer(serializers.Serializer):
    name = serializers.CharField()
    verified_host = serializers.CharField(allow_null=True)
    redirect_host = serializers.CharField()
    loopback = serializers.BooleanField()


class AuthorizeResultSerializer(serializers.Serializer):
    client = ConsentClientSerializer(required=False)
    requested_access = serializers.CharField(required=False)
    labs = ConsentLabSerializer(many=True, required=False)
    redirect = serializers.CharField(required=False)
    error = serializers.CharField(required=False)
    error_description = serializers.CharField(required=False)
