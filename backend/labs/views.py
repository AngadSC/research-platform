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

from core.permissions import Perm, labs_for
from core.views import LabScopedViewMixin
from integrations.http import IntegrationError
from labs import admin_services, ror, services
from labs.admin_serializers import LabDetailsInputSerializer
from labs.models import Invite, LabChatMessage, LabMembership
from labs.serializers import (
    InviteCreateSerializer,
    InvitePreviewSerializer,
    InviteSerializer,
    LabSerializer,
    MembershipSerializer,
    RoleSerializer,
    TokenSerializer,
)
from projects.serializers import (
    ChatMessageFilterSerializer,
    ChatMessageInputSerializer,
    ChatMessageSerializer,
    ChatReadInputSerializer,
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
    """The project chat's API (D206, D207) for the whole lab. Same message shape, so the same
    serializers: they only read `id`, `author`, `body` and `created_at`."""

    model = LabChatMessage
    serializer_class = ChatMessageSerializer
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
        parameters=[ChatMessageFilterSerializer], responses=ChatMessageSerializer(many=True)
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

    @extend_schema(request=ChatMessageInputSerializer, responses={201: ChatMessageSerializer})
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
        return super().get_queryset().filter(accepted_at__isnull=True, revoked_at__isnull=True)

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
