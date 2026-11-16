from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core import link_preview, reactions
from core.permissions import Perm, can, labs_for
from core.views import LabScopedViewMixin
from integrations.http import IntegrationError
from labs import admin_services, google_chat, ror, services
from labs.admin_serializers import LabDetailsInputSerializer
from labs.models import GoogleChatBridge, Invite, LabChatMessage, LabMembership
from labs.serializers import (
    GoogleChatImportInputSerializer,
    GoogleChatImportResultSerializer,
    GoogleChatLinkInputSerializer,
    GoogleChatSpaceSerializer,
    GoogleChatStatusSerializer,
    GoogleChatThreadSerializer,
    InviteCreateSerializer,
    InvitePreviewSerializer,
    InviteSerializer,
    LabChatMessageSerializer,
    LabSerializer,
    LinkPreviewSerializer,
    MembershipSerializer,
    RoleSerializer,
    TokenSerializer,
)
from projects.serializers import (
    ChatMessageFilterSerializer,
    ChatMessageInputSerializer,
    ChatReadInputSerializer,
    ReactionInputSerializer,
)


class LabListCreateView(generics.GenericAPIView):
    serializer_class = LabSerializer
    perms = {"GET": Perm.AUTHENTICATED, "POST": Perm.AUTHENTICATED}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "lab_create"

    def get_throttles(self):  # creation only; listing is not rate limited
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses=LabSerializer(many=True))
    def get(self, request):
        return Response(self.get_serializer(labs_for(request.user), many=True).data)

    @extend_schema(responses={201: LabSerializer})
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        lab = services.create_lab(
            user=request.user,
            name=ser.validated_data["name"],
            institution_name=ser.validated_data.get("institution_name", ""),
            address=ser.validated_data.get("address", ""),
            website=ser.validated_data.get("website", ""),
            request=request,
        )
        return Response(self.get_serializer(lab).data, status=status.HTTP_201_CREATED)


class InstitutionSearchView(APIView):
    """Type-ahead for the institution field (D237). Not lab data, so any signed-in person may
    use it, before they have a lab. If ROR is down the field is still plain free text."""

    perms = {"GET": Perm.AUTHENTICATED}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "institution_search"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="What has been typed so far.")],
        responses=inline_serializer(
            "InstitutionSearch",
            {
                "results": inline_serializer(
                    "InstitutionHit",
                    {
                        "id": serializers.CharField(),
                        "name": serializers.CharField(),
                        "address": serializers.CharField(),
                        "website": serializers.CharField(),
                    },
                    many=True,
                )
            },
        ),
    )
    def get(self, request):
        try:
            results = ror.search(request.query_params.get("q", ""))
        except IntegrationError:
            results = []
        return Response({"results": results})


class LabDetailView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = LabSerializer
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_LAB}

    def get(self, request, lab_id):
        return Response(self.get_serializer(request.lab).data)

    @extend_schema(request=LabDetailsInputSerializer, responses=LabSerializer)
    def patch(self, request, lab_id):
        ser = LabDetailsInputSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        lab = admin_services.update_lab_details(
            lab=request.lab, user=request.user, data=ser.validated_data, request=request
        )
        return Response(self.get_serializer(lab).data)


class LabChatMixin(LabScopedViewMixin):
    """The project chat's API (D206, D207) for the whole lab. The same message shape plus where a
    message came from (D316), since the lab chat can be linked to Google Chat."""

    model = LabChatMessage
    serializer_class = LabChatMessageSerializer
    pagination_class = None
    page_size = 100  # must match CHAT_PAGE_SIZE in the client

    def get_queryset(self):
        return super().get_queryset().select_related("author")


class LabChatListView(LabChatMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}  # viewers too, as project chat (D206)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    def get_throttles(self):  # sending only; polling is not rate limited
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(
        parameters=[ChatMessageFilterSerializer], responses=LabChatMessageSerializer(many=True)
    )
    def get(self, request, lab_id):
        """The newest page, oldest first; `before` (a message's created_at) pages back."""
        filters = ChatMessageFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        qs = self.get_queryset()
        if "before" in filters.validated_data:
            qs = qs.filter(created_at__lt=filters.validated_data["before"])
        page = list(qs.order_by("-created_at", "-id")[: self.page_size])
        return Response(self.get_serializer(reversed(page), many=True).data)

    @extend_schema(request=ChatMessageInputSerializer, responses={201: LabChatMessageSerializer})
    def post(self, request, lab_id):
        ser = ChatMessageInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        message = services.post_lab_message(
            lab=request.lab, by=request.user, body=ser.validated_data["body"]
        )
        return Response(self.get_serializer(message).data, status=status.HTTP_201_CREATED)


class LabChatDetailView(LabChatMixin, generics.GenericAPIView):
    lookup_url_kwarg = "labchatmessage_id"
    perms = {"DELETE": Perm.VIEW_LAB}  # services.delete_lab_message narrows this

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, labchatmessage_id):
        services.delete_lab_message(message=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LabChatReactionView(LabChatMixin, generics.GenericAPIView):
    """D321: add or take away your emoji on a lab chat message."""

    lookup_url_kwarg = "labchatmessage_id"
    perms = {"POST": Perm.VIEW_LAB}

    @extend_schema(request=ReactionInputSerializer, responses=LabChatMessageSerializer)
    def post(self, request, lab_id, labchatmessage_id):
        message = self.get_object()
        ser = ReactionInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        message = reactions.toggle(
            self.get_queryset(), message.pk, request.user, ser.validated_data["emoji"]
        )
        return Response(self.get_serializer(message).data)


class LabChatReadView(LabChatMixin, generics.GenericAPIView):
    serializer_class = ChatReadInputSerializer
    perms = {"POST": Perm.VIEW_LAB}

    @extend_schema(request=ChatReadInputSerializer, responses={204: None})
    def post(self, request, lab_id):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.mark_lab_chat_read(
            lab=request.lab, user=request.user, read_to=ser.validated_data["last_read_at"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class LinkPreviewView(LabScopedViewMixin, generics.GenericAPIView):
    """D322: a web page's title and description, for a link pasted in chat. Any member; the
    page is read by the server through the SSRF-safe client, and the answer is plain text."""

    model = LabChatMessage
    serializer_class = LinkPreviewSerializer
    perms = {"GET": Perm.VIEW_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "link_preview"

    @extend_schema(
        parameters=[OpenApiParameter("url", str, required=True)], responses=LinkPreviewSerializer
    )
    def get(self, request, lab_id):
        try:
            data = link_preview.preview(request.query_params.get("url", ""))
        except ValueError:
            raise serializers.ValidationError(
                {"url": ["This address can't be previewed."]}
            ) from None
        return Response(LinkPreviewSerializer(data).data)


class GoogleChatView(LabScopedViewMixin, generics.GenericAPIView):
    """D318: the lab chat's link to a Google Chat space. Everyone sees whether it is linked, so
    the composer can say where messages also go; `manage_lab_integrations` links and unlinks."""

    model = GoogleChatBridge
    serializer_class = GoogleChatStatusSerializer
    perms = {
        "GET": Perm.VIEW_LAB,
        "PUT": Perm.MANAGE_LAB_INTEGRATIONS,
        "DELETE": Perm.MANAGE_LAB_INTEGRATIONS,
    }

    def _status(self, request):
        lab, user = request.lab, request.user
        return Response(
            GoogleChatStatusSerializer(
                {
                    "bridge": google_chat.bridge_for(lab),
                    "configured": google_chat.PROVIDER.configured,
                    "connected": google_chat.own_account(lab, user) is not None,
                    "can_manage": can(user, Perm.MANAGE_LAB_INTEGRATIONS, lab),
                }
            ).data
        )

    def get(self, request, lab_id):
        return self._status(request)

    @extend_schema(request=GoogleChatLinkInputSerializer, responses=GoogleChatStatusSerializer)
    def put(self, request, lab_id):
        ser = GoogleChatLinkInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        google_chat.link_space(
            lab=request.lab, by=request.user, space=ser.validated_data["space"], request=request
        )
        return self._status(request)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id):
        google_chat.unlink_space(lab=request.lab, by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoogleChatSpacesView(LabScopedViewMixin, generics.GenericAPIView):
    """The spaces the caller's own Google Chat connection is in, to pick one (D318)."""

    model = GoogleChatBridge
    serializer_class = GoogleChatSpaceSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_LAB_INTEGRATIONS}

    @extend_schema(responses=GoogleChatSpaceSerializer(many=True))
    def get(self, request, lab_id):
        spaces = google_chat.list_spaces(request.lab, request.user)
        return Response(GoogleChatSpaceSerializer(spaces, many=True).data)


class GoogleChatThreadsView(LabScopedViewMixin, generics.GenericAPIView):
    """D327: a conversation's recent threads, to import one into the lab chat."""

    model = GoogleChatBridge
    serializer_class = GoogleChatThreadSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_LAB_INTEGRATIONS}

    @extend_schema(
        parameters=[OpenApiParameter("space", str, required=True)],
        responses=GoogleChatThreadSerializer(many=True),
    )
    def get(self, request, lab_id):
        rows = google_chat.list_threads(
            request.lab, request.user, request.query_params.get("space", "")
        )
        return Response(GoogleChatThreadSerializer(rows, many=True).data)


class GoogleChatImportView(LabScopedViewMixin, generics.GenericAPIView):
    """D327: copy a Google Chat thread or conversation into the lab chat, as messages."""

    model = GoogleChatBridge
    serializer_class = GoogleChatImportInputSerializer
    perms = {"POST": Perm.MANAGE_LAB_INTEGRATIONS}

    @extend_schema(
        request=GoogleChatImportInputSerializer, responses=GoogleChatImportResultSerializer
    )
    def post(self, request, lab_id):
        ser = GoogleChatImportInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = google_chat.import_messages(
            lab=request.lab, user=request.user, request=request, **ser.validated_data
        )
        return Response(GoogleChatImportResultSerializer(result).data)


class MemberListView(LabScopedViewMixin, generics.ListAPIView):
    model = LabMembership
    serializer_class = MembershipSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    def get_queryset(self):
        return super().get_queryset().select_related("user").order_by("created_at")


class MemberDetailView(LabScopedViewMixin, generics.GenericAPIView):
    model = LabMembership
    serializer_class = MembershipSerializer
    lookup_url_kwarg = "membership_id"
    perms = {"PATCH": Perm.MANAGE_MEMBERS, "DELETE": Perm.MANAGE_MEMBERS}

    @extend_schema(request=RoleSerializer, responses=MembershipSerializer)
    def patch(self, request, lab_id, membership_id):
        membership = self.get_object()
        ser = RoleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        membership = services.change_role(
            membership=membership, by=request.user, role=ser.validated_data["role"], request=request
        )
        return Response(self.get_serializer(membership).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, membership_id):
        services.remove_member(membership=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(request=InviteCreateSerializer, responses={201: InviteSerializer})
)
class InviteListCreateView(LabScopedViewMixin, generics.ListCreateAPIView):
    model = Invite
    serializer_class = InviteSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_MEMBERS, "POST": Perm.MANAGE_MEMBERS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invites"

    def get_throttles(self):  # creation only; listing is not rate limited
        return super().get_throttles() if self.request.method == "POST" else []

    def get_queryset(self):
        qs = super().get_queryset().filter(accepted_at__isnull=True, revoked_at__isnull=True)
        return qs.select_related("invited_by").order_by("-created_at")

    def create(self, request, *args, **kwargs):
        ser = InviteCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        invite = services.create_invite(
            lab=request.lab, by=request.user, request=request, **ser.validated_data
        )
        return Response(InviteSerializer(invite).data, status=status.HTTP_201_CREATED)


class InviteDetailView(LabScopedViewMixin, generics.GenericAPIView):
    model = Invite
    serializer_class = InviteSerializer
    lookup_url_kwarg = "invite_id"
    perms = {"PATCH": Perm.MANAGE_MEMBERS, "DELETE": Perm.MANAGE_MEMBERS}

    def get_queryset(self):
        qs = super().get_queryset().filter(accepted_at__isnull=True, revoked_at__isnull=True)
        if self.request.method == "PATCH":  # an expired invite can still be revoked, not edited
            qs = qs.filter(expires_at__gt=timezone.now())
        return qs

    @extend_schema(request=RoleSerializer, responses=InviteSerializer)
    def patch(self, request, lab_id, invite_id):
        ser = RoleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        invite = services.change_invite_role(
            invite=self.get_object(),
            by=request.user,
            role=ser.validated_data["role"],
            request=request,
        )
        return Response(self.get_serializer(invite).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, invite_id):
        services.revoke_invite(invite=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitePreviewView(generics.GenericAPIView):
    serializer_class = TokenSerializer
    perms = {"POST": Perm.PUBLIC}

    @extend_schema(responses=InvitePreviewSerializer)
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        invite = services.usable_invite_for_token(ser.validated_data["token"])
        return Response({"lab_name": invite.lab.name, "role": invite.role, "email": invite.email})


class InviteAcceptView(generics.GenericAPIView):
    serializer_class = TokenSerializer
    perms = {"POST": Perm.AUTHENTICATED}

    @extend_schema(responses=LabSerializer)
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        lab = services.accept_invite(
            user=request.user, token=ser.validated_data["token"], request=request
        )
        return Response(LabSerializer(lab, context=self.get_serializer_context()).data)
