from django.conf import settings
from django.core.files.storage import storages
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.utils.http import content_disposition_header
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from assistant.privacy import ai_visible, set_flag
from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can_view_ethics_files, require, visible_projects
from core.tenancy import project_of
from core.views import LabScopedViewMixin
from documents import services
from documents.models import Attachment, Document, DocumentRevision, Folder
from documents.serializers import (
    AttachmentSerializer,
    AttachmentUploadSerializer,
    ConflictSerializer,
    DocumentCreateSerializer,
    DocumentListSerializer,
    DocumentOwnerSerializer,
    DocumentSaveSerializer,
    DocumentSerializer,
    FolderCreateSerializer,
    FolderSerializer,
    FolderUpdateSerializer,
    ItemMoveSerializer,
    ParticipantFlagSerializer,
    RevisionListSerializer,
    RevisionSerializer,
)
from ethics.models import EthicsApproval


class ProjectPermMixin(LabScopedViewMixin):
    """HasPerm reads `view.project`. Collection routes take the project from the URL (404 if
    not visible); item routes take it from the visible object the URL names, so an invisible
    object is a 404 before any 403 (D21)."""

    def get_permission_owner(self):
        projects = visible_projects(self.request.user, self.request.lab)
        return get_object_or_404(projects, pk=self.kwargs["project_id"])

    def check_permissions(self, request):
        owner = self.get_permission_owner()
        self.project = project_of(owner) or owner  # a lab-wide document is its own target (D233)
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(project=self.project) if "project_id" in self.kwargs else qs

    def resolve_folder(self, folder_id):
        """A folder of this view's project, or None. Any other id is the same 400 (no leak)."""
        if folder_id is None:
            return None
        folder = (
            Folder.objects.visible_to(self.request.user, self.request.lab)
            .filter(pk=folder_id, project=self.project)
            .first()
        )
        if folder is None:
            raise ValidationError({"folder": "That folder does not exist in this project."})
        return folder


class DocumentMixin(ProjectPermMixin):
    """Routes under `documents/<document_id>/`, and the project's document collection."""

    model = Document
    allow_lab_wide = True  # D233: reached by document id, so the same routes serve both kinds

    def _documents(self):
        docs = Document.objects.visible_to(self.request.user, self.request.lab)
        if self.allow_lab_wide:
            docs = docs | services.lab_documents(self.request.lab)
        return docs.filter(deleted_at__isnull=True)

    def get_queryset(self):
        if "document_id" in self.kwargs:
            return self._documents()
        return super().get_queryset().filter(deleted_at__isnull=True)

    def get_document(self):
        if not hasattr(self, "_document"):
            self._document = get_object_or_404(self._documents(), pk=self.kwargs["document_id"])
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
        data = dict(ser.validated_data)
        folder = self.resolve_folder(data.pop("folder", None))
        doc = services.create_document(
            project=self.project, user=request.user, folder=folder, **data
        )
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class LabDocumentListCreateView(LabScopedViewMixin, generics.GenericAPIView):
    """D233: lab-wide documents. Everything after creation uses the document routes below."""

    model = Document
    serializer_class = DocumentListSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(responses=DocumentListSerializer(many=True))
    def get(self, request, lab_id):
        qs = (
            services.lab_documents(request.lab)
            .filter(deleted_at__isnull=True)
            .select_related("updated_by")
            .order_by("title", "id")
        )
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=DocumentCreateSerializer, responses={201: DocumentSerializer})
    def post(self, request, lab_id):
        ser = DocumentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        data.pop("folder", None)  # folders belong to a project
        doc = services.create_document(lab=request.lab, user=request.user, **data)
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentDetailView(DocumentMixin, generics.GenericAPIView):
    serializer_class = DocumentSerializer
    lookup_url_kwarg = "document_id"
    perms = {
        "GET": Perm.VIEW_PROJECT,
        "PUT": Perm.EDIT_CONTENT,
        "PATCH": Perm.EDIT_CONTENT,
        "DELETE": Perm.EDIT_CONTENT,
    }

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
        doc = services.save_document(doc, user=request.user, request=request, **ser.validated_data)
        return Response(self.get_serializer(doc).data)

    @extend_schema(request=ParticipantFlagSerializer, responses=DocumentSerializer)
    def patch(self, request, lab_id, document_id):
        """Tick or clear "Contains participant data" (VISION A3). Saving content is PUT."""
        return Response(self.get_serializer(_set_flag(request, self.get_object())).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, document_id):
        doc = self.get_object()
        if doc.lab_wide:  # D233: anyone may fix a typo, but removing the lab manual is a lab call
            require(request.user, Perm.MANAGE_LAB, request.lab)
        services.delete_document(doc, user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentMoveView(DocumentMixin, generics.GenericAPIView):
    serializer_class = ItemMoveSerializer
    lookup_url_kwarg = "document_id"
    allow_lab_wide = False  # folders belong to a project
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=ItemMoveSerializer, responses={204: None})
    def post(self, request, lab_id, document_id):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.move_to_folder(
            self.get_object(), self.resolve_folder(ser.validated_data["folder"])
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentOwnerView(DocumentMixin, generics.GenericAPIView):
    """Give a document a new owner from the handover page. Same rule as the handover's other
    reassignments (D251): manage_project_members on its project, so its leads, PIs and lab
    admins. Lab-wide documents are not in any handover, so they are a 404 here."""

    serializer_class = DocumentOwnerSerializer
    lookup_url_kwarg = "document_id"
    allow_lab_wide = False
    perms = {"POST": Perm.MANAGE_PROJECT_MEMBERS}

    @extend_schema(request=DocumentOwnerSerializer, responses={204: None})
    def post(self, request, lab_id, document_id):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.change_owner(
            self.get_object(),
            user=request.user,
            owner_id=ser.validated_data["owner"],
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class RevisionMixin(DocumentMixin):
    model = DocumentRevision
    lookup_url_kwarg = "version"
    lookup_field = "version"

    def get_queryset(self):
        # Revisions have no `deleted_at`; a deleted document is a 404 via get_document().
        return self.get_document().revisions.select_related("created_by", "restored_from")


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

    @extend_schema(
        responses=AttachmentSerializer(many=True),
        parameters=[
            OpenApiParameter(
                "unflagged",
                bool,
                description="Leave out files that identify participants (the analysis code "
                "picker: Claude may run an analysis's code, VISION C1).",
            )
        ],
    )
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().select_related("uploaded_by").order_by("-created_at")
        if request.query_params.get("unflagged") in ("1", "true"):
            qs = ai_visible(qs)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, project_id):
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pi_only = ser.validated_data["pi_only"]
        if pi_only:  # D244: a grant letter, private from the moment it arrives
            require(request.user, Perm.ACCESS_FUNDING, self.project)
        attachment = services.upload_attachment(
            project=self.project,
            user=request.user,
            file=ser.validated_data.get("file"),
            drive_file_id=ser.validated_data.get("drive_file_id"),
            folder=self.resolve_folder(ser.validated_data.get("folder")),
            request=request,
            pi_only=pi_only,
            contains_participant_data=ser.validated_data["contains_participant_data"],
        )
        return Response(self.get_serializer(attachment).data, status=status.HTTP_201_CREATED)


class AttachmentDetailView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = AttachmentSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(responses=AttachmentSerializer)
    def get(self, request, lab_id, attachment_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=ParticipantFlagSerializer, responses=AttachmentSerializer)
    def patch(self, request, lab_id, attachment_id):
        """Tick or clear "Contains participant data" (VISION A3)."""
        return Response(self.get_serializer(_set_flag(request, self.get_object())).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, attachment_id):
        services.delete_attachment(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttachmentMoveView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = ItemMoveSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=ItemMoveSerializer, responses={204: None})
    def post(self, request, lab_id, attachment_id):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.move_to_folder(
            self.get_object(), self.resolve_folder(ser.validated_data["folder"])
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttachmentEditInGoogleView(AttachmentMixin, generics.GenericAPIView):
    """VISION B3: copy a Word, Excel or PowerPoint upload into the person's own Google Drive."""

    serializer_class = AttachmentSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"POST": Perm.EDIT_CONTENT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(request=None, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, attachment_id):
        copy = services.edit_in_google(self.get_object(), user=request.user, request=request)
        return Response(self.get_serializer(copy).data, status=status.HTTP_201_CREATED)


class AttachmentDownloadView(AttachmentMixin, generics.GenericAPIView):
    serializer_class = AttachmentSerializer
    lookup_url_kwarg = "attachment_id"
    perms = {"GET": Perm.VIEW_PROJECT}
    ethics_approval = None

    def check_permissions(self, request):
        """Ethics-owned files (D38) are checked through their approval (D48): view_ethics plus
        a visible linked project, or pi/lab_admin. Anything else is a project file."""
        approvals = EthicsApproval.objects.visible_to(request.user, request.lab).filter(
            deleted_at__isnull=True
        )
        self.ethics_approval = approvals.filter(
            attachments__pk=self.kwargs["attachment_id"], attachments__deleted_at__isnull=True
        ).first()
        if self.ethics_approval is None:
            return super().check_permissions(request)
        if not can_view_ethics_files(request.user, self.ethics_approval):
            raise PermissionDenied

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, lab_id, attachment_id):
        """ARCHITECTURE section 8: scoped lookup, permission, audit, then stream."""
        if self.ethics_approval is not None:
            attachment = get_object_or_404(
                self.ethics_approval.attachments.filter(deleted_at__isnull=True), pk=attachment_id
            )
        else:
            attachment = self.get_object()
        return download_response(request, attachment)


# ---------------------------------------------------------------- folders


class FolderMixin(ProjectPermMixin):
    model = Folder

    def get_permission_owner(self):
        if "folder_id" in self.kwargs:
            return get_object_or_404(self.get_queryset(), pk=self.kwargs["folder_id"])
        return super().get_permission_owner()


class FolderListCreateView(FolderMixin, generics.GenericAPIView):
    serializer_class = FolderSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=FolderSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset().order_by("name"), many=True).data)

    @extend_schema(request=FolderCreateSerializer, responses={201: FolderSerializer})
    def post(self, request, lab_id, project_id):
        ser = FolderCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        folder = services.create_folder(
            project=self.project,
            user=request.user,
            name=ser.validated_data["name"],
            parent=self.resolve_folder(ser.validated_data.get("parent")),
        )
        return Response(self.get_serializer(folder).data, status=status.HTTP_201_CREATED)


class FolderDetailView(FolderMixin, generics.GenericAPIView):
    serializer_class = FolderSerializer
    lookup_url_kwarg = "folder_id"
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(request=FolderUpdateSerializer, responses=FolderSerializer)
    def patch(self, request, lab_id, folder_id):
        ser = FolderUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        folder = self.get_object()
        if "name" in ser.validated_data:
            folder = services.rename_folder(folder, name=ser.validated_data["name"])
        if "contains_participant_data" in ser.validated_data:
            flag = ser.validated_data["contains_participant_data"]
            folder = set_flag(folder, flag, user=request.user, request=request)
        return Response(self.get_serializer(folder).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, folder_id):
        services.delete_folder(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


def _set_flag(request, obj):
    ser = ParticipantFlagSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    flag = ser.validated_data["contains_participant_data"]
    return set_flag(obj, flag, user=request.user, request=request)


def download_response(request, attachment):
    """Audit the download, then stream it (or presign it). Callers have checked access."""
    record(  # D244: a PI-only file's name stays out of the log lab admins read
        AuditAction.FUNDING_UPDATED if attachment.pi_only else AuditAction.ATTACHMENT_DOWNLOADED,
        actor=request.user,
        lab=request.lab,
        target=attachment,
        request=request,
    )
    if attachment.from_drive:  # D257: no bytes here; Drive decides who may open it
        return HttpResponseRedirect(attachment.external_url)
    inline = attachment.content_type == "application/pdf"  # shown by PDF.js
    # D123: only forced downloads are presigned. Anything shown inline streams through
    # Django, which is the only place `nosniff` and `CSP: sandbox` can be set.
    if settings.LAB_FILES_BUCKET and not settings.LAB_FILES_STREAM_DOWNLOADS and not inline:
        return _presigned_redirect(attachment)
    try:
        handle = storages["lab_files"].open(attachment.storage_key, "rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    response = FileResponse(
        handle,
        as_attachment=not inline,
        filename=attachment.original_filename,
        content_type=attachment.content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox"
    response["Cache-Control"] = "private, no-store"
    return response


def _presigned_redirect(attachment):
    """D90, D123: 302 to a presigned GET of a forced download (`attachment`, never inline).
    The filename goes through Django's RFC 6266/5987 encoder, so quotes, newlines and
    unicode are safe."""
    url = storages["lab_files"].url(
        attachment.storage_key,
        parameters={
            "ResponseContentDisposition": content_disposition_header(
                True, attachment.original_filename
            ),
            "ResponseContentType": attachment.content_type,
            "ResponseCacheControl": "private, no-store",
        },
        expire=min(settings.LAB_FILES_PRESIGN_SECONDS, 60),
    )
    response = HttpResponseRedirect(url)
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response
