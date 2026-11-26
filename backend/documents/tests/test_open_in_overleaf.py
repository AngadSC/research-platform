"""D388: Open in Overleaf hands Overleaf a 5-minute link to one .tex or .zip file."""

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


def test_huge_zips_are_not_opened_up_to_look_inside(w, monkeypatch):
    """O1: a zip with thousands of entries, or over 20 MB, is never listed; no 500, no big read."""
    many = make(w, "many.zip", zipped(*[f"f{i}.png" for i in range(5001)]))
    big = make(w, "big.zip", zipped("a.png"))
    Attachment.objects.for_lab(w[0].pk).filter(pk=big).update(size_bytes=21 * 1024 * 1024)
    small = make(w, "small.zip", zipped("a.png"))
    real = zipfile.ZipFile
    listed = []
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: listed.append(1) or real(*a, **k))
    assert call(w, many).status_code == 200
    assert call(w, big).status_code == 200
    assert listed == []
    assert call(w, small).status_code == 400  # a small zip is still checked
    assert listed == [1]


@pytest.mark.parametrize("error", [zipfile.BadZipFile, ValueError, UnicodeDecodeError])
def test_a_zip_that_cannot_be_read_is_a_plain_refusal(w, monkeypatch, error):
    """O1: a broken zip, or odd file names, is the normal 'no LaTeX' answer, not a 500."""
    exc = error("x", b"x", 0, 1, "bad") if error is UnicodeDecodeError else error("bad")
    good = make(w, "p.zip", zipped("main.tex"))
    junk = make(w, "junk.zip", b"not a zip at all")

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(zipfile, "ZipFile", boom)
    r = call(w, good)
    assert r.status_code == 400 and "no LaTeX" in r.json()["file"]
    r = call(w, junk)
    assert r.status_code == 400 and "no LaTeX" in r.json()["file"]


def test_drive_and_office_copies_are_refused(w):
    """O3: a copy that lives in Drive or OneDrive has no bytes here to send."""
    lab, _, _ = w
    att = make(w)
    Attachment.objects.for_lab(lab.pk).filter(pk=att).update(
        external_url="https://contoso-my.sharepoint.com/x/paper.tex"
    )
    assert call(w, att).status_code == 400
