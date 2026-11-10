"""Per-project protocols and using stock (D228).

A protocol lists reagents from the lab's inventory and how much of each. Recording a use takes
the amount off the item's total in one conditional database update, so concurrent clicks cannot
lose an update or go below zero; `request_id` means a repeated click takes stock only once.
"""

from decimal import Decimal

from django.db import DataError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import Perm, can_reverse_usage
from core.serializers import UserSerializer, no_control_chars
from labs.models import InventoryItem, InventoryUsage, Protocol, ProtocolReagent
from projects.views import ProjectScopedMixin

USAGE_LIST_LIMIT = 200


def same_unit(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def unit_message(unit: str, item) -> str:
    """D217, D228: no unit conversion, so a mismatch stops here and says what to change."""
    return (
        f'This uses "{unit or "no unit"}" but {item.name} is counted in '
        f'"{item.unit or "no unit"}". We do not convert units, so change one to match.'
    )


def _qty(value) -> str:
    return f"{value:f}".rstrip("0").rstrip(".") if "." in f"{value:f}" else f"{value:f}"


# ---------------------------------------------------------------- output and input


class ProtocolReagentSerializer(serializers.ModelSerializer):
    item = serializers.UUIDField(source="item_id")
    item_name = serializers.CharField(source="item.name")
    stock = serializers.DecimalField(source="item.quantity", max_digits=12, decimal_places=2)
    stock_unit = serializers.CharField(source="item.unit")

    class Meta:
        model = ProtocolReagent
        fields = ["id", "item", "item_name", "amount", "unit", "stock", "stock_unit"]
        read_only_fields = fields


class ProtocolSerializer(serializers.ModelSerializer):
    reagents = ProtocolReagentSerializer(many=True)

    class Meta:
        model = Protocol
        fields = ["id", "name", "notes", "reagents", "created_at"]
        read_only_fields = fields


class ReagentInputSerializer(serializers.Serializer):
    item = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unit = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")


class ProtocolInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    reagents = ReagentInputSerializer(many=True, required=False, max_length=50)


class UseInputSerializer(serializers.Serializer):
    reagent = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    request_id = serializers.UUIDField(help_text="New per click; a repeat of one takes stock once.")


class InventoryUsageSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name")
    used_by = UserSerializer()
    can_reverse = serializers.SerializerMethodField()

    class Meta:
        model = InventoryUsage
        fields = [
            "id",
            "item",
            "item_name",
            "protocol",
            "protocol_name",
            "amount",
            "unit",
            "used_by",
            "created_at",
            "reversed_at",
            "can_reverse",
        ]
        read_only_fields = fields

    def get_can_reverse(self, usage) -> bool:
        return usage.reversed_at is None and can_reverse_usage(self.context["request"].user, usage)


# ---------------------------------------------------------------- services


def _replace_reagents(protocol, lines):
    if len({line["item"] for line in lines}) != len(lines):
        raise ValidationError({"reagents": "List each reagent only once."})
    lab = protocol.lab_id
    items = {
        i.pk: i
        for i in InventoryItem.objects.for_lab(lab).filter(pk__in=[r["item"] for r in lines])
    }
    if len(items) != len(lines):
        raise ValidationError({"reagents": "One of these items is not in this lab's inventory."})
    for r in lines:
        if not same_unit(r["unit"], items[r["item"]].unit):
            raise ValidationError({"reagents": unit_message(r["unit"], items[r["item"]])})
    ProtocolReagent.objects.for_lab(lab).filter(protocol=protocol).delete()
    ProtocolReagent.objects.bulk_create(
        ProtocolReagent(
            lab_id=lab,
            protocol=protocol,
            item=items[r["item"]],
            amount=r["amount"],
            unit=r["unit"].strip(),
        )
        for r in lines
    )


@transaction.atomic
def create_protocol(*, project, user, data, request=None):
    lines = data.pop("reagents", [])
    protocol = Protocol(lab=project.lab, project=project, created_by=user, **data)
    protocol.save()
    _replace_reagents(protocol, lines)
    record(A.PROTOCOL_CREATED, actor=user, lab=project.lab, target=protocol, request=request)
    return protocol


@transaction.atomic
def update_protocol(protocol, *, user, data, request=None):
    lines = data.pop("reagents", None)
    for key, value in data.items():
        setattr(protocol, key, value)
    protocol.save()
    if lines is not None:
        _replace_reagents(protocol, lines)
    record(
        A.PROTOCOL_UPDATED,
        actor=user,
        lab=protocol.lab,
        target=protocol,
        request=request,
        metadata={"fields": sorted([*data, *([] if lines is None else ["reagents"])])},
    )
    return protocol


@transaction.atomic
def delete_protocol(protocol, *, user, request=None):
    record(A.PROTOCOL_DELETED, actor=user, lab=protocol.lab, target=protocol, request=request)
    protocol.delete()


@transaction.atomic
def record_use(*, protocol, reagent_id, amount, request_id, user, request=None):
    """Exactly once: the usage row (unique per request_id) and the conditional update share a
    transaction, so a repeat changes nothing and a refused amount leaves no record."""
    lab = protocol.lab
    reagent = (
        ProtocolReagent.objects.for_lab(lab)
        .select_related("item")
        .filter(protocol=protocol, pk=reagent_id)
        .first()
    )
    if reagent is None:
        raise ValidationError({"reagent": "This reagent is not in this protocol."})
    item, amount = reagent.item, amount if amount is not None else reagent.amount
    if not same_unit(reagent.unit, item.unit):
        raise ValidationError({"amount": unit_message(reagent.unit, item)})

    usage = InventoryUsage(
        lab=lab,
        project=protocol.project,
        protocol=protocol,
        protocol_name=protocol.name,
        item=item,
        amount=amount,
        unit=reagent.unit,
        used_by=user,
        request_id=request_id,
    )
    try:
        with transaction.atomic():
            usage.save()
    except IntegrityError:
        # The same click arrived twice; the first one already took the stock.
        first = (
            InventoryUsage.objects.for_lab(lab)
            .filter(request_id=request_id, used_by=user, item=item)
            .first()
        )
        if first is None:  # the id is taken by someone else's record: never reuse it
            raise ValidationError({"request_id": "Try that again."}) from None
        return first

    updated = (
        InventoryItem.objects.for_lab(lab)
        .filter(pk=item.pk, quantity__gte=amount)
        .update(quantity=F("quantity") - amount, updated_at=timezone.now())
    )
    if not updated:
        left = InventoryItem.objects.for_lab(lab).get(pk=item.pk).quantity
        raise ValidationError(
            {
                "amount": f"Only {_qty(left)} {item.unit} of {item.name} is left, so "
                f"{_qty(amount)} {item.unit} cannot be taken. Nothing was changed."
            }
        )
    record(
        A.INVENTORY_USED,
        actor=user,
        lab=lab,
        target=item,
        request=request,
        metadata={
            "amount": str(amount),
            "unit": reagent.unit,
            "protocol": str(protocol.pk),
            "project": str(protocol.project_id),
            "usage": str(usage.pk),
        },
    )
    return usage


@transaction.atomic
def reverse_use(usage, *, user, request=None):
    """Exactly once as well: only the update that flips `reversed_at` puts the amount back."""
    lab = usage.lab
    item = usage.item
    if not same_unit(usage.unit, item.unit):
        raise ValidationError({"detail": unit_message(usage.unit, item)})
    flipped = (
        InventoryUsage.objects.for_lab(lab)
        .filter(pk=usage.pk, reversed_at__isnull=True)
        .update(reversed_at=timezone.now(), reversed_by=user)
    )
    if not flipped:
        raise ValidationError({"detail": "This use has already been reversed."})
    try:
        InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(
            quantity=F("quantity") + usage.amount, updated_at=timezone.now()
        )
    except DataError as exc:  # past the column's 12 digits; the transaction rolls back
        raise ValidationError({"detail": "That would overflow the item's quantity."}) from exc
    record(
        A.INVENTORY_USE_REVERSED,
        actor=user,
        lab=lab,
        target=item,
        request=request,
        metadata={"amount": str(usage.amount), "unit": usage.unit, "usage": str(usage.pk)},
    )
    usage.refresh_from_db(fields=["reversed_at", "reversed_by"])
    return usage


# ---------------------------------------------------------------- views


class _Inventory(ProjectScopedMixin, generics.GenericAPIView):
    needs_inventory = True  # D227: HasPerm answers 403 while the lab has inventory turned off


class _ProtocolMixin(_Inventory):
    model = Protocol
    serializer_class = ProtocolSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("reagents__item").order_by("name", "id")


class ProtocolListCreateView(_ProtocolMixin):
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=ProtocolSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=ProtocolInputSerializer, responses={201: ProtocolSerializer})
    def post(self, request, lab_id, project_id):
        protocol = create_protocol(
            project=self.project,
            user=request.user,
            data=dict(self.body(ProtocolInputSerializer)),
            request=request,
        )
        return self.out(self.get_queryset().get(pk=protocol.pk), status.HTTP_201_CREATED)


class ProtocolDetailView(_ProtocolMixin):
    lookup_url_kwarg = "protocol_id"
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(request=ProtocolInputSerializer, responses=ProtocolSerializer)
    def patch(self, request, lab_id, protocol_id):
        update_protocol(
            self.get_object(),
            user=request.user,
            data=dict(self.body(ProtocolInputSerializer)),
            request=request,
        )
        return self.out(self.get_queryset().get(pk=protocol_id))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, protocol_id):
        delete_protocol(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProtocolUseView(_ProtocolMixin):
    lookup_url_kwarg = "protocol_id"
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=UseInputSerializer, responses={201: InventoryUsageSerializer})
    def post(self, request, lab_id, protocol_id):
        data = self.body(UseInputSerializer)
        usage = record_use(
            protocol=self.get_object(),
            reagent_id=data["reagent"],
            amount=data.get("amount"),
            request_id=data["request_id"],
            user=request.user,
            request=request,
        )
        return Response(
            InventoryUsageSerializer(usage, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class UsageListView(_Inventory):
    model = InventoryUsage
    serializer_class = InventoryUsageSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=InventoryUsageSerializer(many=True))
    def get(self, request, lab_id, project_id):
        rows = (
            self.get_queryset()
            .select_related("item", "used_by", "project")
            .order_by("-created_at", "id")[:USAGE_LIST_LIMIT]
        )
        return Response(self.get_serializer(rows, many=True).data)


class UsageReverseView(_Inventory):
    model = InventoryUsage
    serializer_class = InventoryUsageSerializer
    lookup_url_kwarg = "inventoryusage_id"
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=None, responses=InventoryUsageSerializer)
    def post(self, request, lab_id, inventoryusage_id):
        usage = self.get_object()
        if not can_reverse_usage(request.user, usage):
            raise PermissionDenied("Only the person who recorded this, or a project lead, can.")
        return self.out(reverse_use(usage, user=request.user, request=request))
