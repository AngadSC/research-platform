"""Admin area endpoints (D146-D151): lab details live in labs/views.py; resources, onboarding
and inventory are here."""

import csv

from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm
from core.views import LabScopedViewMixin
from labs import admin_services as svc
from labs.admin_serializers import (
    CompletionInputSerializer,
    InventoryInputSerializer,
    InventorySerializer,
    OnboardingItemInputSerializer,
    OnboardingItemSerializer,
    ResourceInputSerializer,
    ResourceSerializer,
    StartersLoadedSerializer,
)
from labs.models import InstitutionResource, InventoryItem, OnboardingItem


def _body(serializer_class, request, partial=False):
    ser = serializer_class(data=request.data, partial=partial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


# ---------------------------------------------------------------- institution resources


class ResourceListCreateView(LabScopedViewMixin, generics.GenericAPIView):
    model = InstitutionResource
    serializer_class = ResourceSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_LAB}

    @extend_schema(
        parameters=[
            OpenApiParameter("category", str, description="ethics, funding, data_management, other")
        ],
        responses=ResourceSerializer(many=True),
    )
    def get(self, request, lab_id):
        qs = self.get_queryset().order_by("category", "order", "title", "id")
        if cat := request.query_params.get("category"):
            qs = qs.filter(category=cat)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=ResourceInputSerializer, responses={201: ResourceSerializer})
    def post(self, request, lab_id):
        obj = svc.create_resource(
            lab=request.lab,
            user=request.user,
            data=_body(ResourceInputSerializer, request),
            request=request,
        )
        return Response(self.get_serializer(obj).data, status=status.HTTP_201_CREATED)


class ResourceDetailView(LabScopedViewMixin, generics.GenericAPIView):
    model = InstitutionResource
    serializer_class = ResourceSerializer
    lookup_url_kwarg = "institutionresource_id"
    perms = {"PATCH": Perm.MANAGE_LAB, "DELETE": Perm.MANAGE_LAB}

    @extend_schema(request=ResourceInputSerializer, responses=ResourceSerializer)
    def patch(self, request, lab_id, institutionresource_id):
        obj = svc.update_resource(
            self.get_object(),
            user=request.user,
            data=_body(ResourceInputSerializer, request, True),
            request=request,
        )
        return Response(self.get_serializer(obj).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, institutionresource_id):
        svc.delete_resource(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResourceLoadStartersView(LabScopedViewMixin, generics.GenericAPIView):
    """Copy the lab's university links and the national links into the lab (D149)."""

    serializer_class = StartersLoadedSerializer
    pagination_class = None
    perms = {"POST": Perm.MANAGE_LAB}

    @extend_schema(request=None, responses=StartersLoadedSerializer)
    def post(self, request, lab_id):
        result = svc.load_starter_resources(request.lab, user=request.user, request=request)
        return Response(self.get_serializer(result).data)


# ---------------------------------------------------------------- onboarding


class OnboardingMixin(LabScopedViewMixin):
    model = OnboardingItem
    serializer_class = OnboardingItemSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().prefetch_related("completions")

    def out(self, obj, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=obj.pk)).data, status=code)


class OnboardingListCreateView(OnboardingMixin, generics.GenericAPIView):
    perms = {"GET": Perm.MANAGE_LAB, "POST": Perm.MANAGE_LAB}

    @extend_schema(responses=OnboardingItemSerializer(many=True))
    def get(self, request, lab_id):
        qs = self.get_queryset().order_by("kind", "order", "created_at", "id")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=OnboardingItemInputSerializer, responses={201: OnboardingItemSerializer})
    def post(self, request, lab_id):
        obj = svc.create_onboarding_item(
            lab=request.lab,
            user=request.user,
            data=_body(OnboardingItemInputSerializer, request),
            request=request,
        )
        return self.out(obj, status.HTTP_201_CREATED)


class OnboardingDetailView(OnboardingMixin, generics.GenericAPIView):
    lookup_url_kwarg = "onboardingitem_id"
    perms = {"PATCH": Perm.MANAGE_LAB, "DELETE": Perm.MANAGE_LAB}

    @extend_schema(request=OnboardingItemInputSerializer, responses=OnboardingItemSerializer)
    def patch(self, request, lab_id, onboardingitem_id):
        obj = svc.update_onboarding_item(
            self.get_object(),
            user=request.user,
            data=_body(OnboardingItemInputSerializer, request, True),
            request=request,
        )
        return self.out(obj)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, onboardingitem_id):
        svc.delete_onboarding_item(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OnboardingCompletionView(OnboardingMixin, generics.GenericAPIView):
    lookup_url_kwarg = "onboardingitem_id"
    perms = {"POST": Perm.MANAGE_LAB}

    @extend_schema(request=CompletionInputSerializer, responses=OnboardingItemSerializer)
    def post(self, request, lab_id, onboardingitem_id):
        item = self.get_object()
        data = _body(CompletionInputSerializer, request)
        svc.set_completion(
            item, member=data["user"], done=data["done"], by=request.user, request=request
        )
        return self.out(item)


# ---------------------------------------------------------------- inventory

ORDERINGS = {
    "name",
    "category",
    "location",
    "quantity",
    "status",
    "serial_number",
    "purchase_date",
    "due_date",
    "owner__display_name",
}

Q_PARAMS = [
    OpenApiParameter("q", str, description="Search name, location, serial number, notes"),
    OpenApiParameter("category", str),
    OpenApiParameter("ordering", str, description="A field name, '-' prefix for descending"),
]


def _filtered(qs, params):
    if q := params.get("q", "").strip():
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(location__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(notes__icontains=q)
            | Q(unit__icontains=q)
        )
    if cat := params.get("category"):
        qs = qs.filter(category=cat)
    order = params.get("ordering", "name")
    if order.lstrip("-") not in ORDERINGS:
        order = "name"
    return qs.order_by(order, "id")


class InventoryMixin(LabScopedViewMixin):
    model = InventoryItem
    serializer_class = InventorySerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().select_related("owner")

    def out(self, obj, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=obj.pk)).data, status=code)


class InventoryListCreateView(InventoryMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_INVENTORY}

    @extend_schema(parameters=Q_PARAMS, responses=InventorySerializer(many=True))
    def get(self, request, lab_id):
        qs = _filtered(self.get_queryset(), request.query_params)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=InventoryInputSerializer, responses={201: InventorySerializer})
    def post(self, request, lab_id):
        obj = svc.create_inventory_item(
            lab=request.lab,
            user=request.user,
            data=_body(InventoryInputSerializer, request),
            request=request,
        )
        return self.out(obj, status.HTTP_201_CREATED)


def _safe_cell(value):
    """Spreadsheet formula injection: a leading = + - @ makes Excel run the cell."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class InventoryExportView(InventoryMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(parameters=Q_PARAMS, responses=OpenApiTypes.BINARY)
    def get(self, request, lab_id):
        qs = _filtered(self.get_queryset(), request.query_params)
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="inventory.csv"'
        w = csv.writer(resp)
        w.writerow(
            [
                "Name",
                "Category",
                "Location",
                "Quantity",
                "Unit",
                "Owner",
                "Serial number",
                "Purchase date",
                "Due date",
                "Status",
                "Notes",
            ]
        )
        count = 0
        for i in qs:
            owner = (i.owner.display_name or i.owner.email) if i.owner else ""
            row = [i.name, i.category, i.location, i.quantity, i.unit, owner, i.serial_number]
            row += [i.purchase_date, i.due_date, i.status, i.notes]
            w.writerow(_safe_cell(v) for v in row)
            count += 1
        record(
            AuditAction.INVENTORY_EXPORTED,
            actor=request.user,
            lab=request.lab,
            request=request,
            metadata={"rows": count},
        )
        return resp


class InventoryDetailView(InventoryMixin, generics.GenericAPIView):
    lookup_url_kwarg = "inventoryitem_id"
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_INVENTORY, "DELETE": Perm.MANAGE_INVENTORY}

    @extend_schema(responses=InventorySerializer)
    def get(self, request, lab_id, inventoryitem_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=InventoryInputSerializer, responses=InventorySerializer)
    def patch(self, request, lab_id, inventoryitem_id):
        obj = svc.update_inventory_item(
            self.get_object(),
            user=request.user,
            data=_body(InventoryInputSerializer, request, True),
            request=request,
        )
        return self.out(obj)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, inventoryitem_id):
        svc.delete_inventory_item(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
