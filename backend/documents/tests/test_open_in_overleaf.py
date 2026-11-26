"""D380: Open in Overleaf hands Overleaf a 5-minute link to one .tex or .zip file."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents.models import Attachment, Folder
from documents.tests.test_documents import url
from labs.models import LabRole

pytestmark = pytest.mark.django_db
TEX = rb"\documentclass{article}\begin{document}Hi\end{document}"


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    lab = make_lab()
    user = make_user()
    join(user, lab, LabRole.PI)
    c = APIClient()
    c.force_login(user)
    return lab, make_project(lab), c


def zipped(*names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return buf.getvalue()


def marked_folder(w):
    lab, project, c = w
    return Folder.objects.create(
        lab=lab,
        project=project,
        name="P",
        contains_participant_data=True,
        created_by=project.created_by,
    )


def make(w, name="paper.tex", data=TEX, folder=None):
    lab, project, c = w
    body = {"file": SimpleUploadedFile(name, data), "acknowledged_notice": "true"}
    if folder:
        body["folder"] = folder
    r = c.post(url("attachment-list", lab, project_id=project.pk), body, format="multipart")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def call(w, att):
    lab, _, c = w
    return c.post(url("attachment-open-in-overleaf", lab, attachment_id=att))


def test_link_downloads_exactly_that_file_and_is_audited(w):
    att = make(w)
    other = make(w, "other.tex")
    r = call(w, att)
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["name"] == "paper.tex" and "/api/file-link?token=" in body["url"]
    token = body["url"].split("token=")[1]
    got = APIClient().get("/api/file-link", {"token": token})  # no session: the token alone
    assert got.status_code == 200 and b"".join(got.streaming_content) == TEX
    assert (
        AuditEvent.objects.get(action=AuditAction.FILE_LINK_CREATED).metadata["via"] == "overleaf"
    )
    assert (
        AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=att).metadata[
            "via"
        ]
        == "overleaf"
    )
    assert not AuditEvent.objects.filter(
        action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=other
    ).exists()


def test_link_expires_in_five_minutes(w):
    from datetime import timedelta

    from assistant.models import FileLink

    call(w, make(w))
    link = FileLink.objects.for_lab(w[0].pk).get()
    assert link.expires_at - link.created_at <= timedelta(minutes=5, seconds=5)


def test_zip_needs_latex_inside(w):
    assert call(w, make(w, "p.zip", zipped("main.tex", "fig.png"))).status_code == 200
    r = call(w, make(w, "q.zip", zipped("a.png")))
    assert r.status_code == 400 and "no LaTeX" in r.json()["file"]


def test_other_file_types_refused(w):
    assert call(w, make(w, "a.csv", b"a,b\n1,2\n")).status_code == 400


@pytest.mark.parametrize("where", ["file", "folder"])
def test_participant_data_never_gets_a_link(w, where):
    from assistant.models import FileLink

    lab, project, c = w
    att = make(w)
    if where == "file":
        Attachment.objects.for_lab(lab.pk).filter(pk=att).update(contains_participant_data=True)
    else:
        att = make(w, folder=str(marked_folder(w).pk))
    r = call(w, att)
    assert r.status_code == 400 and "identifies participants" in r.json()["file"]
    assert not FileLink.objects.for_lab(lab.pk).exists()


def test_marking_after_the_link_was_made_blocks_the_download(w):
    lab, _, _ = w
    att = make(w)
    token = call(w, att).json()["url"].split("token=")[1]
    Attachment.objects.for_lab(lab.pk).filter(pk=att).update(contains_participant_data=True)
    assert APIClient().get("/api/file-link", {"token": token}).status_code == 403
