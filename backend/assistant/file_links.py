"""VISION S1: links for tools on the person's own computer, such as MATLAB run by Claude Desktop.

`GET /api/file-link?token=<secret>` downloads one project file (MATLAB: websave), and
`POST /api/file-link?token=<secret>` with a multipart field "file" uploads one file into a project
(MATLAB: webwrite or matlab.net.http). The AI tools get_file_link and create_upload_link make
them. As with the calendar feed (D231), the token is the only credential, a session cookie does
not stand in for it, and it sits in the query string because nothing logs query strings. Only its
sha256 is stored. A link lasts 15 minutes; an upload link works once.

Every use reads the access of the person who made the link again: they must still be in the lab,
the Claude connection that made the link must still be live and name the lab (a link from the
in-app assistant needs the lab's in-app assistant on), they must still see the file (or edit the
project), and the file must still not be marked "Contains participant data".
"""

import datetime
import secrets
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, views
from rest_framework.exceptions import APIException
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from assistant import privacy
from assistant.models import AIGrant, FileLink, FileLinkKind
from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can, forget, get_lab_or_404, scope, visible_projects
from core.tenancy import by_secret
from documents import services as document_services
from documents.models import Attachment
from labs.models import AiPolicy, hash_token
from projects.activity import _request as activity_request
from provenance import services as provenance_services

TTL = datetime.timedelta(minutes=15)
ASK_AGAIN = "Ask Claude for a new link."


def issue(kind, *, user, project, via, grant_id="", client="", request=None, **targets):
    """Make a link and audit it. The caller has checked access. Returns (link, url)."""
    token = secrets.token_urlsafe(32)
    link = FileLink.objects.create(
        lab=project.lab,
        kind=kind,
        token_hash=hash_token(token),
        created_by=user,
        project=project,
        expires_at=timezone.now() + TTL,
        via=via,
        grant=AIGrant.objects.filter(pk=grant_id).first() if via == "mcp" and grant_id else None,
        **targets,
    )
    record(
        AuditAction.FILE_LINK_CREATED,
        actor=user,
        lab=project.lab,
        target=link.attachment or project,
        request=request,
        metadata={
            "kind": kind,
            "link": str(link.pk),
            "folder": str(link.folder_id) if link.folder_id else None,
            "analysis": str(link.analysis_id) if link.analysis_id else None,
            "expires_at": link.expires_at.isoformat(),
            "via": via,
            "client": client,
        },
    )
    return link, f"{settings.FRONTEND_URL}/api/file-link?token={token}"


class Refused(APIException):
    def __init__(self, code, detail):
        self.status_code = code
        super().__init__(detail)


def _open(request, kind):
    """(link, user, lab) for a usable token of this kind, or Refused."""
    token = request.query_params.get("token") or (
        request.data.get("token", "") if request.method == "POST" else ""
    )
    link = by_secret(FileLink).filter(token_hash=hash_token(str(token))).first()
    if link is None or link.kind != kind:
        raise Refused(401, "This link is not valid. " + ASK_AGAIN)
    if link.expires_at <= timezone.now():
        raise Refused(410, "This link has expired. " + ASK_AGAIN)
    if link.used_at is not None:
        raise Refused(410, "This link has already been used. " + ASK_AGAIN)
    user = link.created_by
    forget(user)  # roles may have changed since the link was made
    try:
        if not user.is_active:
            raise Http404
        lab = get_lab_or_404(user, link.lab_id)
    except Http404:
        raise Refused(404, "This link is no longer available.") from None
    if lab.ai_policy == AiPolicy.OFF:
        raise Refused(403, "This lab has turned AI tools off.")
    if link.via == "in_app":
        if lab.ai_policy != AiPolicy.FULL:
            raise Refused(403, "This lab has turned the in-app assistant off.")
    elif not (link.grant and link.grant.active and link.grant.labs.filter(pk=lab.pk).exists()):
        raise Refused(403, "The Claude connection that made this link has ended. " + ASK_AGAIN)
    return link, user, lab


class FileLinkView(views.APIView):
    authentication_classes = []  # a browser session must not stand in for the token
    perms = {"GET": Perm.PUBLIC, "POST": Perm.PUBLIC}
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "file_links"

    @extend_schema(exclude=True)
    def get(self, request):
        link, user, lab = _open(request, FileLinkKind.DOWNLOAD)
        att = (
            scope(Attachment, user, lab)
            .filter(
                pk=link.attachment_id,
                project=link.project_id,
                project__deleted_at__isnull=True,
                deleted_at__isnull=True,
            )
            .first()
        )
        if att is None or not can(user, Perm.VIEW_PROJECT, att) or att.from_drive:
            raise Refused(404, "This file is no longer available.")
        if privacy.is_flagged(att):
            raise Refused(403, privacy.REFUSAL)
        try:
            handle = document_services.lab_files().open(att.storage_key, "rb")
        except FileNotFoundError:
            raise Refused(404, "This file is no longer available.") from None
        record(
            AuditAction.ATTACHMENT_DOWNLOADED,
            actor=user,
            lab=lab,
            target=att,
            request=request,
            metadata={"via": "file_link", "link": str(link.pk)},
        )
        response = FileResponse(
            handle,
            as_attachment=True,
            filename=att.original_filename,
            content_type=att.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    @extend_schema(exclude=True)
    def post(self, request):
        link, user, lab = _open(request, FileLinkKind.UPLOAD)
        file = request.FILES.get("file")
        if file is None:
            raise Refused(400, 'Send the file as multipart form data in a field named "file".')
        # D139: "last edited" names the link's owner, never a session that came along
        token = activity_request.set(SimpleNamespace(user=user))
        try:
            with transaction.atomic():
                # the lock makes a second upload wait, then see used_at (single use)
                link = FileLink.objects.for_lab(lab).select_for_update().get(pk=link.pk)
                if link.used_at is not None:
                    raise Refused(410, "This link has already been used. " + ASK_AGAIN)
                project = visible_projects(user, lab).filter(pk=link.project_id).first()
                if project is None:
                    raise Refused(404, "This project is no longer available.")
                if not can(user, Perm.EDIT_CONTENT, project):
                    raise Refused(403, "You can no longer add files to this project.")
                att = document_services.upload_attachment(
                    user=user,
                    file=file,
                    project=project,
                    folder=link.folder,
                    request=request,
                    source="link",
                )
                if link.analysis_id:
                    provenance_services.create(
                        "result",
                        project=project,
                        user=user,
                        data={
                            "title": att.original_filename,
                            "analysis": link.analysis_id,
                            "attachments": [att.pk],
                        },
                        request=request,
                    )
                link.used_at = timezone.now()
                link.save(update_fields=["used_at", "updated_at"])
        finally:
            activity_request.reset(token)
        return Response(
            {
                "id": att.pk,
                "name": att.original_filename,
                "size_bytes": att.size_bytes,
                "url": f"{settings.FRONTEND_URL}/labs/{lab.pk}/projects/{project.pk}/documents",
            },
            status=status.HTTP_201_CREATED,
        )
