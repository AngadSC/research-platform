from rest_framework import serializers

from core.models import Institution
from core.permissions import LAB_ROLE_PERMS, lab_role
from core.serializers import UserSerializer, no_control_chars
from labs.admin_serializers import web_url
from labs.models import GoogleChatBridge, Invite, Lab, LabChatMessage, LabMembership, LabRole
from projects.serializers import ReactionsMixin  # D321: shared with project chat


class InstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ["id", "name"]


class LabSerializer(serializers.ModelSerializer):
    institution = InstitutionSerializer(read_only=True)
    institution_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=200,
        validators=[no_control_chars],
    )  # only read on create; PATCH uses LabDetailsInputSerializer
    # D237: filled from the institution picked when the lab is made. PATCH does not use these.
    address = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    website = serializers.CharField(
        required=False, allow_blank=True, max_length=300, validators=[web_url]
    )
    my_role = serializers.SerializerMethodField()
    my_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Lab
        fields = [
            "id",
            "name",
            "institution",
            "institution_name",
            "department",
            "description",
            "address",
            "contact_email",
            "website",
            "inventory_enabled",
            "my_role",
            "my_permissions",
        ]
        read_only_fields = [
            "id",
            "department",
            "description",
            "contact_email",
            "inventory_enabled",
        ]
        extra_kwargs = {"name": {"validators": [no_control_chars]}}

    def get_my_role(self, lab) -> str | None:
        return lab_role(self.context["request"].user, lab)

    def get_my_permissions(self, lab) -> list[str]:
        role = self.get_my_role(lab)
        return sorted(p.value for p in LAB_ROLE_PERMS.get(role, ()))


class MemberUserSerializer(UserSerializer):
    """The members list also shows each person's short bio."""

    class Meta(UserSerializer.Meta):
        fields = [*UserSerializer.Meta.fields, "bio"]
        read_only_fields = UserSerializer.Meta.fields + ["bio"]


class MembershipSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

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


# ---------------------------------------------------------------- lab chat and Google Chat (D316)


class LabChatMessageSerializer(ReactionsMixin, serializers.ModelSerializer):
    """The project chat's shape plus where it came from. `author` is null for a message from
    someone in Google Chat who has no connected account here; `external_author` names them."""

    author = UserSerializer(read_only=True, allow_null=True)

    class Meta:
        model = LabChatMessage
        fields = ["id", "author", "external_author", "source", "body", "reactions", "created_at"]
        read_only_fields = fields


class GoogleChatBridgeSerializer(serializers.ModelSerializer):
    """What every member sees of the link; `last_error` and `last_polled_at` help whoever
    manages it."""

    linked_by = UserSerializer(source="created_by", read_only=True)

    class Meta:
        model = GoogleChatBridge
        fields = ["space", "space_name", "linked_by", "last_polled_at", "last_error", "created_at"]
        read_only_fields = fields


class GoogleChatStatusSerializer(serializers.Serializer):
    bridge = GoogleChatBridgeSerializer(allow_null=True)
    configured = serializers.BooleanField(help_text="The site has a Google Chat app set up.")
    connected = serializers.BooleanField(help_text="You have connected Google Chat in this lab.")
    can_manage = serializers.BooleanField()


class GoogleChatSpaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    display_name = serializers.CharField()


class GoogleChatThreadSerializer(serializers.Serializer):
    name = serializers.CharField()
    first = serializers.CharField(allow_blank=True, help_text="The thread's first words.")
    count = serializers.IntegerField(help_text="Messages among the space's recent ones.")
    last_at = serializers.DateTimeField()


class GoogleChatImportInputSerializer(serializers.Serializer):
    space = serializers.CharField(max_length=120)
    thread = serializers.CharField(max_length=260)


class GoogleChatLinkInputSerializer(serializers.Serializer):
    space = serializers.CharField(max_length=120)


class LinkPreviewSerializer(serializers.Serializer):
    """D322: plain text only; the client shows it as text, never as markup."""

    url = serializers.CharField()
    host = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    site_name = serializers.CharField(allow_blank=True)
