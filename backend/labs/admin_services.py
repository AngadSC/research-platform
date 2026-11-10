"""Admin-area business logic (D146-D151). Writes audit in the same transaction."""

import csv
import io

from django.db import DataError, IntegrityError, transaction
from django.db.models import F, ProtectedError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction as A
from audit.services import record
from core.institution_starters import NATIONAL_RESOURCES, STARTER_RESOURCES, match_institution
from core.models import Institution, User
from documents.services import Conflict
from labs.admin_serializers import InventoryInputSerializer
from labs.models import (
    InstitutionResource,
    InventoryItem,
    InventoryOrder,
    LabEvent,
    LabMembership,
    OnboardingCompletion,
    OnboardingItem,
    OrderStatus,
)

DETAIL_FIELDS = [
    "name",
    "department",
    "description",
    "address",
    "contact_email",
    "website",
    "inventory_enabled",
]


def _members_only_owner(lab, owner_id):
    if owner_id is None:
        return None
    if not LabMembership.objects.for_lab(lab).filter(user_id=owner_id).exists():
        raise ValidationError({"owner": "This person is not a member of the lab."})
    return User.objects.get(pk=owner_id)


def _save(obj):
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:  # D33
        raise ValidationError({"url": "This link is already in the list."}) from exc


# ---------------------------------------------------------------- lab details


@transaction.atomic
def update_lab_details(*, lab, user, data, request=None):
    changed = [f for f in DETAIL_FIELDS if f in data and getattr(lab, f) != data[f]]
    for f in changed:
        setattr(lab, f, data[f])
    new_name = data.get("institution_name")
    if new_name is not None:
        inst = institution_for(new_name)
        if inst.pk != lab.institution_id:
            lab.institution = inst
            changed.append("institution")
    if changed:
        lab.save()
    record(
        A.LAB_UPDATED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"name": lab.name, "changed": changed},
    )
    if "institution" in changed:
        apply_starter_resources(lab, user=user, request=request)
    return lab


def institution_for(name):
    """The Institution for a typed name; a recognised name takes its canonical spelling."""
    name = match_institution(name) or name.strip()
    return Institution.objects.filter(name__iexact=name).first() or Institution.objects.create(
        name=name
    )


def apply_starter_resources(lab, *, user=None, request=None) -> int:
    """Idempotent: adds the institution's starter links and the national links that the lab does
    not have yet, matched by URL, and leaves existing rows alone so a lab's edits survive.
    ponytail: deletions are not tracked, so a link the lab removed comes back the next time
    this runs; add a dismissed-URL list if labs complain."""
    rows = [
        *STARTER_RESOURCES.get(match_institution(lab.institution.name), []),
        *NATIONAL_RESOURCES,
    ]
    added = 0
    for i, row in enumerate(rows):
        res, created = InstitutionResource.objects.for_lab(lab).get_or_create(
            url=row["url"], defaults={**row, "lab": lab, "order": i}
        )  # get_or_create, not a prior read: two clicks at once must not hit the unique constraint
        if not created:
            continue
        record(
            A.INSTITUTION_RESOURCE_CREATED,
            actor=user,
            lab=lab,
            target=res,
            request=request,
            metadata={"source": "starter"},
            actor_label="" if user else "job:institution_resources",
        )
        added += 1
    return added


@transaction.atomic
def load_starter_resources(lab, *, user, request=None) -> dict:
    """The "Get my university's forms" action (D149)."""
    return {
        "added": apply_starter_resources(lab, user=user, request=request),
        "institution": lab.institution.name,
        "curated_institution": match_institution(lab.institution.name),
    }


# ---------------------------------------------------------------- generic CRUD


def _create(model, created, *, lab, user, data, request):
    obj = model(lab=lab, **data)
    _save(obj)
    record(created, actor=user, lab=lab, target=obj, request=request)
    return obj


def _update(obj, updated, *, user, data, request):
    for k, v in data.items():
        setattr(obj, k, v)
    _save(obj)
    record(
        updated,
        actor=user,
        lab=obj.lab,
        target=obj,
        request=request,
        metadata={"changed": sorted(data)},
    )
    return obj


def _delete(obj, deleted, *, user, request):
    record(deleted, actor=user, lab=obj.lab, target=obj, request=request)  # before: repr survives
    obj.delete()


@transaction.atomic
def create_resource(*, lab, user, data, request=None):
    return _create(
        InstitutionResource,
        A.INSTITUTION_RESOURCE_CREATED,
        lab=lab,
        user=user,
        data=data,
        request=request,
    )


@transaction.atomic
def update_resource(obj, *, user, data, request=None):
    return _update(obj, A.INSTITUTION_RESOURCE_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_resource(obj, *, user, request=None):
    _delete(obj, A.INSTITUTION_RESOURCE_DELETED, user=user, request=request)


def _with_training(lab, data):
    """Swap the requirement id for the lab's own requirement (a foreign id reads as unknown)."""
    if "training_requirement" not in data:
        return data
    data = dict(data)
    if (rid := data["training_requirement"]) is not None:
        from training.models import TrainingRequirement

        req = TrainingRequirement.objects.for_lab(lab).filter(pk=rid).first()
        if req is None:
            raise ValidationError({"training_requirement": "This training does not exist."})
        data["training_requirement"] = req
    return data


@transaction.atomic
def create_onboarding_item(*, lab, user, data, request=None):
    data = _with_training(lab, data)
    return _create(
        OnboardingItem, A.ONBOARDING_ITEM_CREATED, lab=lab, user=user, data=data, request=request
    )


@transaction.atomic
def update_onboarding_item(obj, *, user, data, request=None):
    data = _with_training(obj.lab, data)
    return _update(obj, A.ONBOARDING_ITEM_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_onboarding_item(obj, *, user, request=None):
    _delete(obj, A.ONBOARDING_ITEM_DELETED, user=user, request=request)


@transaction.atomic
def set_completion(item, *, member, done, by, request=None):
    lab = item.lab
    if not LabMembership.objects.for_lab(lab).filter(user=member).exists():
        raise ValidationError({"user": "This person is not a member of the lab."})
    qs = OnboardingCompletion.objects.for_lab(lab).filter(item=item, user=member)
    if done and not qs.exists():
        OnboardingCompletion.objects.create(lab=lab, item=item, user=member, completed_by=by)
    elif not done:
        qs.delete()
    else:
        return
    record(
        A.ONBOARDING_COMPLETION_CHANGED,
        actor=by,
        lab=lab,
        target=item,
        request=request,
        metadata={"user": str(member.pk), "done": done},
    )


@transaction.atomic
def create_inventory_item(*, lab, user, data, request=None):
    data = {**data, "owner": _members_only_owner(lab, data.pop("owner", None))}
    return _create(
        InventoryItem, A.INVENTORY_ITEM_CREATED, lab=lab, user=user, data=data, request=request
    )


@transaction.atomic
def update_inventory_item(obj, *, user, data, request=None):
    data = dict(data)
    if "owner" in data:
        data["owner"] = _members_only_owner(obj.lab, data["owner"])
    return _update(obj, A.INVENTORY_ITEM_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_inventory_item(obj, *, user, request=None):
    try:
        with transaction.atomic():
            _delete(obj, A.INVENTORY_ITEM_DELETED, user=user, request=request)
    except ProtectedError as exc:
        raise Conflict(
            "A protocol or a record of use still points at this item. Remove it from the "
            "protocol first, or mark the item as retired instead."
        ) from exc


IMPORT_MAX_BYTES = 1024 * 1024
IMPORT_MAX_ROWS = 1000
_IMPORT_FIELDS = {
    "name",
    "category",
    "location",
    "quantity",
    "unit",
    "serial_number",
    "purchase_date",
    "due_date",
    "status",
    "notes",
}


def _import_header(cell):
    return cell.strip().lower().replace(" ", "_").replace("-", "_")


def _clean_cell(cell):
    """Undo the quote our own export puts in front of a cell that looks like a formula."""
    text = cell.strip()
    return text[1:] if text[:2] in ("'=", "'+", "'-", "'@") else text


def read_inventory_file(lab, upload) -> dict:
    """CSV only (D229): every row is checked and nothing is written here. A file-level problem is
    a 400 for the `file` field; a row-level one comes back beside that row."""
    if upload.size > IMPORT_MAX_BYTES:
        raise ValidationError({"file": "The file is too large (1 MB at most)."})
    raw = upload.read()
    if raw[:2] == b"PK":  # the zip signature of an .xlsx file
        raise ValidationError({"file": "This looks like an Excel file. Save it as CSV first."})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # Excel's "CSV" on Windows
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        header = [_import_header(c) for c in next(reader, [])]
        table = [(reader.line_num, row) for row in reader if any(c.strip() for c in row)]
    except csv.Error as exc:
        raise ValidationError({"file": "This file could not be read as CSV."}) from exc
    if not {"name", "category"} <= set(header):
        raise ValidationError(
            {"file": "The first row must name the columns, including Name and Category."}
        )
    if len(table) > IMPORT_MAX_ROWS:
        raise ValidationError({"file": f"Too many rows ({IMPORT_MAX_ROWS} at most)."})

    existing = {
        n.casefold() for n in InventoryItem.objects.for_lab(lab).values_list("name", flat=True)
    }
    seen, rows, ready = set(), [], []
    for line, cells in table:
        data = {
            f: _clean_cell(c) for f, c in zip(header, cells, strict=False) if f in _IMPORT_FIELDS
        }
        for f in ("category", "status"):
            if f in data:
                data[f] = data[f].lower().replace(" ", "_")
        data = {k: v for k, v in data.items() if v or k in ("name", "category")}
        ser = InventoryInputSerializer(data=data)
        errors = {} if ser.is_valid() else {k: str(v[0]) for k, v in ser.errors.items()}
        name = data.get("name", "")
        rows.append(
            {
                "row": line,
                "name": name,
                "category": data.get("category", ""),
                "quantity": data.get("quantity", ""),
                "unit": data.get("unit", ""),
                "errors": errors,
                "warning": (
                    "An item with this name already exists, so this adds another one."
                    if name.casefold() in existing | seen
                    else ""
                ),
            }
        )
        seen.add(name.casefold())
        if not errors:
            ready.append(ser.validated_data)
    invalid = len(rows) - len(ready)
    return {
        "rows": rows,
        "valid": len(ready),
        "invalid": invalid,
        "imported": 0,
        "ignored_columns": [h for h in header if h and h not in _IMPORT_FIELDS],
        "_ready": ready,
    }


@transaction.atomic
def import_inventory(*, lab, user, ready, request=None) -> int:
    """All rows or none: the caller checks `invalid` first, and any failure here rolls back."""
    for data in ready:
        create_inventory_item(lab=lab, user=user, data=dict(data), request=request)
    record(
        A.INVENTORY_IMPORTED, actor=user, lab=lab, request=request, metadata={"rows": len(ready)}
    )
    return len(ready)


# ---------------------------------------------------------------- inventory orders


def _with_item(lab, data):
    """Swap the item id for the lab's own item (a foreign id reads as unknown)."""
    if "item" not in data:
        return data
    data = dict(data)
    if (item_id := data["item"]) is not None:
        data["item"] = InventoryItem.objects.for_lab(lab).filter(pk=item_id).first()
        if data["item"] is None:
            raise ValidationError({"item": "This inventory item does not exist."})
    return data


def _add_to_stock(order, *, user, request):
    """Only called on the move into received, under the order's row lock (or on creation).
    ponytail: adds `order.quantity` as is, with no unit conversion from the order's unit to the
    item's; compare units here if labs order in different units from the ones they stock."""
    if order.item_id is None:
        return
    try:
        InventoryItem.objects.for_lab(order.lab_id).filter(pk=order.item_id).update(
            quantity=F("quantity") + order.quantity, updated_at=timezone.now()
        )
    except DataError as exc:  # past the column's 12 digits; the surrounding atomic rolls back
        raise ValidationError({"quantity": "That would overflow the item's quantity."}) from exc
    record(
        A.INVENTORY_ITEM_UPDATED,
        actor=user,
        lab=order.lab,
        target=order.item,
        request=request,
        metadata={"changed": ["quantity"], "order": str(order.pk), "added": str(order.quantity)},
    )


@transaction.atomic
def create_inventory_order(*, lab, user, data, request=None):
    data = {**_with_item(lab, data), "requested_by": user}
    order = _create(
        InventoryOrder, A.INVENTORY_ORDER_CREATED, lab=lab, user=user, data=data, request=request
    )
    if order.status == OrderStatus.RECEIVED:
        _add_to_stock(order, user=user, request=request)
    return order


@transaction.atomic
def update_inventory_order(order, *, user, data, request=None):
    """The row lock, plus a received order being frozen, is what makes stock go up exactly once:
    a repeat or concurrent "received" waits here, then sees the status already set."""
    order = InventoryOrder.objects.for_lab(order.lab_id).select_for_update().get(pk=order.pk)
    data = _with_item(order.lab, data)
    was_received = order.status == OrderStatus.RECEIVED
    if was_received and any(k != "notes" and getattr(order, k) != v for k, v in data.items()):
        raise ValidationError(
            {"status": "This order was received and added to stock; only its notes can change."}
        )
    order = _update(order, A.INVENTORY_ORDER_UPDATED, user=user, data=data, request=request)
    if order.status == OrderStatus.RECEIVED and not was_received:
        _add_to_stock(order, user=user, request=request)
    return order


# ---------------------------------------------------------------- calendar events


def _check_event_dates(date, end_date):
    if end_date is not None and end_date < date:
        raise ValidationError({"end_date": "The end date is before the start date."})


@transaction.atomic
def create_lab_event(*, lab, user, data, request=None):
    _check_event_dates(data["date"], data.get("end_date"))
    return _create(
        LabEvent,
        A.LAB_EVENT_CREATED,
        lab=lab,
        user=user,
        data={**data, "created_by": user},
        request=request,
    )


@transaction.atomic
def update_lab_event(obj, *, user, data, request=None):
    _check_event_dates(data.get("date", obj.date), data.get("end_date", obj.end_date))
    return _update(obj, A.LAB_EVENT_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_lab_event(obj, *, user, request=None):
    _delete(obj, A.LAB_EVENT_DELETED, user=user, request=request)
