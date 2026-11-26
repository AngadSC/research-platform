import datetime
import uuid
from types import SimpleNamespace

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status, views
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

from core.auth import recent_auth_required
from core.permissions import Perm, can, forget, get_lab_or_404, visible_projects
from core.tenancy import by_secret
from core.views import LabScopedViewMixin
from documents.views import ProjectPermMixin
from instrument_parsers import SOFTWARE_CHOICES
from instruments import services
from instruments.models import InstrumentDropLink, InstrumentFile, UploadedVia
from instruments.serializers import (
    DropLinkCreatedSerializer,
    DropLinkInputSerializer,
    DropLinkSerializer,
    DropUploadSerializer,
    InstrumentFileDetailSerializer,
    InstrumentFileSerializer,
    PublicDropResultSerializer,
    PublicDropSerializer,
    SoftwareChoiceSerializer,
)
from labs.models import InventoryCategory, InventoryItem, hash_token
from projects.activity import _request as activity_request
from projects.services import refuse_if_archived

LIST_LIMIT = 100


def _instrument(request, item_id) -> InventoryItem:
    """An equipment item of this lab; anything else is the same 404."""
    items = InventoryItem.objects.visible_to(request.user, request.lab).filter(
        category=InventoryCategory.EQUIPMENT
    )
    return get_object_or_404(items, pk=item_id)


class SoftwareChoicesView(views.APIView):
    """The instrument software the parsers know, for the equipment form."""

    perms = {"GET": Perm.AUTHENTICATED}

    @extend_schema(responses=SoftwareChoiceSerializer(many=True))
    def get(self, request):
        return Response([{"value": v, "label": label} for v, label in SOFTWARE_CHOICES])


class InstrumentFileListView(LabScopedViewMixin, generics.GenericAPIView):
    """The newest instrument files in projects the viewer can see."""

    model = InstrumentFile
    serializer_class = InstrumentFileSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}
    needs_inventory = True

    @extend_schema(
        parameters=[
            OpenApiParameter("instrument", str, description="Only this instrument's files."),
            OpenApiParameter("project", str, description="Only this project's files."),
        ],
        responses=InstrumentFileSerializer(many=True),
    )
    def get(self, request, lab_id):
        qs = self.get_queryset()
        for key in ("instrument", "project"):
            if value := request.query_params.get(key):
                try:
                    qs = qs.filter(**{f"{key}_id": uuid.UUID(value)})
                except ValueError:
                    return Response([])
        qs = qs.select_related("attachment", "instrument", "project", "dropped_by")
        return Response(
            self.get_serializer(qs.order_by("-created_at")[:LIST_LIMIT], many=True).data
        )


class InstrumentFileDetailView(LabScopedViewMixin, generics.GenericAPIView):
    """One file with its parsed summary; the page polls this while the status is pending."""

    model = InstrumentFile
    serializer_class = InstrumentFileDetailSerializer
    perms = {"GET": Perm.VIEW_PROJECT}
    needs_inventory = True

    def check_permissions(self, request):
        qs = self.get_queryset().select_related("attachment", "instrument", "project", "dropped_by")
        self.item = get_object_or_404(qs, pk=self.kwargs["instrumentfile_id"])
        self.project = self.item.project
        super().check_permissions(request)

    def get(self, request, lab_id, instrumentfile_id):
        return Response(self.get_serializer(self.item).data)


class DropFileView(ProjectPermMixin, generics.GenericAPIView):
    """The signed-in drop page (and the QR sticker): one file per request into a project."""

    model = InstrumentFile
    serializer_class = InstrumentFileSerializer
    parser_classes = [MultiPartParser, FormParser]
    perms = {"POST": Perm.EDIT_CONTENT}
    needs_inventory = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(request=DropUploadSerializer, responses={201: InstrumentFileSerializer})
    def post(self, request, lab_id, project_id, inventoryitem_id):
        instrument = _instrument(request, inventoryitem_id)
        refuse_if_archived(self.project)
        ser = DropUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        item = services.drop_file(
            instrument=instrument,
            project=self.project,
            user=request.user,
            file=ser.validated_data["file"],
            via=UploadedVia.PAGE,
            flag=ser.validated_data["contains_participant_data"],
            request=request,
        )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)


class DropLinkListCreateView(LabScopedViewMixin, generics.GenericAPIView):
    """Links into a project for this instrument: your own (PIs and lab admins see everyone's)."""

    model = InstrumentDropLink
    serializer_class = DropLinkSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}
    needs_inventory = True

    @extend_schema(responses=DropLinkSerializer(many=True))
    def get(self, request, lab_id, inventoryitem_id):
        instrument = _instrument(request, inventoryitem_id)
        qs = (
            self.get_queryset()
            .filter(instrument=instrument, revoked_at__isnull=True)
            .select_related("project", "created_by")
            .order_by("-created_at")
        )
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=DropLinkInputSerializer, responses={201: DropLinkCreatedSerializer})
    def post(self, request, lab_id, inventoryitem_id):
        instrument = _instrument(request, inventoryitem_id)
        ser = DropLinkInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        project = visible_projects(request.user, request.lab).filter(pk=data["project"]).first()
        if project is None:
            raise Http404
        if not can(request.user, Perm.EDIT_CONTENT, project):
            raise PermissionDenied("You can only make a link into a project you can add files to.")
        refuse_if_archived(project)
        stale = recent_auth_required(request)  # D194: a login-free way in is a secret
        if stale:
            return stale
        days = data.get("expires_in_days")
        link, token = services.issue_link(
            instrument=instrument,
            project=project,
            user=request.user,
            label=data.get("label", ""),
            expires_at=timezone.now() + datetime.timedelta(days=days) if days else None,
            request=request,
        )
        out = DropLinkCreatedSerializer(link, context={"token": token})
        return Response(out.data, status=status.HTTP_201_CREATED)


class DropLinkDetailView(LabScopedViewMixin, generics.GenericAPIView):
    model = InstrumentDropLink
    serializer_class = DropLinkSerializer
    perms = {"DELETE": Perm.VIEW_LAB}
    needs_inventory = True

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, instrumentdroplink_id):
        link = get_object_or_404(self.get_queryset(), pk=instrumentdroplink_id)
        services.revoke_link(link, by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- the public drop page


class Refused(APIException):
    def __init__(self, code, detail):
        self.status_code = code
        super().__init__(detail)


ASK = "Ask the person who gave it to you for a new one."


def _token(request) -> str:
    token = request.query_params.get("token")
    if not token and request.method == "POST":
        token = request.data.get("token")
    return str(token or "")


class DropLinkThrottle(SimpleRateThrottle):
    """Per link, whoever sends: a leaked link cannot be used to flood the project."""

    scope = "instrument_drop_link"

    def get_cache_key(self, request, view):
        if request.method != "POST":
            return None
        return self.cache_format % {"scope": self.scope, "ident": hash_token(_token(request))}


def _open(request):
    """(link, maker, lab, project) for a usable link, or Refused. The maker's access is read
    again on every use, so leaving the project or the lab ends the link at once."""
    token = _token(request)
    link = (
        by_secret(InstrumentDropLink)
        .filter(token_hash=hash_token(token))
        .select_related("instrument", "created_by")
        .first()
        if token
        else None
    )
    if link is None:
        raise Refused(401, "This link does not work. " + ASK)
    if link.revoked_at is not None:
        raise Refused(410, "This link was turned off. " + ASK)
    if link.expires_at is not None and link.expires_at <= timezone.now():
        raise Refused(410, "This link has expired. " + ASK)
    user = link.created_by
    forget(user)
    try:
        if not user.is_active:
            raise Http404
        lab = get_lab_or_404(user, link.lab_id)
    except Http404:
        raise Refused(404, "This link no longer works. " + ASK) from None
    project = visible_projects(user, lab).filter(pk=link.project_id).first()
    if project is None:
        raise Refused(404, "This link no longer works. " + ASK)
    if not lab.inventory_enabled:
        raise Refused(403, "Inventory is turned off for this lab.")
    if not can(user, Perm.EDIT_CONTENT, project):
        raise Refused(403, "The person who made this link can no longer add files here. " + ASK)
    return link, user, lab, project


class PublicDropView(views.APIView):
    """`/drop/<token>` in the app: shows the instrument and project names and takes files. It
    never lists or reads anything. The token is the only credential; a session does not count."""

    authentication_classes = []
    perms = {"GET": Perm.PUBLIC, "POST": Perm.PUBLIC}
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle, DropLinkThrottle]
    throttle_scope = "instrument_drop"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    @extend_schema(
        parameters=[OpenApiParameter("token", str, required=True)],
        responses=PublicDropSerializer,
    )
    def get(self, request):
        link, _, _, project = _open(request)
        data = {
            "instrument": link.instrument.name,
            "project": project.name,
            "max_bytes": settings.ATTACHMENT_MAX_BYTES,
        }
        return Response(PublicDropSerializer(data).data)

    @extend_schema(request=DropUploadSerializer, responses={201: PublicDropResultSerializer})
    def post(self, request):
        link, user, lab, project = _open(request)
        refuse_if_archived(project)
        ser = DropUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # D139: "last edited" names the link's maker, as with file links (VISION S1)
        token = activity_request.set(SimpleNamespace(user=user))
        try:
            item = services.drop_file(
                instrument=link.instrument,
                project=project,
                user=user,
                file=ser.validated_data["file"],
                via=UploadedVia.LINK,
                flag=ser.validated_data["contains_participant_data"],
                link=link,
                request=request,
            )
        finally:
            activity_request.reset(token)
        att = item.attachment
        out = {"name": att.original_filename, "size_bytes": att.size_bytes}
        return Response(PublicDropResultSerializer(out).data, status=status.HTTP_201_CREATED)
