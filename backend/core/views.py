from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import Perm, get_lab_or_404
from core.serializers import UserSerializer


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
