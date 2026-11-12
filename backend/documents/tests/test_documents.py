import hashlib
import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents import embed
from documents.models import Attachment, Document, DocumentRevision, Folder
from labs.models import LabRole
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db

BLOCKS = [{"type": "paragraph", "content": "hello"}]
PDF = b"%PDF-1.4 tiny"


@pytest.fixture
def setup(make_lab, make_user, make_project, join):
    lab = make_lab("Lab A")
    user = make_user()
    join(user, lab, LabRole.PI)
    project = make_project(lab)
    client = APIClient()
    client.force_login(user)
    return lab, user, project, client


def url(name, lab, **kw):
    return reverse(f"documents:{name}", kwargs={"lab_id": lab.pk, **kw})


def make_doc(client, lab, project, content=BLOCKS):
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "T", "content": content},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def put(client, lab, doc_id, version, content=BLOCKS, title="T"):
    return client.put(
        url("document-detail", lab, document_id=doc_id),
        {"title": title, "content": content, "base_version": version},
        format="json",
    )


def upload(client, lab, project, *, ack="true", data=PDF, name="a.pdf", ctype="application/pdf"):
    body = {"file": SimpleUploadedFile(name, data, content_type=ctype)}
    if ack is not None:
        body["acknowledged_notice"] = ack
    return client.post(url("attachment-list", lab, project_id=project.pk), body, format="multipart")


# ---------------------------------------------------------------- documents


def test_create_writes_revision_one(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    assert doc["version"] == 1
    revs = client.get(url("revision-list", lab, document_id=doc["id"])).json()
    assert [r["version"] for r in revs] == [1]


def test_stale_save_returns_409_with_who_and_when(setup, make_user, join):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    other = make_user(display_name="Other Person")
    join(other, lab, LabRole.PI)
    other_client = APIClient()
    other_client.force_login(other)
    assert put(other_client, lab, doc["id"], 1, [{"type": "heading"}]).status_code == 200
    resp = put(client, lab, doc["id"], 1)  # still on version 1
    assert resp.status_code == 409
    body = resp.json()
    assert body["current_version"] == 2
    assert body["updated_by"]["display_name"] == "Other Person"
    assert body["updated_at"]
    assert Document.objects.for_lab(lab).get(pk=doc["id"]).content == [{"type": "heading"}]


def test_put_requires_base_version(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    resp = client.put(
        url("document-detail", lab, document_id=doc["id"]),
        {"title": "T", "content": BLOCKS},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("content", ["text", {"a": 1}, [1, 2], [{"a": 1}, "x"]])
def test_content_must_be_array_of_objects(setup, content):
    lab, _, project, client = setup
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "T", "content": content},
        format="json",
    )
    assert resp.status_code == 400


def test_content_size_cap(setup):
    lab, _, project, client = setup
    big = [{"type": "paragraph", "content": "x" * (1024 * 1024)}]
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "T", "content": big},
        format="json",
    )
    assert resp.status_code == 400


def test_restore_creates_new_revision_and_keeps_history(setup):
    lab, user, project, client = setup
    first = [{"type": "paragraph", "content": "first"}]
    second = [{"type": "paragraph", "content": "second"}]
    doc = make_doc(client, lab, project, first)
    assert put(client, lab, doc["id"], 1, second).status_code == 200
    resp = client.post(url("revision-restore", lab, document_id=doc["id"], version=1))
    assert resp.status_code == 200
    assert resp.json()["version"] == 3
    assert resp.json()["content"] == first
    revs = client.get(url("revision-list", lab, document_id=doc["id"])).json()
    assert [r["version"] for r in revs] == [3, 2, 1]
    assert revs[0]["restored_from_version"] == 1
    old = client.get(url("revision-detail", lab, document_id=doc["id"], version=2)).json()
    assert old["content"] == second  # history untouched
    event = AuditEvent.objects.get(lab=lab, action=AuditAction.DOCUMENT_RESTORED)
    assert event.actor == user and event.metadata == {"restored_version": 1, "new_version": 3}


def test_soft_deleted_document_is_404_everywhere(setup):
    lab, user, project, client = setup
    doc = make_doc(client, lab, project)
    assert client.delete(url("document-detail", lab, document_id=doc["id"])).status_code == 204
    assert client.get(url("document-detail", lab, document_id=doc["id"])).status_code == 404
    assert put(client, lab, doc["id"], 1).status_code == 404
    assert client.get(url("revision-list", lab, document_id=doc["id"])).status_code == 404
    assert client.get(url("document-list", lab, project_id=project.pk)).json() == []
    row = Document.objects.for_lab(lab).get(pk=doc["id"])  # row and revisions are kept
    assert row.deleted_at is not None and row.revisions.count() == 1
    assert (
        AuditEvent.objects.filter(lab=lab, action=AuditAction.DOCUMENT_DELETED, actor=user).count()
        == 1
    )


def test_document_view_writes_audit_event(setup):
    lab, user, project, client = setup
    doc = make_doc(client, lab, project)
    assert not AuditEvent.objects.filter(lab=lab, action=AuditAction.DOCUMENT_VIEWED).exists()
    assert client.get(url("document-detail", lab, document_id=doc["id"])).status_code == 200
    event = AuditEvent.objects.get(lab=lab, action=AuditAction.DOCUMENT_VIEWED)
    assert (event.actor, event.lab, str(event.target_id)) == (user, lab, doc["id"])
    assert event.project_id == project.pk


def test_forbidden_view_writes_no_audit_event(setup, make_user, join):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    member = make_user()
    join(member, lab, LabRole.MEMBER)  # not on the project: invisible
    other = APIClient()
    other.force_login(member)
    assert other.get(url("document-detail", lab, document_id=doc["id"])).status_code == 404
    assert not AuditEvent.objects.filter(lab=lab, action=AuditAction.DOCUMENT_VIEWED).exists()


# ---------------------------------------------------------------- attachments


def test_upload_requires_acknowledgment(setup):
    lab, _, project, client = setup
    for ack in (None, "false"):
        resp = upload(client, lab, project, ack=ack)
        assert resp.status_code == 400
        assert "acknowledge" in str(resp.json()["acknowledged_notice"]).lower()
    assert not Attachment.objects.for_lab(lab).exists()


def test_upload_stores_under_lab_prefix_and_audits(setup, lab_files):
    lab, _, project, client = setup
    resp = upload(client, lab, project)
    assert resp.status_code == 201, resp.content
    att = Attachment.objects.for_lab(lab).get(pk=resp.json()["id"])
    assert att.storage_key == f"labs/{lab.pk}/attachments/{att.pk}"
    assert att.sha256 == hashlib.sha256(PDF).hexdigest() and att.size_bytes == len(PDF)
    assert att.notice_acknowledged_at is not None
    assert lab_files.exists(att.storage_key)
    event = AuditEvent.objects.get(lab=lab, action=AuditAction.ATTACHMENT_UPLOADED)
    assert event.target_id == att.pk and event.metadata["notice_acknowledged_at"]


def test_client_cannot_choose_storage_key(setup):
    lab, _, project, client = setup
    body = {
        "file": SimpleUploadedFile("a.pdf", PDF),
        "acknowledged_notice": "true",
        "storage_key": "labs/other/attachments/x",
    }
    resp = client.post(url("attachment-list", lab, project_id=project.pk), body, format="multipart")
    key = Attachment.objects.for_lab(lab).get(pk=resp.json()["id"]).storage_key
    assert key.startswith(f"labs/{lab.pk}/")


def test_oversize_upload_rejected(setup, settings):
    lab, _, project, client = setup
    settings.ATTACHMENT_MAX_BYTES = 10
    resp = upload(client, lab, project, data=b"x" * 11)
    assert resp.status_code == 413  # D53: rejected while streaming, same status as the middleware
    assert not Attachment.objects.for_lab(lab).exists()


def test_download_headers_pdf_inline(setup):
    lab, user, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == PDF
    assert resp["Content-Disposition"].startswith("inline")
    assert resp["Content-Type"] == "application/pdf"
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Content-Security-Policy"] == "sandbox"
    assert resp["Cache-Control"] == "private, no-store"
    event = AuditEvent.objects.get(lab=lab, action=AuditAction.ATTACHMENT_DOWNLOADED)
    assert event.actor == user and str(event.target_id) == att_id


def test_download_other_types_are_attachments(setup):
    lab, _, project, client = setup
    att_id = upload(
        client, lab, project, data=b"<script>1</script>", name="x.html", ctype="text/html"
    ).json()["id"]
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp["Content-Disposition"].startswith("attachment")
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Content-Security-Policy"] == "sandbox"


def test_every_download_is_audited(setup):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    for _ in range(2):
        client.get(url("attachment-download", lab, attachment_id=att_id))
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.ATTACHMENT_DOWNLOADED).count() == 2


def test_downloading_a_pi_only_file_stays_out_of_file_events(setup):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    Attachment.objects.for_lab(lab).filter(pk=att_id).update(pi_only=True)  # D244
    assert client.get(url("attachment-download", lab, attachment_id=att_id)).status_code == 200
    assert not AuditEvent.objects.filter(lab=lab, action=AuditAction.ATTACHMENT_DOWNLOADED).exists()
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.FUNDING_UPDATED).exists()


def test_attachment_delete_is_soft_and_keeps_bytes(setup, lab_files):
    lab, user, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    key = Attachment.objects.for_lab(lab).get(pk=att_id).storage_key
    assert client.delete(url("attachment-detail", lab, attachment_id=att_id)).status_code == 204
    assert client.get(url("attachment-detail", lab, attachment_id=att_id)).status_code == 404
    assert client.get(url("attachment-download", lab, attachment_id=att_id)).status_code == 404
    assert client.get(url("attachment-list", lab, project_id=project.pk)).json() == []
    assert Attachment.objects.for_lab(lab).get(pk=att_id).deleted_at is not None
    assert lab_files.exists(key)
    assert (
        AuditEvent.objects.filter(
            lab=lab, action=AuditAction.ATTACHMENT_DELETED, actor=user
        ).count()
        == 1
    )


def test_project_viewer_can_download_but_not_upload(setup, make_user, join):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    viewer = make_user()
    join(viewer, lab, LabRole.MEMBER)
    ProjectMembership.objects.create(lab=lab, project=project, user=viewer, role=ProjectRole.VIEWER)
    vc = APIClient()
    vc.force_login(viewer)
    assert vc.get(url("attachment-download", lab, attachment_id=att_id)).status_code == 200
    assert upload(vc, lab, project).status_code == 403


def test_media_url_does_not_expose_files(setup, settings):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    key = Attachment.objects.for_lab(lab).get(pk=att_id).storage_key
    anon = APIClient()  # nothing is mounted under MEDIA_URL, static or any file prefix
    for prefix in (settings.MEDIA_URL, "/media/", "/static/", "/files/", "/data/lab_files/"):
        assert anon.get(f"{prefix.rstrip('/')}/{key}").status_code == 404


# ---------------------------------------------------------------- autosave


def autosave(client, lab, doc_id, version, content=BLOCKS, title="T"):
    return client.put(
        url("document-detail", lab, document_id=doc_id),
        {"title": title, "content": content, "base_version": version, "autosave": True},
        format="json",
    )


def revisions(client, lab, doc_id):
    return client.get(url("revision-list", lab, document_id=doc_id)).json()


def test_autosave_folds_into_own_recent_revision_and_bumps_version(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)  # revision 1, by this user, just now
    resp = autosave(client, lab, doc["id"], 1, [{"type": "heading"}], title="New")
    assert resp.status_code == 200 and resp.json()["version"] == 2
    assert resp.json()["title"] == "New" and resp.json()["content"] == [{"type": "heading"}]
    revs = revisions(client, lab, doc["id"])
    assert [r["version"] for r in revs] == [2]  # moved to the new version, unique constraint held
    latest = client.get(url("revision-detail", lab, document_id=doc["id"], version=2)).json()
    assert latest["content"] == [{"type": "heading"}] and latest["title"] == "New"


def test_autosave_chain_keeps_one_revision_and_conflicts_like_any_save(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    assert autosave(client, lab, doc["id"], 1).json()["version"] == 2
    assert autosave(client, lab, doc["id"], 2).json()["version"] == 3
    assert [r["version"] for r in revisions(client, lab, doc["id"])] == [3]
    assert autosave(client, lab, doc["id"], 2).status_code == 409  # stale


def test_manual_save_always_creates_a_revision(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    assert put(client, lab, doc["id"], 1).status_code == 200
    assert [r["version"] for r in revisions(client, lab, doc["id"])] == [2, 1]


def test_autosave_makes_a_new_revision_after_the_window(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    DocumentRevision.objects.for_lab(lab).filter(document_id=doc["id"]).update(
        created_at=timezone.now() - timedelta(minutes=16)
    )
    assert autosave(client, lab, doc["id"], 1).status_code == 200
    assert [r["version"] for r in revisions(client, lab, doc["id"])] == [2, 1]


def test_autosave_makes_a_new_revision_when_someone_else_wrote_the_latest(setup, make_user, join):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)  # by client's user
    other = make_user()
    join(other, lab, LabRole.PI)
    other_client = APIClient()
    other_client.force_login(other)
    assert autosave(other_client, lab, doc["id"], 1).status_code == 200
    assert [r["version"] for r in revisions(client, lab, doc["id"])] == [2, 1]


def test_autosave_never_rewrites_a_restore(setup):
    lab, _, project, client = setup
    doc = make_doc(client, lab, project)
    assert put(client, lab, doc["id"], 1, [{"type": "heading"}]).status_code == 200
    restore = url("revision-restore", lab, document_id=doc["id"], version=1)
    assert client.post(restore).status_code == 200  # version 3, restored_from revision 1
    assert autosave(client, lab, doc["id"], 3).status_code == 200
    revs = revisions(client, lab, doc["id"])
    assert [r["version"] for r in revs] == [4, 3, 2, 1]
    assert revs[1]["restored_from_version"] == 1


# ---------------------------------------------------------------- folders


def folder_url(lab, **kw):
    if "folder_id" in kw:
        return url("folder-detail", lab, **kw)
    return url("folder-list", lab, **kw)


def make_folder(client, lab, project, name="F", parent=None):
    resp = client.post(
        folder_url(lab, project_id=project.pk),
        {"name": name, "parent": str(parent) if parent else None},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def move(client, lab, kind, item_id, folder_id):
    return client.post(
        url(f"{kind}-move", lab, **{f"{kind}_id": item_id}),
        {"folder": str(folder_id) if folder_id else None},
        format="json",
    )


def test_folder_tree_and_moves(setup, lab_files):
    lab, _, project, client = setup
    top = make_folder(client, lab, project, "Top")
    sub = make_folder(client, lab, project, "Sub", parent=top["id"])
    assert sub["parent"] == top["id"]
    doc = make_doc(client, lab, project)
    attachment = upload(client, lab, project).json()
    assert move(client, lab, "document", doc["id"], sub["id"]).status_code == 204
    assert move(client, lab, "attachment", attachment["id"], top["id"]).status_code == 204
    docs = client.get(url("document-list", lab, project_id=project.pk)).json()
    assert docs[0]["folder"] == sub["id"]
    files = client.get(url("attachment-list", lab, project_id=project.pk)).json()
    assert files[0]["folder"] == top["id"]
    assert move(client, lab, "document", doc["id"], None).status_code == 204  # back to the top
    resp = client.patch(folder_url(lab, folder_id=sub["id"]), {"name": "Renamed"}, format="json")
    assert resp.status_code == 200 and resp.json()["name"] == "Renamed"
    assert resp.json()["parent"] == top["id"]  # never re-parented


def test_delete_folder_lifts_contents_and_children_to_its_parent(setup, lab_files):
    lab, _, project, client = setup
    top = make_folder(client, lab, project, "Top")
    mid = make_folder(client, lab, project, "Mid", parent=top["id"])
    deep = make_folder(client, lab, project, "Deep", parent=mid["id"])
    doc = make_doc(client, lab, project)
    attachment = upload(client, lab, project).json()
    move(client, lab, "document", doc["id"], mid["id"])
    move(client, lab, "attachment", attachment["id"], mid["id"])
    assert client.delete(folder_url(lab, folder_id=mid["id"])).status_code == 204
    top_id = uuid.UUID(top["id"])
    assert Folder.objects.for_lab(lab).get(pk=deep["id"]).parent_id == top_id
    assert Document.objects.for_lab(lab).get(pk=doc["id"]).folder_id == top_id
    assert Attachment.objects.for_lab(lab).get(pk=attachment["id"]).folder_id == top_id
    # A top-level folder hands its contents to the project's top level, not to nowhere.
    assert client.delete(folder_url(lab, folder_id=top["id"])).status_code == 204
    assert Document.objects.for_lab(lab).get(pk=doc["id"]).folder_id is None
    assert Folder.objects.for_lab(lab).get(pk=deep["id"]).parent_id is None


def test_a_folder_of_another_project_is_refused(setup, make_project, lab_files):
    lab, user, project, client = setup
    other = make_project(lab, "Other")
    theirs = Folder.objects.create(lab=lab, project=other, name="T", created_by=user)
    doc = make_doc(client, lab, project)
    attachment = upload(client, lab, project).json()
    assert move(client, lab, "document", doc["id"], theirs.pk).status_code == 400
    assert move(client, lab, "attachment", attachment["id"], theirs.pk).status_code == 400
    resp = client.post(
        folder_url(lab, project_id=project.pk),
        {"name": "x", "parent": str(theirs.pk)},
        format="json",
    )
    assert resp.status_code == 400
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "x", "folder": str(theirs.pk)},
        format="json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------- embeds

GOOGLE_ID = "195j9eDD3ccgjQRttHhJPymLJUCOUjs-jmwTrekvdjFE"


@pytest.mark.parametrize(
    ("pasted", "frame", "opener"),
    [
        (
            f"https://docs.google.com/document/d/{GOOGLE_ID}/edit?usp=sharing",
            f"https://docs.google.com/document/d/{GOOGLE_ID}/preview",
            f"https://docs.google.com/document/d/{GOOGLE_ID}/edit",
        ),
        (
            f"https://docs.google.com/spreadsheets/u/1/d/{GOOGLE_ID}/edit#gid=0",
            f"https://docs.google.com/spreadsheets/d/{GOOGLE_ID}/preview",
            f"https://docs.google.com/spreadsheets/d/{GOOGLE_ID}/edit",
        ),
        (
            f"https://docs.google.com/presentation/d/{GOOGLE_ID}",
            f"https://docs.google.com/presentation/d/{GOOGLE_ID}/preview",
            f"https://docs.google.com/presentation/d/{GOOGLE_ID}/edit",
        ),
        (
            "https://view.officeapps.live.com/op/view.aspx?src=https://x.org/a.docx",
            "https://view.officeapps.live.com/op/embed.aspx?src=https%3A%2F%2Fx.org%2Fa.docx",
            "https://view.officeapps.live.com/op/view.aspx?src=https%3A%2F%2Fx.org%2Fa.docx",
        ),
        (
            "https://onedrive.live.com/edit.aspx?resid=ABC!123&authkey=zzz",
            "https://onedrive.live.com/embed?resid=ABC%21123&em=2&authkey=zzz",
            "https://onedrive.live.com/edit.aspx?resid=ABC!123&authkey=zzz",
        ),
        (
            "https://uni.sharepoint.com/:w:/g/personal/ada/Eabc?e=xy1",
            "https://uni.sharepoint.com/:w:/g/personal/ada/Eabc?e=xy1&action=embedview",
            "https://uni.sharepoint.com/:w:/g/personal/ada/Eabc?e=xy1",
        ),
    ],
)
def test_embed_links_normalise(pasted, frame, opener):
    assert embed.normalise(pasted) == (frame, opener)


@pytest.mark.parametrize(
    "bad",
    [
        f"http://docs.google.com/document/d/{GOOGLE_ID}/edit",  # not https
        f"https://user@docs.google.com/document/d/{GOOGLE_ID}/edit",  # userinfo
        f"https://docs.google.com:8443/document/d/{GOOGLE_ID}/edit",  # odd port
        f"https://docs.google.com.evil.org/document/d/{GOOGLE_ID}/edit",  # lookalike host
        f"https://evilsharepoint.com/document/d/{GOOGLE_ID}/edit",
        "https://docs.google.com/document/d/e/2PACX-abc/pub",  # published, not a share link
        "https://docs.google.com/forms/d/x/viewform",  # not a kind we embed
        "https://1drv.ms/w/s!Abc",  # short links need resolving
        "https://onedrive.live.com/about",  # no file id
        "https://view.officeapps.live.com/op/embed.aspx?src=http://x.org/a.docx",  # http file
        "https://uni.sharepoint.com/",
        "javascript:alert(1)",
        "https://example.com/x",
    ],
)
def test_embed_links_refused(bad):
    with pytest.raises(ValidationError):
        embed.normalise(bad)


def test_embedded_document_stores_frame_and_open_urls(setup):
    lab, _, project, client = setup
    pasted = f"https://docs.google.com/document/d/{GOOGLE_ID}/edit"
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "Shared notes", "embed_url": pasted},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["embed_url"] == f"https://docs.google.com/document/d/{GOOGLE_ID}/preview"
    assert body["embed_open_url"] == pasted
    resp = client.post(
        url("document-list", lab, project_id=project.pk),
        {"title": "No", "embed_url": "https://evil.example/x"},
        format="json",
    )
    assert resp.status_code == 400 and "embed_url" in resp.json()
