"""Parse a dropped instrument file after the upload has been answered."""

import datetime
import json
import re

from celery import shared_task
from django.conf import settings
from django.db import DataError, transaction
from django.utils import timezone

from documents.services import lab_files
from instrument_parsers import parse_file
from instruments.models import InstrumentFile, ParseStatus
from labs.models import Lab

MAX_SUMMARY_BYTES = 600 * 1024  # the parsers promise about 500 KB
STUCK_AFTER = datetime.timedelta(minutes=10)
NOT_IN_TIME = "We could not read this file in time."
_UNSTORABLE = re.compile("[\x00\ud800-\udfff]")  # Postgres jsonb refuses NUL and lone surrogates


def _clean(value):
    """The summary is made from a file's own content: strip what Postgres cannot store."""
    if isinstance(value, str):
        return _UNSTORABLE.sub("", value)
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {_clean(k): _clean(v) for k, v in value.items()}
    return value


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


# Its own queue ("parsing"): a parser child may use 1 GB, so a flood of drops must queue up
# behind a small dedicated worker, not behind email and alerts.
@shared_task(queue="parsing", soft_time_limit=180, time_limit=240)
def parse_instrument_file(file_id: str, lab_id: str) -> None:
    item = (
        InstrumentFile.objects.for_lab(lab_id)
        .select_related("attachment")
        .filter(pk=file_id, status=ParseStatus.PENDING)
        .first()
    )
    if item is None:
        return
    summary = _clean(_summary(item))
    status = summary.get("status")
    if status not in (ParseStatus.OK, ParseStatus.UNSUPPORTED, ParseStatus.FAILED):
        status = ParseStatus.FAILED
    rows = InstrumentFile.objects.for_lab(lab_id).filter(pk=file_id)
    try:
        with transaction.atomic():
            rows.update(status=status, summary=summary)
    except DataError:  # never stay "pending": the page would wait for ever
        rows.update(
            status=ParseStatus.FAILED,
            summary={"status": "failed", "error": "The file could not be read."},
        )


@shared_task
def fail_stuck_files() -> None:
    """A parse that never finished (worker down, task killed) must not leave the page waiting."""
    cutoff = timezone.now() - STUCK_AFTER
    for lab in Lab.objects.all():
        InstrumentFile.objects.for_lab(lab).filter(
            status=ParseStatus.PENDING, created_at__lt=cutoff
        ).update(status=ParseStatus.FAILED, summary={"status": "failed", "error": NOT_IN_TIME})
