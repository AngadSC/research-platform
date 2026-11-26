"""Parse a dropped instrument file after the upload has been answered."""

import json

from celery import shared_task
from django.conf import settings

from documents.services import lab_files
from instrument_parsers import parse_file
from instruments.models import InstrumentFile, ParseStatus

MAX_SUMMARY_BYTES = 600 * 1024  # the parsers promise about 500 KB


def _summary(item) -> dict:
    try:
        with lab_files().open(item.attachment.storage_key, "rb") as handle:
            data = handle.read(settings.ATTACHMENT_MAX_BYTES + 1)
    except (FileNotFoundError, OSError):
        return {"status": ParseStatus.FAILED, "error": "The file could not be read."}
    try:
        out = parse_file(data, item.attachment.original_filename, item.software)
        size = len(json.dumps(out).encode())
    except Exception:  # parse_file never raises; a broken parser still must not stay pending
        return {"status": ParseStatus.FAILED, "error": "The file could not be read."}
    if not isinstance(out, dict) or size > MAX_SUMMARY_BYTES:
        return {"status": ParseStatus.FAILED, "error": "The summary was too large to keep."}
    return out


@shared_task(soft_time_limit=180, time_limit=240)
def parse_instrument_file(file_id: str, lab_id: str) -> None:
    item = (
        InstrumentFile.objects.for_lab(lab_id)
        .select_related("attachment")
        .filter(pk=file_id, status=ParseStatus.PENDING)
        .first()
    )
    if item is None:
        return
    summary = _summary(item)
    status = summary.get("status")
    if status not in (ParseStatus.OK, ParseStatus.UNSUPPORTED, ParseStatus.FAILED):
        status = ParseStatus.FAILED
    InstrumentFile.objects.for_lab(lab_id).filter(pk=file_id).update(status=status, summary=summary)
