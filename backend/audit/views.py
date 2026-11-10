from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.pagination import CursorPagination

from audit.models import AuditAction, AuditEvent
from audit.serializers import AuditEventSerializer, AuditFilterSerializer
from audit.services import record
from core.permissions import Perm, can_access_funding
from core.views import LabScopedViewMixin


class AuditCursorPagination(CursorPagination):
    ordering = ("-occurred_at", "-id")  # newest first
    page_size = 50


@extend_schema_view(  # on `get`: spectacular ignores `list` for generic views
    get=extend_schema(
        parameters=[
            AuditFilterSerializer,
            OpenApiParameter("cursor", str, description="Pagination cursor"),
        ]
    )
)
class AuditEventListView(LabScopedViewMixin, generics.ListAPIView):
    """Read-only. AuditEvent is not lab-scoped (D23), so the lab filter is explicit here."""

    serializer_class = AuditEventSerializer
    pagination_class = AuditCursorPagination
    perms = {"GET": Perm.VIEW_AUDIT_LOG}

    def get_queryset(self):
        f = AuditFilterSerializer(data=self.request.query_params)
        f.is_valid(raise_exception=True)
        q = f.validated_data
        qs = AuditEvent.objects.filter(lab=self.request.lab).select_related("actor")
        if not can_access_funding(self.request.user, self.request.lab):  # D226: names the funder
            qs = qs.exclude(action__startswith="funding.")
        for key in ("action", "target_type", "target_id"):
            if key in q:
                qs = qs.filter(**{key: q[key]})
        if "actor" in q:
            qs = qs.filter(actor_id=q["actor"])
        if "date_from" in q:
            qs = qs.filter(occurred_at__date__gte=q["date_from"])
        if "date_to" in q:
            qs = qs.filter(occurred_at__date__lte=q["date_to"])
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        record(AuditAction.AUDIT_LOG_VIEWED, actor=request.user, lab=request.lab, request=request)
        return response
