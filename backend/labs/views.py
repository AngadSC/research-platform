from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from core.permissions import Perm, labs_for
from core.views import LabScopedViewMixin
from labs import services
from labs.models import Invite, LabMembership
from labs.serializers import (
    InviteCreateSerializer,
    InvitePreviewSerializer,
    InviteSerializer,
    LabSerializer,
    MembershipSerializer,
    RoleSerializer,
    TokenSerializer,
)


class LabListCreateView(generics.GenericAPIView):
    serializer_class = LabSerializer
    perms = {"GET": Perm.AUTHENTICATED, "POST": Perm.AUTHENTICATED}

    @extend_schema(responses=LabSerializer(many=True))
    def get(self, request):
        return Response(self.get_serializer(labs_for(request.user), many=True).data)

    @extend_schema(responses={201: LabSerializer})
    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        name = ser.validated_data["name"]
        lab = services.create_lab(user=request.user, name=name, request=request)
        return Response(self.get_serializer(lab).data, status=status.HTTP_201_CREATED)


class LabDetailView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = LabSerializer
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_LAB}

    def get(self, request, lab_id):
        return Response(self.get_serializer(request.lab).data)

    def patch(self, request, lab_id):
        ser = self.get_serializer(request.lab, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        name = ser.validated_data.get("name", request.lab.name)
        lab = services.update_lab(lab=request.lab, user=request.user, name=name, request=request)
        return Response(self.get_serializer(lab).data)


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
    perms = {"DELETE": Perm.MANAGE_MEMBERS}

    def get_queryset(self):
        return super().get_queryset().filter(accepted_at__isnull=True, revoked_at__isnull=True)

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
