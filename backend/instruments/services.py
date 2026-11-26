"""Instrument files and drop links. Callers have checked access; these write the rows, file the
upload under "Instrument data" > instrument, queue the parse, and audit."""

import mimetypes
import secrets

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can, drop_links_of, forget
from documents import services as document_services
from documents.models import Folder
from instruments import jobs
from instruments.models import InstrumentDropLink, InstrumentFile, UploadedVia
from labs.models import hash_token
from projects.models import Project

FOLDER_NAME = "Instrument data"


def _instrument_folder(project, instrument, user) -> Folder:
    """ "Instrument data" > "<instrument name>" at the project's top level, made if missing. The
    project row lock makes two drops at once find the same folders instead of making two."""
    Project.objects.for_lab(project.lab_id).select_for_update().get(pk=project.pk)
    folders = Folder.objects.for_lab(project.lab_id).filter(project=project)
    top = folders.filter(parent__isnull=True, name=FOLDER_NAME).order_by("created_at").first()
    if top is None:
        top = document_services.create_folder(project=project, user=user, name=FOLDER_NAME)
    name = instrument.name[:200]
    sub = folders.filter(parent=top, name=name).order_by("created_at").first()
    return sub or document_services.create_folder(project=project, user=user, name=name, parent=top)


def _content_type(file) -> str:
    """Never the browser's word for it: the type follows the name, and a "PDF" (the only type
    shown inline) must start like one."""
    guessed = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    if guessed == "application/pdf":
        head = file.read(5)
        file.seek(0)
        if head != b"%PDF-":
            guessed = "application/octet-stream"
    return guessed


def drop_file(
    *, instrument, project, user, file, via, flag=False, link=None, request=None
) -> InstrumentFile:
    """Store `file` as a project attachment by `user` (a link's maker, for a link) and record
    it as this instrument's. The parse runs after commit and never holds up the upload."""
    file.content_type = _content_type(file)
    with transaction.atomic():  # short: the project lock is not held while the bytes are written
        folder = _instrument_folder(project, instrument, user)
    with transaction.atomic():
        att = document_services.upload_attachment(
            user=user,
            file=file,
            project=project,
            folder=folder,
            request=request,
            contains_participant_data=flag,
        )
        item = InstrumentFile.objects.create(
            lab=project.lab,
            instrument=instrument,
            attachment=att,
            project=project,
            software=instrument.instrument_software,
            uploaded_via=via,
            dropped_by=user if via == UploadedVia.PAGE else None,
        )
        if link is not None:
            InstrumentDropLink.objects.for_lab(link.lab_id).filter(pk=link.pk).update(
                last_used_at=timezone.now()
            )
            record(
                AuditAction.INSTRUMENT_DROP_LINK_USED,
                actor=None,
                actor_label="instrument drop link",
                lab=project.lab,
                target=link,
                request=request,
                metadata={"attachment": str(att.pk), "made_by": str(link.created_by_id)},
            )
        transaction.on_commit(
            lambda: jobs.parse_instrument_file.delay(str(item.pk), str(item.lab_id)), robust=True
        )
    return item


def issue_link(*, instrument, project, user, label="", expires_at=None, request=None):
    """Returns (link, token). Only the token's hash is kept, so this is the one time it exists."""
    token = secrets.token_urlsafe(32)
    with transaction.atomic():
        link = InstrumentDropLink.objects.create(
            lab=project.lab,
            instrument=instrument,
            project=project,
            created_by=user,
            label=label,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
        record(
            AuditAction.INSTRUMENT_DROP_LINK_CREATED,
            actor=user,
            lab=project.lab,
            target=link,
            request=request,
            metadata={
                "instrument": instrument.name,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
    return link, token


def revoke_link(link, *, by, reason="", request=None) -> None:
    """Idempotent: an already revoked link is left as it is."""
    with transaction.atomic():
        done = (
            InstrumentDropLink.objects.for_lab(link.lab_id)
            .filter(pk=link.pk, revoked_at__isnull=True)
            .update(revoked_at=timezone.now())
        )
        if done:
            record(
                AuditAction.INSTRUMENT_DROP_LINK_REVOKED,
                actor=by,
                actor_label="" if by else "system",
                lab=link.lab,
                target=link,
                request=request,
                metadata={"reason": reason} if reason else {},
            )


def revoke_lost_links(user, *, lab, by=None, reason, request=None) -> None:
    """After an access change: end `user`'s live links into projects they can no longer add
    files to (left the lab or the project, lost the role, deactivated). Use re-checks too."""
    forget(user)
    links = InstrumentDropLink.objects.for_lab(lab).filter(created_by=user, revoked_at__isnull=True)
    for link in links.select_related("project", "lab"):
        if not can(user, Perm.EDIT_CONTENT, link.project):
            revoke_link(link, by=by, reason=reason, request=request)


def revoke_all_links(user, *, reason, request=None) -> None:
    """A security event (password change or reset, TOTP removed, deactivation) ends every link
    the person made, as with calendar feeds (D231): a leaked link is what those events stop."""
    for link in drop_links_of(user).select_related("lab"):
        revoke_link(link, by=None, reason=reason, request=request)
