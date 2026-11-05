from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.models import Notification
from core.notifications import visible_notifications
from core.permissions import Perm, get_lab_or_404
from core.search import MAX_Q, SPECS, search
from core.serializers import NotificationSerializer, UserSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"status": "ok"})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch", "head", "options"]
    perms = {"GET": Perm.AUTHENTICATED, "PATCH": Perm.AUTHENTICATED}

    def get_object(self):
        return self.request.user


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
