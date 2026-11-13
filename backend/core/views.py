from django.core.files.storage import storages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.exceptions import NotAuthenticated
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core import avatars
from core.auth import login_methods_for_email, sso_for_email
from core.models import Notification, User
from core.notifications import visible_notifications
from core.permissions import Perm, get_lab_or_404, shares_a_lab
from core.search import MAX_Q, SPECS, search
from core.serializers import MeSerializer, NotificationSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"status": "ok"})


class LoginMethodsView(APIView):
    """Email-first sign-in (D156): which ways in this address has. Answers by domain only, so it
    says nothing about whether an account exists. POST keeps the address out of URLs and logs."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login_methods"

    @extend_schema(
        request=inline_serializer("LoginMethodsRequest", {"email": serializers.EmailField()}),
        responses=inline_serializer(
            "LoginMethods",
            {
                "methods": serializers.ListField(child=serializers.CharField()),
                "institution": serializers.CharField(allow_null=True),
            },
        ),
    )
    def post(self, request):
        email = serializers.EmailField().run_validation(request.data.get("email"))
        cfg = sso_for_email(email)
        return Response(
            {
                "methods": login_methods_for_email(email),
                "institution": cfg.institution.name if cfg else None,
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]
    perms = {"GET": Perm.AUTHENTICATED, "PATCH": Perm.AUTHENTICATED}

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        # Lock the row and re-read it, so two saves at once (the zone sync and the recent-items
        # tracker on first load) merge their preferences instead of one wiping the other.
        with transaction.atomic():
            User.objects.select_for_update().filter(pk=request.user.pk).first()
            request.user.refresh_from_db()
            return super().update(request, *args, **kwargs)


class MyAvatarView(APIView):
    """PUT replaces your profile picture, DELETE removes it (D258)."""

    parser_classes = [MultiPartParser]
    perms = {"PUT": Perm.AUTHENTICATED, "DELETE": Perm.AUTHENTICATED}

    @extend_schema(
        request={
            "multipart/form-data": inline_serializer(
                "AvatarUpload", {"file": serializers.FileField()}
            )
        },
        responses=MeSerializer,
    )
    def put(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": "Choose a picture to upload."})
        avatars.replace(request.user, upload)
        return Response(MeSerializer(request.user).data)

    @extend_schema(responses={204: None})
    def delete(self, request):
        avatars.remove(request.user)
        return Response(status=204)


class UserAvatarView(APIView):
    """The picture of yourself or of someone you share a lab with; anyone else gets 404, as does
    a person with no picture. Streamed here so the type and `nosniff` are ours (D258)."""

    perms = {"GET": Perm.AUTHENTICATED}

    @extend_schema(responses={(200, "image/*"): OpenApiTypes.BINARY})
    def get(self, request, user_id):
        person = get_object_or_404(User, pk=user_id)
        if not person.avatar or not shares_a_lab(request.user, person):
            raise Http404
        try:
            handle = storages["lab_files"].open(person.avatar, "rb")
        except FileNotFoundError as exc:
            raise Http404 from exc
        response = FileResponse(handle, content_type=avatars.content_type(person.avatar))
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        response["Cache-Control"] = "private, max-age=300"  # the ?v= in the URL busts it
        return response


class LabScopedViewMixin:
    """ARCHITECTURE section 2: anonymous gets 401, then the lab is resolved (404 if the user
    is not a member) before permissions run. Item lookups go through `get_queryset()`."""

    model = None  # lab-scoped model served by this view

    def initial(self, request, *args, **kwargs):
        self.perform_authentication(request)
        if not request.user.is_authenticated:
            raise NotAuthenticated()
        request.lab = get_lab_or_404(request.user, kwargs["lab_id"])
        super().initial(request, *args, **kwargs)

    def get_queryset(self):
        return self.model.objects.visible_to(self.request.user, self.request.lab)


# ---------------------------------------------------------------- notifications (D30)


class NotificationMixin(LabScopedViewMixin):
    """Lab-scoped like everything else; additionally limited to the requester's own rows, so
    another user's notification is a 404."""

    model = Notification
    serializer_class = NotificationSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().filter(recipient=self.request.user)


class NotificationListView(NotificationMixin, generics.ListAPIView):
    perms = {"GET": Perm.VIEW_LAB}

    def get_queryset(self):
        qs = super().get_queryset().order_by("-created_at", "id")
        if self.request.query_params.get("unread") == "true":
            qs = qs.filter(read_at__isnull=True)
        return visible_notifications(self.request.user, self.request.lab, qs)


class NotificationReadView(NotificationMixin, generics.GenericAPIView):
    lookup_url_kwarg = "notification_id"
    perms = {"POST": Perm.VIEW_LAB}

    @extend_schema(request=None, responses=NotificationSerializer)
    def post(self, request, lab_id, notification_id):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at", "updated_at"])
        return Response(self.get_serializer(notification).data)


class NotificationReadAllView(NotificationMixin, generics.GenericAPIView):
    perms = {"POST": Perm.VIEW_LAB}

    @extend_schema(
        request=None,
        responses=inline_serializer("ReadAllResult", {"updated": serializers.IntegerField()}),
    )
    def post(self, request, lab_id):
        updated = (
            self.get_queryset()
            .filter(read_at__isnull=True)
            .update(read_at=timezone.now(), updated_at=timezone.now())
        )
        return Response({"updated": updated})


# ---------------------------------------------------------------- search (D93)


class SearchProjectSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class SearchHitSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.UUIDField()
    title = serializers.CharField()
    snippet = serializers.CharField()
    project = SearchProjectSerializer(allow_null=True)
    url = serializers.CharField()


class SearchView(LabScopedViewMixin, APIView):
    """Reading, like browsing: not audited (D93)."""

    perms = {"GET": Perm.VIEW_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "search"

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description=f"At least 2 characters, at most {MAX_Q}."),
            OpenApiParameter(
                "types", str, description="Comma-separated: " + ", ".join(s.type for s in SPECS)
            ),
        ],
        responses=inline_serializer("SearchResults", {"results": SearchHitSerializer(many=True)}),
    )
    def get(self, request, lab_id):
        types = {t for t in request.query_params.get("types", "").split(",") if t}
        hits = search(request.user, request.lab, request.query_params.get("q", ""), types)
        return Response({"results": hits})
