"""Per-project protocols and using stock (D228).

A protocol lists reagents from the lab's inventory and how much of each. Recording a use takes
the amount off the item's total in one conditional database update, so concurrent clicks cannot
lose an update or go below zero; `request_id` means a repeated click takes stock only once.
"""

from decimal import Decimal

from django.db import DataError, IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import Perm, can, can_reverse_usage
from core.serializers import UserSerializer, no_control_chars
from core.views import LabScopedViewMixin
from labs import low_stock
from labs.models import InventoryItem, InventoryUsage, Protocol, ProtocolReagent
from labs.units import convert
from projects.views import ProjectScopedMixin

USAGE_LIST_LIMIT = 200


def unit_message(unit: str, item) -> str:
    """D328: litres, millilitres and microlitres convert (so do grams, milligrams and so on), but
    other units only match themselves, so anything else stops here and says what to change."""
    return (
        f'"{unit or "no unit"}" cannot be taken from {item.name}, which is counted in '
        f'"{item.unit or "no unit"}". Use the same unit or one of the same kind '
        "(for example mL for litres)."
    )


def _qty(value) -> str:
    return f"{value:f}".rstrip("0").rstrip(".") if "." in f"{value:f}" else f"{value:f}"


def can_reverse_lab_use(user, usage) -> bool:
    """A use logged on the item (no project): the person who logged it, or whoever manages
    inventory. A project's use follows the project rules (D228)."""
    if usage.project_id is not None:
        return can_reverse_usage(user, usage)
    return usage.used_by_id == user.pk or can(user, Perm.MANAGE_INVENTORY, usage.item)


# ---------------------------------------------------------------- output and input


class ProtocolReagentSerializer(serializers.ModelSerializer):
    item = serializers.UUIDField(source="item_id")
    item_name = serializers.CharField(source="item.name")
    stock = serializers.DecimalField(source="item.quantity", max_digits=18, decimal_places=6)
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
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0.000001")
    )
    unit = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")


class ProtocolInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, validators=[no_control_chars])
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)
    reagents = ReagentInputSerializer(many=True, required=False, max_length=50)


class UseInputSerializer(serializers.Serializer):
    reagent = serializers.UUIDField()
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0.000001"), required=False
    )
    request_id = serializers.UUIDField(help_text="New per click; a repeat of one takes stock once.")


class ItemUseInputSerializer(serializers.Serializer):
    """Log a use straight on an inventory item (D328): any unit of the same kind as the item's."""

    amount = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0.000001")
    )
    unit = serializers.CharField(max_length=32, allow_blank=True, required=False, default="")
    project = serializers.UUIDField(required=False, allow_null=True, default=None)
    note = serializers.CharField(
        max_length=300, allow_blank=True, required=False, default="", validators=[no_control_chars]
    )
    request_id = serializers.UUIDField(help_text="New per click; a repeat of one takes stock once.")


class InventoryUsageSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name")
    item_unit = serializers.CharField(source="item.unit")
    project_name = serializers.SerializerMethodField()
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
            "project",
            "project_name",
            "item_unit",
            "amount",
            "unit",
            "deducted",
            "note",
            "used_by",
            "created_at",
            "reversed_at",
            "can_reverse",
        ]
        read_only_fields = fields

    def get_project_name(self, usage) -> str:
        return usage.project.name if usage.project_id else ""

    def get_can_reverse(self, usage) -> bool:
        if usage.reversed_at is not None:
            return False
        return can_reverse_lab_use(self.context["request"].user, usage)


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
        if convert(r["amount"], r["unit"], items[r["item"]].unit) is None:
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


def _take_stock(
    *, lab, item, amount, unit, user, request_id, request, project=None, protocol=None, note=""
):
    """Exactly once: the usage row (unique per request_id) and the conditional update share a
    transaction, so a repeat changes nothing and a refused amount leaves no record. `amount` is in
    `unit`; what leaves the item is that amount in the item's own unit (D328)."""
    deducted = convert(amount, unit, item.unit)
    if deducted is None:
        raise ValidationError({"unit": unit_message(unit, item)})
    if deducted <= 0:
        raise ValidationError({"amount": "That amount is too small to count in this item's unit."})
    usage = InventoryUsage(
        lab=lab,
        project=project,
        protocol=protocol,
        protocol_name=protocol.name if protocol else "",
        item=item,
        amount=amount,
        unit=unit.strip(),
        deducted=deducted,
        note=note,
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
        .filter(pk=item.pk, quantity__gte=deducted)
        .update(quantity=F("quantity") - deducted, updated_at=timezone.now())
    )
    if not updated:
        left = InventoryItem.objects.for_lab(lab).get(pk=item.pk).quantity
        raise ValidationError(
            {
                "amount": f"Only {_qty(left)} {item.unit} of {item.name} is left, so "
                f"{_qty(amount)} {unit} cannot be taken. Nothing was changed."
            }
        )
    low_stock.check(
        item.pk,
        lab.pk,
        before=InventoryItem.objects.for_lab(lab).get(pk=item.pk).quantity + deducted,
    )
    record(
        A.INVENTORY_USED,
        actor=user,
        lab=lab,
        target=item,
        request=request,
        metadata={
            "amount": str(amount),
            "unit": unit.strip(),
            "deducted": str(deducted),
            "usage": str(usage.pk),
            **({"protocol": str(protocol.pk)} if protocol else {}),
            **({"project": str(project.pk)} if project else {}),
        },
    )
    return usage


@transaction.atomic
def record_use(*, protocol, reagent_id, amount, request_id, user, request=None):
    """Take a protocol line's stock (or `amount` of it) for the project."""
    lab = protocol.lab
    reagent = (
        ProtocolReagent.objects.for_lab(lab)
        .select_related("item")
        .filter(protocol=protocol, pk=reagent_id)
        .first()
    )
    if reagent is None:
        raise ValidationError({"reagent": "This reagent is not in this protocol."})
    return _take_stock(
        lab=lab,
        item=reagent.item,
        amount=amount if amount is not None else reagent.amount,
        unit=reagent.unit,
        user=user,
        request_id=request_id,
        request=request,
        project=protocol.project,
        protocol=protocol,
    )


@transaction.atomic
def log_use(*, item, amount, unit, request_id, user, project=None, note="", request=None):
    """Log a use straight on an item: "10 mL of the 100 L of water". With a project it counts
    towards that project (and the person must be able to edit it); without, it is the lab's."""
    return _take_stock(
        lab=item.lab,
        item=item,
        amount=amount,
        unit=unit,
        user=user,
        request_id=request_id,
        request=request,
        project=project,
        note=note,
    )


@transaction.atomic
def reverse_use(usage, *, user, request=None):
    """Exactly once as well: only the update that flips `reversed_at` puts the amount back."""
    lab = usage.lab
    item = usage.item
    back = usage.deducted if usage.deducted is not None else usage.amount
    flipped = (
        InventoryUsage.objects.for_lab(lab)
        .filter(pk=usage.pk, reversed_at__isnull=True)
        .update(reversed_at=timezone.now(), reversed_by=user)
    )
    if not flipped:
        raise ValidationError({"detail": "This use has already been reversed."})
    try:
        InventoryItem.objects.for_lab(lab).filter(pk=item.pk).update(
            quantity=F("quantity") + back, updated_at=timezone.now()
        )
    except DataError as exc:  # past the column's 18 digits; the transaction rolls back
        raise ValidationError({"detail": "That would overflow the item's quantity."}) from exc
    record(
        A.INVENTORY_USE_REVERSED,
        actor=user,
        lab=lab,
        target=item,
        request=request,
        metadata={"amount": str(back), "unit": item.unit, "usage": str(usage.pk)},
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


# ---------------------------------------------------------------- uses logged on an item (D328)


class _ItemUse(LabScopedViewMixin, generics.GenericAPIView):
    model = InventoryItem
    serializer_class = InventoryUsageSerializer
    pagination_class = None
    needs_inventory = True


class ItemUsageView(_ItemUse):
    """GET the item's recent uses (everyone in the lab); POST logs one (anyone who contributes)."""

    lookup_url_kwarg = "inventoryitem_id"
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CONTRIBUTE_LAB}

    def _rows(self, item):
        return (
            InventoryUsage.objects.for_lab(item.lab_id)
            .filter(item=item)
            .select_related("item", "used_by", "project")
            .order_by("-created_at", "id")[:USAGE_LIST_LIMIT]
        )

    @extend_schema(responses=InventoryUsageSerializer(many=True))
    def get(self, request, lab_id, inventoryitem_id):
        rows = self._rows(self.get_object())
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(request=ItemUseInputSerializer, responses={201: InventoryUsageSerializer})
    def post(self, request, lab_id, inventoryitem_id):
        from core.permissions import can as _can
        from projects.models import Project

        item = self.get_object()
        ser = ItemUseInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        project = None
        if data["project"]:
            project = (
                Project.objects.visible_to(request.user, request.lab)
                .filter(pk=data["project"])
                .first()
            )
            if project is None or not _can(request.user, Perm.EDIT_CONTENT, project):
                raise ValidationError({"project": "Pick a project you can edit."})
        usage = log_use(
            item=item,
            amount=data["amount"],
            unit=data["unit"],
            request_id=data["request_id"],
            user=request.user,
            project=project,
            note=data["note"],
            request=request,
        )
        usage = (
            InventoryUsage.objects.for_lab(item.lab_id)
            .select_related("item", "used_by", "project")
            .get(pk=usage.pk)
        )
        return Response(
            InventoryUsageSerializer(usage, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class ItemUsageReverseView(LabScopedViewMixin, generics.GenericAPIView):
    """Undo a use logged on an item: the person who logged it, or whoever manages inventory."""

    model = InventoryUsage
    serializer_class = InventoryUsageSerializer
    lookup_url_kwarg = "itemusage_id"
    needs_inventory = True
    perms = {"POST": Perm.CONTRIBUTE_LAB}

    def get_queryset(self):
        return InventoryUsage.objects.for_lab(self.request.lab.pk).filter(project__isnull=True)

    @extend_schema(request=None, responses=InventoryUsageSerializer)
    def post(self, request, lab_id, itemusage_id):
        # Not get_object(): its object check reads a usage with no project as unresolvable.
        # The lab-wide permission was already checked, and `can_reverse_lab_use` decides who.
        usage = get_object_or_404(self.get_queryset(), pk=itemusage_id)
        if not can_reverse_lab_use(request.user, usage):
            raise PermissionDenied("Only the person who logged this, or an inventory manager, can.")
        reverse_use(usage, user=request.user, request=request)
        usage = self.get_queryset().select_related("item", "used_by", "project").get(pk=usage.pk)
        return Response(self.get_serializer(usage).data)
