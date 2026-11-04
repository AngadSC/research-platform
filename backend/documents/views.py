from django.core.files.storage import storages
from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, visible_projects
from core.tenancy import project_of
from core.views import LabScopedViewMixin
from documents import services
from documents.models import Attachment, Document, DocumentRevision
from documents.serializers import (
    AttachmentSerializer,
    AttachmentUploadSerializer,
    ConflictSerializer,
    DocumentCreateSerializer,
    DocumentListSerializer,
    DocumentSaveSerializer,
    DocumentSerializer,
    RevisionListSerializer,
    RevisionSerializer,
)


class ProjectPermMixin(LabScopedViewMixin):
    """HasPerm reads `view.project`. Collection routes take the project from the URL (404 if
    not visible); item routes take it from the visible object the URL names, so an invisible
    object is a 404 before any 403 (D21)."""

    def get_permission_owner(self):
        projects = visible_projects(self.request.user, self.request.lab)
        return get_object_or_404(projects, pk=self.kwargs["project_id"])

    def check_permissions(self, request):
        self.project = project_of(self.get_permission_owner())
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(project=self.project) if "project_id" in self.kwargs else qs


class DocumentMixin(ProjectPermMixin):
    """Routes under `documents/<document_id>/`, and the project's document collection."""

    model = Document

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def get_document(self):
        if not hasattr(self, "_document"):
            self._document = get_object_or_404(
                Document.objects.visible_to(self.request.user, self.request.lab).filter(
                    deleted_at__isnull=True
                ),
                pk=self.kwargs["document_id"],
            )
        return self._document

    def get_permission_owner(self):
        if "document_id" in self.kwargs:
            return self.get_document()
        return super().get_permission_owner()


class DocumentListCreateView(DocumentMixin, generics.GenericAPIView):
    serializer_class = DocumentListSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=DocumentListSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().select_related("updated_by").order_by("-updated_at")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=DocumentCreateSerializer, responses={201: DocumentSerializer})
    def post(self, request, lab_id, project_id):
        ser = DocumentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc = services.create_document(
            project=self.project, user=request.user, **ser.validated_data
        )
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(DocumentMixin, generics.GenericAPIView):
    serializer_class = DocumentSerializer
    lookup_url_kwarg = "document_id"
    perms = {"GET": Perm.VIEW_PROJECT, "PUT": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(responses=DocumentSerializer)
    def get(self, request, lab_id, document_id):
        doc = self.get_object()
        record(
            AuditAction.DOCUMENT_VIEWED,
            actor=request.user,
            lab=request.lab,
            target=doc,
            request=request,
        )
        return Response(self.get_serializer(doc).data)

    @extend_schema(
        request=DocumentSaveSerializer,
        responses={200: DocumentSerializer, 409: ConflictSerializer},
    )
    def put(self, request, lab_id, document_id):
        doc = self.get_object()
        ser = DocumentSaveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc = services.save_document(doc, user=request.user, **ser.validated_data)
        return Response(self.get_serializer(doc).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, document_id):
        services.delete_document(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevisionMixin(DocumentMixin):
    model = DocumentRevision
    lookup_url_kwarg = "version"
    lookup_field = "version"

    def get_queryset(self):
        # Revisions have no `deleted_at`; a deleted document is a 404 via get_document().
        qs = ProjectPermMixin.get_queryset(self)
        return qs.filter(document=self.get_document()).select_related("created_by", "restored_from")


class RevisionListView(RevisionMixin, generics.ListAPIView):
    serializer_class = RevisionListSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_PROJECT}

    def get_queryset(self):
        return super().get_queryset().order_by("-version")


class RevisionDetailView(RevisionMixin, generics.RetrieveAPIView):
    serializer_class = RevisionSerializer
    perms = {"GET": Perm.VIEW_PROJECT}

    def retrieve(self, request, *args, **kwargs):
        revision = self.get_object()
        record(
            AuditAction.DOCUMENT_VIEWED,
            actor=request.user,
            lab=request.lab,
            target=revision.document,
            request=request,
            metadata={"version": revision.version},
        )
        return Response(self.get_serializer(revision).data)


class RevisionRestoreView(RevisionMixin, generics.GenericAPIView):
    serializer_class = DocumentSerializer
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=None, responses=DocumentSerializer)
    def post(self, request, lab_id, document_id, version):
        doc = services.restore_revision(self.get_object(), user=request.user, request=request)
        return Response(self.get_serializer(doc).data)


# ---------------------------------------------------------------- attachments


class AttachmentMixin(ProjectPermMixin):
    model = Attachment

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

    def get_permission_owner(self):
        if "attachment_id" in self.kwargs:
            return get_object_or_404(self.get_queryset(), pk=self.kwargs["attachment_id"])
        return super().get_permission_owner()


class AttachmentListCreateView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = AttachmentSerializer
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser]
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    def get_throttles(self):  # uploads only; listing is not rate limited
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses=AttachmentSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().select_related("uploaded_by").order_by("-created_at")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, project_id):
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attachment = services.upload_attachment(
            project=self.project,
            user=request.user,
            file=ser.validated_data["file"],
            request=request,
        )
        return Response(self.get_serializer(attachment).data, status=status.HTTP_201_CREATED)


class AttachmentDetailView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = AttachmentSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"GET": Perm.VIEW_PROJECT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(responses=AttachmentSerializer)
    def get(self, request, lab_id, attachment_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, attachment_id):
        services.delete_attachment(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttachmentDownloadView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = AttachmentSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, lab_id, attachment_id):
        """ARCHITECTURE section 8: scoped lookup, permission, audit, then stream."""
        attachment = self.get_object()
        record(
            AuditAction.ATTACHMENT_DOWNLOADED,
            actor=request.user,
            lab=request.lab,
            target=attachment,
            request=request,
        )
        try:
            handle = storages["lab_files"].open(attachment.storage_key, "rb")
        except FileNotFoundError as exc:
            raise Http404 from exc
        response = FileResponse(
            handle,
            as_attachment=attachment.content_type != "application/pdf",  # PDFs: inline for PDF.js
            filename=attachment.original_filename,
            content_type=attachment.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        response["Cache-Control"] = "private, no-store"
        return response
