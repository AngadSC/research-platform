import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm, can_view_ethics_files, visible_projects
from core.views import LabScopedViewMixin
from documents.serializers import AttachmentSerializer, AttachmentUploadSerializer
from ethics import services
from ethics.models import EthicsApproval
from ethics.serializers import EthicsApprovalInputSerializer, EthicsApprovalSerializer


class ApprovalMixin(LabScopedViewMixin):
    model = EthicsApproval
    serializer_class = EthicsApprovalSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(deleted_at__isnull=True)
            .select_related("created_by")
            .prefetch_related("projects", "attachments", "attachments__uploaded_by")
        )

    def body(self, *, partial=False):
        ser = EthicsApprovalInputSerializer(data=self.request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        return ser.validated_data

    def out(self, approval, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=approval.pk)  # re-read: prefetched links are stale
        return Response(self.get_serializer(fresh).data, status=code)


class ApprovalListCreateView(ApprovalMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_ETHICS, "POST": Perm.EDIT_ETHICS}

    def get_queryset(self):
        return super().get_queryset().order_by("expiry_date", "id")

    @extend_schema(
        parameters=[
            OpenApiParameter("project", OpenApiTypes.UUID, description="Only this project")
        ],
        responses=EthicsApprovalSerializer(many=True),
    )
    def get(self, request, lab_id):
        qs = self.get_queryset()
        project = request.query_params.get("project")
        if project:  # D134: the project's Ethics tab. Same visibility rules, just narrower.
            try:
                pk = uuid.UUID(project)
            except ValueError:
                pk = None
            # an invisible project reads as empty, so the filter can't probe for links
            if pk and visible_projects(request.user, request.lab).filter(pk=pk).exists():
                qs = qs.filter(projects__pk=pk)
            else:
                qs = qs.none()
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=EthicsApprovalInputSerializer, responses={201: EthicsApprovalSerializer})
    def post(self, request, lab_id):
        approval = services.create_approval(
            lab=request.lab, user=request.user, data=self.body(), request=request
        )
        return self.out(approval, status.HTTP_201_CREATED)


class ApprovalDetailView(ApprovalMixin, generics.GenericAPIView):
    lookup_url_kwarg = "ethicsapproval_id"
    perms = {"GET": Perm.VIEW_ETHICS, "PATCH": Perm.EDIT_ETHICS, "DELETE": Perm.EDIT_ETHICS}

    @extend_schema(responses=EthicsApprovalSerializer)
    def get(self, request, lab_id, ethicsapproval_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=EthicsApprovalInputSerializer, responses=EthicsApprovalSerializer)
    def patch(self, request, lab_id, ethicsapproval_id):
        approval = services.update_approval(
            self.get_object(), user=request.user, data=self.body(partial=True), request=request
        )
        return self.out(approval)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, ethicsapproval_id):
        services.delete_approval(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApprovalAttachmentUploadView(ApprovalMixin, generics.GenericAPIView):
    """Same notice, size limit, throttle and 413 middleware as project uploads. Uploading is file
    access, so D48 applies on top of edit_ethics."""

    lookup_url_kwarg = "ethicsapproval_id"
    parser_classes = [MultiPartParser, FormParser]
    perms = {"POST": Perm.EDIT_ETHICS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, ethicsapproval_id):
        approval = self.get_object()
        if not can_view_ethics_files(request.user, approval):
            raise PermissionDenied
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attachment = services.upload_file(
            approval=approval,
            user=request.user,
            file=ser.validated_data.get("file"),
            drive_file_id=ser.validated_data.get("drive_file_id"),
            request=request,
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)
