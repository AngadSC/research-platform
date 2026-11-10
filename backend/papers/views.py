"""The lab's paper library, all under /api/labs/<lab_id>/. Every member reads; `contribute_lab` adds
and edits. A paper's PDF is served only through its paper (D175): `Attachment.visible_to` filters
by project, so the project file routes 404 on it, and this route only ever finds its own file."""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm
from core.search import MAX_Q, match
from core.views import LabScopedViewMixin
from documents.serializers import AttachmentSerializer, AttachmentUploadSerializer
from documents.views import download_response
from integrations.http import IntegrationError
from integrations.serializers import ImportResultSerializer
from papers import citation, crossref, services
from papers.models import Paper, PaperNote
from papers.serializers import (
    NoteInputSerializer,
    PaperCitationSerializer,
    PaperDetailSerializer,
    PaperDoiLookupSerializer,
    PaperInputSerializer,
    PaperNoteSerializer,
    PaperSerializer,
    ZoteroImportSerializer,
    ZoteroItemSerializer,
)

LIST_LIMIT = 200
ZOTERO_DOWN = "Zotero could not be reached. Try again shortly."
SEARCH_FIELDS = ("title", "authors", "venue", "doi", "abstract")


class ProviderUnavailable(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "provider_error"
    default_detail = "Crossref could not be reached. Try again, or fill the fields in yourself."


class PaperMixin(LabScopedViewMixin):
    model = Paper
    lookup_url_kwarg = "paper_id"

    def get_queryset(self):
        return services.with_counts(super().get_queryset())


class PaperListCreateView(PaperMixin, generics.GenericAPIView):
    serializer_class = PaperSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="Words to look for.")],
        responses=PaperSerializer(many=True),
    )
    def get(self, request, lab_id):
        qs = self.get_queryset().select_related("added_by")
        q = request.query_params.get("q", "").strip()[:MAX_Q]
        if q:
            qs = match(qs, SEARCH_FIELDS, q)
        # ponytail: newest 200 with search narrowing them; add paging if a library outgrows that
        return Response(
            self.get_serializer(qs.order_by("-created_at", "pk")[:LIST_LIMIT], many=True).data
        )

    @extend_schema(request=PaperInputSerializer, responses={201: PaperDetailSerializer})
    def post(self, request, lab_id):
        ser = PaperInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        paper = services.create_paper(request.lab, user=request.user, data=ser.validated_data)
        return Response(PaperDetailSerializer(paper).data, status=status.HTTP_201_CREATED)


class PaperDetailView(PaperMixin, generics.GenericAPIView):
    serializer_class = PaperDetailSerializer
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.CONTRIBUTE_LAB, "DELETE": Perm.CONTRIBUTE_LAB}

    def get_queryset(self):
        return super().get_queryset().select_related("added_by")

    @extend_schema(responses=PaperDetailSerializer)
    def get(self, request, lab_id, paper_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=PaperInputSerializer, responses=PaperDetailSerializer)
    def patch(self, request, lab_id, paper_id):
        paper = self.get_object()
        ser = PaperInputSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        paper = services.update_paper(paper, data=ser.validated_data)
        return Response(self.get_serializer(paper).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, paper_id):
        services.delete_paper(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PaperPdfView(PaperMixin, generics.GenericAPIView):
    """One live PDF per paper: GET streams it (audited), POST replaces it."""

    parser_classes = [MultiPartParser, FormParser]
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CONTRIBUTE_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, lab_id, paper_id):
        attachment = services.live_pdf(self.get_object())
        if attachment is None:
            raise Http404
        return download_response(request, attachment)

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, paper_id):
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attachment = services.upload_pdf(
            self.get_object(), user=request.user, file=ser.validated_data["file"], request=request
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class PaperCitationView(PaperMixin, generics.GenericAPIView):
    """All four styles at once: the UI switches between them without another request."""

    serializer_class = PaperCitationSerializer
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=PaperCitationSerializer)
    def get(self, request, lab_id, paper_id):
        paper = self.get_object()
        return Response({style: citation.cite(paper, style) for style in citation.STYLES})


class DoiLookupView(LabScopedViewMixin, generics.GenericAPIView):
    """Autofill for the add-paper form. Unknown or malformed DOI: `found: false`."""

    serializer_class = PaperDoiLookupSerializer
    perms = {"GET": Perm.CONTRIBUTE_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_search"

    @extend_schema(
        parameters=[OpenApiParameter("doi", str)],
        responses=PaperDoiLookupSerializer,
    )
    def get(self, request, lab_id):
        try:
            meta = crossref.lookup(request.query_params.get("doi", ""))
        except IntegrationError:
            raise ProviderUnavailable from None
        return Response({"found": True, **meta} if meta else {"found": False})


class ZoteroImportView(LabScopedViewMixin, generics.GenericAPIView):
    """D242: GET lists items from your own Zotero account, POST copies the chosen ones in. Your
    key stays yours: nothing here uses or shows anyone else's. No account: 404."""

    serializer_class = ZoteroItemSerializer
    pagination_class = None
    perms = {"GET": Perm.CONTRIBUTE_LAB, "POST": Perm.CONTRIBUTE_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_search"

    @extend_schema(
        parameters=[OpenApiParameter("q", str, description="Words to look for.")],
        responses=ZoteroItemSerializer(many=True),
    )
    def get(self, request, lab_id):
        q = request.query_params.get("q", "").strip()[:MAX_Q]
        try:
            items = services.zotero_items(request.lab, user=request.user, query=q)
        except IntegrationError:
            raise ProviderUnavailable(ZOTERO_DOWN) from None
        return Response(self.get_serializer(items, many=True).data)

    @extend_schema(request=ZoteroImportSerializer, responses=ImportResultSerializer)
    def post(self, request, lab_id):
        body = ZoteroImportSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = services.import_from_zotero(
                request.lab, user=request.user, ids=body.validated_data["ids"], request=request
            )
        except IntegrationError:
            raise ProviderUnavailable(ZOTERO_DOWN) from None
        return Response(result)


class PaperNoteCreateView(PaperMixin, generics.GenericAPIView):
    serializer_class = PaperNoteSerializer
    perms = {"POST": Perm.CONTRIBUTE_LAB}

    @extend_schema(request=NoteInputSerializer, responses={201: PaperNoteSerializer})
    def post(self, request, lab_id, paper_id):
        ser = NoteInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = services.add_note(
            self.get_object(), author=request.user, body=ser.validated_data["body"]
        )
        return Response(self.get_serializer(note).data, status=status.HTTP_201_CREATED)


class PaperNoteDetailView(LabScopedViewMixin, generics.GenericAPIView):
    """PATCH: the author only. DELETE: the author, or a PI or lab admin (checked in the service)."""

    model = PaperNote
    serializer_class = PaperNoteSerializer
    lookup_url_kwarg = "papernote_id"
    perms = {"PATCH": Perm.CONTRIBUTE_LAB, "DELETE": Perm.CONTRIBUTE_LAB}

    def get_queryset(self):
        return super().get_queryset().select_related("author")

    @extend_schema(request=NoteInputSerializer, responses=PaperNoteSerializer)
    def patch(self, request, lab_id, papernote_id):
        note = self.get_object()
        ser = NoteInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = services.edit_note(note, user=request.user, body=ser.validated_data["body"])
        return Response(self.get_serializer(note).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, papernote_id):
        services.delete_note(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
