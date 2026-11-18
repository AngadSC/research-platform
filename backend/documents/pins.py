"""Pin for everyone: the lab's "Start here" list on Home. Lab documents are pinned by people who
manage the lab, project documents by the project's lead (`edit_project`, which a lab document
maps to `manage_lab`). Anyone who can see the document sees the pin."""

from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can
from core.views import LabScopedViewMixin
from documents.models import Document, PinnedDocument
from documents.views import DocumentMixin


class PinSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="document_id")
    title = serializers.CharField(source="document.title")
    project = serializers.UUIDField(source="document.project_id", allow_null=True)
    project_name = serializers.SerializerMethodField()
    embed_url = serializers.CharField(source="document.embed_url")
    can_manage = serializers.SerializerMethodField()

    def get_project_name(self, pin) -> str:
        return pin.document.project.name if pin.document.project_id else ""

    def get_can_manage(self, pin) -> bool:
        return can(self.context["request"].user, Perm.EDIT_PROJECT, pin.document)


def visible_pins(user, lab):
    """Pins on documents this person can see (lab documents, or a project they are in)."""
    from documents import services

    docs = (Document.objects.visible_to(user, lab) | services.lab_documents(lab)).filter(
        deleted_at__isnull=True
    )
    return (
        PinnedDocument.objects.for_lab(lab)
        .filter(document__in=docs)
        .select_related("document", "document__project")
        .order_by(F("document__project_id").asc(nulls_first=True), "order", "created_at", "id")
    )


class StartHereView(LabScopedViewMixin, generics.GenericAPIView):
    model = PinnedDocument
    serializer_class = PinSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=PinSerializer(many=True))
    def get(self, request, lab_id):
        # lab documents first (nulls sort first), then each project's, in their own order
        return Response(
            self.get_serializer(visible_pins(request.user, request.lab), many=True).data
        )


def _scope(doc):
    return PinnedDocument.objects.for_lab(doc.lab_id).filter(document__project_id=doc.project_id)


@transaction.atomic
def pin(doc, *, user, request=None):
    scope = _scope(doc)
    if scope.filter(document=doc).exists():
        return
    last = scope.order_by("-order").values_list("order", flat=True).first()
    PinnedDocument.objects.create(
        lab=doc.lab, document=doc, pinned_by=user, order=0 if last is None else last + 1
    )
    record(AuditAction.DOCUMENT_PINNED, actor=user, lab=doc.lab, target=doc, request=request)


@transaction.atomic
def unpin(doc, *, user, request=None):
    deleted, _ = PinnedDocument.objects.for_lab(doc.lab_id).filter(document=doc).delete()
    if deleted:
        record(AuditAction.DOCUMENT_UNPINNED, actor=user, lab=doc.lab, target=doc, request=request)


@transaction.atomic
def move(doc, direction):
    """Swap with the neighbour in the same scope (lab documents, or the same project)."""
    pins = list(_scope(doc).select_for_update().order_by("order", "created_at", "id"))
    i = next((n for n, p in enumerate(pins) if p.document_id == doc.pk), None)
    j = None if i is None else i + (-1 if direction == "up" else 1)
    if j is None or not 0 <= j < len(pins):
        return
    pins[i], pins[j] = pins[j], pins[i]
    for n, p in enumerate(pins):
        if p.order != n:
            p.order = n
            p.save(update_fields=["order", "updated_at"])


class MoveSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=["up", "down"])


class DocumentPinView(DocumentMixin, generics.GenericAPIView):
    """Visible to anyone who can see the document (404 if not), then edit_project: the project's
    lead, or manage_lab for a lab document (403 for everyone else)."""

    serializer_class = MoveSerializer
    lookup_url_kwarg = "document_id"
    perms = {"POST": Perm.EDIT_PROJECT, "PATCH": Perm.EDIT_PROJECT, "DELETE": Perm.EDIT_PROJECT}

    @extend_schema(request=None, responses={204: None})
    def post(self, request, lab_id, document_id):
        pin(self.get_document(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=MoveSerializer, responses={204: None})
    def patch(self, request, lab_id, document_id):
        ser = MoveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        move(self.get_document(), ser.validated_data["direction"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, document_id):
        unpin(self.get_document(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
