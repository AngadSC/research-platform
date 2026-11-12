"""Participant data and AI (VISION A3, SPEC section 1). The one place that decides what AI tools
may see: every tool in assistant/tools.py (the in-app assistant and the MCP server) goes through
`ai_visible` for lists and search and `is_flagged` for an item asked for by id.

An item counts as flagged when its own "Contains participant data" box is ticked, or when it sits
directly in a folder that is (so moving a file into a flagged folder hides it at once). A Google
copy of a file counts as flagged when the original is.
"""

from django.db import transaction
from django.db.models import Q

from audit.models import AuditAction
from audit.services import record
from documents.models import Attachment, Document, Folder
from provenance.models import DatasetRecord

REFUSAL = "This item contains participant data, so AI tools cannot open it."

# model -> the folder field that also counts (None: the item's own box only)
_CONTAINER = {Folder: "parent", Document: "folder", Attachment: "folder", DatasetRecord: None}

_CHANGED = {
    Folder: AuditAction.FOLDER_PARTICIPANT_FLAG_CHANGED,
    Document: AuditAction.DOCUMENT_PARTICIPANT_FLAG_CHANGED,
    Attachment: AuditAction.ATTACHMENT_PARTICIPANT_FLAG_CHANGED,
    DatasetRecord: AuditAction.DATASET_PARTICIPANT_FLAG_CHANGED,
}


def _flagged_q(model) -> Q:
    q = Q(contains_participant_data=True)
    if container := _CONTAINER[model]:
        q |= Q(**{f"{container}__contains_participant_data": True})
    if model is Attachment:  # a Google copy follows the upload it was made from
        q |= Q(copied_from__contains_participant_data=True)
    return q


def ai_visible(qs):
    """`qs` without flagged items. Any other model passes through unchanged."""
    return qs.exclude(_flagged_q(qs.model)) if qs.model in _CONTAINER else qs


def is_flagged(obj) -> bool:
    """True if AI tools must refuse `obj`. False for kinds that cannot carry the flag."""
    if type(obj) not in _CONTAINER:
        return False
    container = _CONTAINER[type(obj)]
    parent = getattr(obj, container) if container else None
    if obj.contains_participant_data or (parent and parent.contains_participant_data):
        return True
    original = getattr(obj, "copied_from", None) if isinstance(obj, Attachment) else None
    return bool(original and original.contains_participant_data)


@transaction.atomic
def set_flag(obj, value: bool, *, user, request=None):
    """Tick or clear the box on a folder, document, file or dataset, with an audit event. The
    caller has checked the person may edit `obj`. Ticking a folder ticks everything inside it,
    all the way down; clearing it leaves the contents as they are."""
    old = obj.contains_participant_data
    if old == value:
        return obj
    obj.contains_participant_data = value
    obj.save(update_fields=["contains_participant_data", "updated_at"])
    metadata = {"old": old, "new": value}
    if value and isinstance(obj, Folder):
        metadata["items_flagged"] = _flag_contents(obj)
    record(
        _CHANGED[type(obj)], actor=user, lab=obj.lab, target=obj, request=request, metadata=metadata
    )
    return obj


def _flag_contents(folder) -> int:
    """Flag every folder, document and file under `folder`. Returns how many changed."""
    folders = Folder.objects.for_lab(folder.lab_id)
    ids, frontier = [folder.pk], [folder.pk]
    while frontier:  # the folder tree has no cycles, so this always ends
        frontier = list(folders.filter(parent__in=frontier).values_list("pk", flat=True))
        ids += frontier
    n = folders.filter(pk__in=ids, contains_participant_data=False).update(
        contains_participant_data=True
    )
    for model in (Document, Attachment):
        n += (
            model.objects.for_lab(folder.lab_id)
            .filter(folder__in=ids, contains_participant_data=False)
            .update(contains_participant_data=True)
        )
    return n
