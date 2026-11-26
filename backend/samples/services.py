"""Sample registry and storage writes. Each writes its audit event in the same transaction."""

import csv
import io
import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import visible_projects
from documents import services as document_services
from documents.models import Attachment
from documents.services import Conflict
from labs.admin_services import (
    IMPORT_MAX_BYTES,
    IMPORT_MAX_ROWS,
    _clean_cell,
    _import_header,
    _members_only_owner,
    _same,
)
from labs.models import InventoryItem
from samples.models import (
    CODE_PREFIX,
    Sample,
    SampleKind,
    StorageBox,
    StorageUnit,
    Tube,
    position_label,
)
from samples.serializers import SampleInputSerializer

LINKS = ("parents", "projects", "linked_files")


def next_codes(lab) -> dict[str, str]:
    """Per kind, the prefix and one more than the highest number used (deleted entries too)."""
    highest = dict.fromkeys(CODE_PREFIX, 0)
    by_prefix = {p: k for k, p in CODE_PREFIX.items()}
    for code in Sample.objects.for_lab(lab).values_list("code", flat=True):
        m = re.fullmatch(r"([A-Z]+)(\d+)", code)
        if m and m[1] in by_prefix:
            kind = by_prefix[m[1]]
            highest[kind] = max(highest[kind], int(m[2]))
    return {k: f"{CODE_PREFIX[k]}{highest[k] + 1:04d}" for k in CODE_PREFIX}


def _code_taken(lab, code, exclude=None) -> bool:
    qs = Sample.objects.for_lab(lab).filter(code=code, deleted_at__isnull=True)
    return qs.exclude(pk=exclude).exists() if exclude else qs.exists()


def _set_links(sample, links, *, user):
    """Replace parents, projects and linked files with the ones given, among those this person
    can see. Links to things they cannot see are kept: they never knew those were there."""
    lab = sample.lab
    if "parents" in links:
        seen = Sample.objects.visible_to(user, lab)
        wanted = list(seen.filter(pk__in=links["parents"]).exclude(pk=sample.pk))
        if len(wanted) != len({p for p in links["parents"] if p != sample.pk}):
            raise ValidationError({"parents": "One of these samples does not exist."})
        ancestors, frontier = set(), {p.pk for p in wanted}
        while frontier:  # a parent may not descend from this sample
            if sample.pk in frontier:
                raise ValidationError({"parents": "A sample can't be its own ancestor."})
            ancestors |= frontier
            frontier = (
                set(
                    Sample.parents.through.objects.filter(from_sample_id__in=frontier).values_list(
                        "to_sample_id", flat=True
                    )
                )
                - ancestors
            )
        hidden = sample.parents.exclude(pk__in=seen.values("pk"))
        sample.parents.set([*wanted, *hidden])
    if "projects" in links:
        seen = visible_projects(user, lab).filter(deleted_at__isnull=True)
        wanted = list(seen.filter(pk__in=links["projects"]))
        if len(wanted) != len(set(links["projects"])):
            raise ValidationError({"projects": "One of these projects does not exist."})
        hidden = sample.projects.exclude(pk__in=seen.values("pk"))
        sample.projects.set([*wanted, *hidden])
    if "linked_files" in links:
        seen = Attachment.objects.visible_to(user, lab).filter(
            deleted_at__isnull=True, project__isnull=False
        )
        wanted = list(seen.filter(pk__in=links["linked_files"]))
        if len(wanted) != len(set(links["linked_files"])):
            raise ValidationError({"linked_files": "One of these files does not exist."})
        hidden = sample.linked_files.exclude(pk__in=seen.values("pk"))
        sample.linked_files.set([*wanted, *hidden])


def _save(sample):
    try:
        with transaction.atomic():
            sample.save()
    except IntegrityError as exc:  # two saves raced for one code
        raise ValidationError({"code": "Another sample already has this code."}) from exc


@transaction.atomic
def create_sample(*, lab, user, data, request=None, audit=True):
    data = dict(data)
    links = {k: data.pop(k) for k in LINKS if k in data}
    data["owner"] = _members_only_owner(lab, data.pop("owner", None))
    if not data.get("code"):
        data["code"] = next_codes(lab)[data["kind"]]
    elif _code_taken(lab, data["code"]):
        raise ValidationError({"code": "Another sample already has this code."})
    sample = Sample(lab=lab, **data)
    _save(sample)
    _set_links(sample, links, user=user)
    if audit:
        record(A.SAMPLE_CREATED, actor=user, lab=lab, target=sample, request=request)
    return sample


@transaction.atomic
def update_sample(sample, *, user, data, request=None):
    data = dict(data)
    links = {k: data.pop(k) for k in LINKS if k in data}
    if "owner" in data:
        data["owner"] = _members_only_owner(sample.lab, data["owner"])
    if "code" in data and _code_taken(sample.lab, data["code"], exclude=sample.pk):
        raise ValidationError({"code": "Another sample already has this code."})
    changed = sorted(k for k, v in data.items() if not _same(getattr(sample, k), v))
    for k, v in data.items():
        setattr(sample, k, v)
    if changed:
        _save(sample)
    if links:
        _set_links(sample, links, user=user)
        changed += sorted(links)
    if changed:
        record(
            A.SAMPLE_UPDATED,
            actor=user,
            lab=sample.lab,
            target=sample,
            request=request,
            metadata={"changed": changed},
        )
    return sample


@transaction.atomic
def delete_sample(sample, *, user, request=None):
    """Soft delete. Its tubes must be taken out first, so no box points at a deleted entry."""
    tubes = sample.tubes.count()
    if tubes:
        raise Conflict(
            f"This sample still has {tubes} {'tube' if tubes == 1 else 'tubes'} in storage. "
            "Take them out first, or archive the sample instead."
        )
    now = timezone.now()
    sample.deleted_at = now
    sample.save(update_fields=["deleted_at", "updated_at"])
    sample.attachments.filter(deleted_at__isnull=True).update(deleted_at=now)
    record(A.SAMPLE_DELETED, actor=user, lab=sample.lab, target=sample, request=request)


def upload_file(sample, *, user, file=None, drive_file_id=None, request=None):
    return document_services.upload_attachment(
        sample=sample, user=user, file=file, drive_file_id=drive_file_id, request=request
    )


# ---------------------------------------------------------------- CSV import


_KINDS = {
    **{k.value: k.value for k in SampleKind},
    **{k.label.lower(): k.value for k in SampleKind},
}
_STATUS_WORDS = {"in use": "in_use", "verified": "verified", "archived": "archived"}
IMPORT_FIELDS = {
    "kind",
    "code",
    "name",
    "description",
    "status",
    "backbone",
    "insert",
    "resistance",
    "tag",
    "species",
    "genotype",
    "sequence",
    "concentration",
    "buffer",
    "made_on",
}


def read_file(lab, upload) -> dict:
    """Like the inventory import (D229): CSV only, every row checked, nothing written here.
    A row without a code gets the next free one for its kind."""
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
    if not {"name", "kind"} <= set(header):
        raise ValidationError(
            {"file": "The first row must name the columns, including Name and Kind."}
        )
    if len(table) > IMPORT_MAX_ROWS:
        raise ValidationError({"file": f"Too many rows ({IMPORT_MAX_ROWS} at most)."})

    codes = next_codes(lab)
    taken = set(
        Sample.objects.for_lab(lab).filter(deleted_at__isnull=True).values_list("code", flat=True)
    )
    rows, ready = [], []
    for line, cells in table:
        data = {
            f: _clean_cell(c) for f, c in zip(header, cells, strict=False) if f in IMPORT_FIELDS
        }
        data["kind"] = _KINDS.get(data.get("kind", "").lower(), data.get("kind", ""))
        if "status" in data:
            data["status"] = _STATUS_WORDS.get(data["status"].lower(), data["status"])
        data = {k: v for k, v in data.items() if v or k in ("name", "kind")}
        ser = SampleInputSerializer(data=data)
        errors = {} if ser.is_valid() else {k: str(v[0]) for k, v in ser.errors.items()}
        if "kind" in errors:
            errors["kind"] = "Use one of: " + ", ".join(k.label for k in SampleKind) + "."
        code = ser.validated_data.get("code", "") if not errors else data.get("code", "")
        if not errors and not code:  # the next free code, counting earlier rows too
            prefix = codes[data["kind"]].rstrip("0123456789")
            n = int(codes[data["kind"]][len(prefix) :])
            while f"{prefix}{n:04d}" in taken:
                n += 1
            code = f"{prefix}{n:04d}"
            codes[data["kind"]] = f"{prefix}{n + 1:04d}"
        elif not errors and code in taken:
            errors["code"] = "Another sample already has this code."
        rows.append(
            {
                "row": line,
                "code": code,
                "kind": data.get("kind", ""),
                "name": data.get("name", ""),
                "errors": errors,
            }
        )
        if not errors:
            taken.add(code)
            ready.append({**ser.validated_data, "code": code})
    return {
        "rows": rows,
        "valid": len(ready),
        "invalid": len(rows) - len(ready),
        "imported": 0,
        "ignored_columns": [h for h in header if h and h not in IMPORT_FIELDS],
        "_ready": ready,
    }


@transaction.atomic
def import_samples(*, lab, user, ready, request=None) -> int:
    """All rows or none. One audit event for the file, not one per row."""
    for data in ready:
        create_sample(lab=lab, user=user, data=data, request=request, audit=False)
    record(A.SAMPLES_IMPORTED, actor=user, lab=lab, request=request, metadata={"rows": len(ready)})
    return len(ready)


# ---------------------------------------------------------------- storage


def _equipment(lab, data):
    if data.get("equipment") is not None:
        item = InventoryItem.objects.for_lab(lab).filter(pk=data["equipment"]).first()
        if item is None:
            raise ValidationError({"equipment": "This inventory item does not exist."})
        data["equipment"] = item
    return data


def _audit_changes(obj, action, *, user, data, request, extra=None):
    changed = sorted(k for k, v in data.items() if not _same(getattr(obj, k), v))
    for k, v in data.items():
        setattr(obj, k, v)
    if changed:
        obj.save()
        record(
            action,
            actor=user,
            lab=obj.lab,
            target=obj,
            request=request,
            metadata={"changed": changed, **(extra or {})},
        )
    return obj


@transaction.atomic
def create_unit(*, lab, user, data, request=None):
    unit = StorageUnit.objects.create(lab=lab, **_equipment(lab, dict(data)))
    record(A.STORAGE_CREATED, actor=user, lab=lab, target=unit, request=request)
    return unit


@transaction.atomic
def update_unit(unit, *, user, data, request=None):
    data = _equipment(unit.lab, dict(data))
    return _audit_changes(unit, A.STORAGE_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_unit(unit, *, user, request=None):
    if unit.boxes.exists():
        raise Conflict("Move or delete the boxes in it first.")
    record(A.STORAGE_DELETED, actor=user, lab=unit.lab, target=unit, request=request)
    unit.delete()


def _unit(lab, unit_id):
    unit = StorageUnit.objects.for_lab(lab).filter(pk=unit_id).first()
    if unit is None:
        raise ValidationError({"unit": "This freezer or fridge does not exist."})
    return unit


@transaction.atomic
def create_box(*, lab, user, data, request=None):
    data = {**data, "unit": _unit(lab, data["unit"])}
    box = StorageBox.objects.create(lab=lab, **data)
    record(A.STORAGE_CREATED, actor=user, lab=lab, target=box, request=request)
    return box


@transaction.atomic
def update_box(box, *, user, data, request=None):
    data = dict(data)
    if "unit" in data:
        data["unit"] = _unit(box.lab, data["unit"])
    rows, cols = data.get("rows", box.rows), data.get("cols", box.cols)
    if box.tubes.filter(row__gt=rows).exists() or box.tubes.filter(col__gt=cols).exists():
        raise ValidationError({"rows": "Some tubes sit outside that size. Move them first."})
    return _audit_changes(box, A.STORAGE_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_box(box, *, user, request=None):
    if box.tubes.exists():
        raise Conflict("Take the tubes out of this box first.")
    record(A.STORAGE_DELETED, actor=user, lab=box.lab, target=box, request=request)
    box.delete()


def _tube_refs(lab, data):
    """Resolve box, sample and owner ids; check the position fits the box."""
    if "box" in data:
        data["box"] = StorageBox.objects.for_lab(lab).filter(pk=data["box"]).first()
        if data["box"] is None:
            raise ValidationError({"box": "This box does not exist."})
    if "sample" in data:
        data["sample"] = (
            Sample.objects.for_lab(lab).filter(pk=data["sample"], deleted_at__isnull=True).first()
        )
        if data["sample"] is None:
            raise ValidationError({"sample": "This sample does not exist."})
    if "owner" in data:
        data["owner"] = _members_only_owner(lab, data["owner"])
    return data


def _check_spot(box, row, col, exclude=None):
    if row > box.rows or col > box.cols:
        raise ValidationError({"row": f"{box.name} has {box.rows} rows and {box.cols} columns."})
    spot = box.tubes.filter(row=row, col=col)
    if exclude:
        spot = spot.exclude(pk=exclude)
    if spot.exists():
        raise ValidationError({"row": f"{position_label(row, col)} already holds a tube."})


def _lock_box(box):
    """Two people placing into one box at once: the second waits, then sees the first's tube."""
    return StorageBox.objects.for_lab(box.lab_id).select_for_update().get(pk=box.pk)


@transaction.atomic
def place_tube(*, lab, user, data, request=None):
    data = _tube_refs(lab, dict(data))
    data.setdefault("owner", user)
    data["box"] = _lock_box(data["box"])
    _check_spot(data["box"], data["row"], data["col"])
    tube = Tube.objects.create(lab=lab, **data)
    record(
        A.TUBE_PLACED,
        actor=user,
        lab=lab,
        target=tube,
        request=request,
        metadata={"sample": str(tube.sample_id), "box": str(tube.box_id), "at": tube.position},
    )
    return tube


@transaction.atomic
def update_tube(tube, *, user, data, request=None):
    """A new box, row or column is a move; anything else is an edit."""
    data = _tube_refs(tube.lab, dict(data))
    box = _lock_box(data.get("box", tube.box))
    row, col = data.get("row", tube.row), data.get("col", tube.col)
    before = (tube.box.name, tube.position)
    moved = (box.pk, row, col) != (tube.box_id, tube.row, tube.col)
    if moved:
        _check_spot(box, row, col, exclude=tube.pk)
    data["box"] = box
    extra = {"from": " ".join(before), "to": f"{box.name} {position_label(row, col)}"}
    action = A.TUBE_MOVED if moved else A.TUBE_UPDATED
    return _audit_changes(
        tube, action, user=user, data=data, request=request, extra=extra if moved else None
    )


@transaction.atomic
def remove_tube(tube, *, user, request=None):
    record(
        A.TUBE_REMOVED,
        actor=user,
        lab=tube.lab,
        target=tube,
        request=request,
        metadata={"sample": str(tube.sample_id), "box": str(tube.box_id), "at": tube.position},
    )
    tube.delete()
