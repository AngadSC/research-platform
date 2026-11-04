import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents.models import Attachment, Document
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
