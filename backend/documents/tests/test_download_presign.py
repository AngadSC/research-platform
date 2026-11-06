"""D90: S3 mode redirects downloads to a short presigned URL (no network: signing is local)."""

import os
import subprocess
import sys
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from rest_framework.test import APIClient
from storages.backends.s3 import S3Storage

from audit.models import AuditAction, AuditEvent
from documents import views as documents_views
from documents.storage import LabFilesS3Storage
from documents.tests.test_documents import PDF, upload, url
from labs.models import LabRole


@pytest.fixture
def setup(make_lab, make_user, make_project, join):
    lab = make_lab("Lab A")
    user = make_user()
    join(user, lab, LabRole.PI)
    client = APIClient()
    client.force_login(user)
    return lab, user, make_project(lab), client


@pytest.fixture
def s3(settings, monkeypatch):
    """Uploads still hit the filesystem fixture; only the download view sees the S3 storage."""
    settings.LAB_FILES_BUCKET = "lab-bucket"
    settings.LAB_FILES_STREAM_DOWNLOADS = False
    store = S3Storage(
        bucket_name="lab-bucket",
        access_key="AKIAFAKE",
        secret_key="secret",
        region_name="eu-west-1",
        querystring_auth=True,
        signature_version="s3v4",
    )
    spy = MagicMock(wraps=store.url)
    store.url = spy
    monkeypatch.setattr("documents.views.storages", {"lab_files": store})
    return spy


def query(resp):
    return {k: v[0] for k, v in parse_qs(urlsplit(resp["Location"]).query).items()}


def test_redirects_to_short_presigned_url_with_overrides(setup, s3):
    lab, user, project, client = setup
    att_id = upload(client, lab, project, name='re"po\nrt é.txt', ctype="text/plain").json()["id"]
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp.status_code == 302
    assert resp["Cache-Control"] == "no-store"
    assert resp["Referrer-Policy"] == "no-referrer"
    q = query(resp)
    assert urlsplit(resp["Location"]).netloc.startswith("lab-bucket.")
    assert urlsplit(resp["Location"]).path.startswith(f"/labs/{lab.pk}/attachments/")
    assert 0 < int(q["X-Amz-Expires"]) <= 60
    assert q["response-content-type"] == "text/plain"
    assert q["response-cache-control"] == "private, no-store"
    disposition = q["response-content-disposition"]
    assert disposition.startswith("attachment; filename*=utf-8''")  # RFC 5987, not a raw quote
    assert "\n" not in disposition and '"' not in disposition and "é" not in disposition
    event = AuditEvent.objects.get(lab=lab, action=AuditAction.ATTACHMENT_DOWNLOADED)
    assert event.actor == user and str(event.target_id) == att_id


def test_pdf_streams_through_django_with_the_safety_headers(setup, s3):
    """D123: anything shown inline never gets a bucket URL, so it keeps `nosniff` and the
    sandbox CSP, which only Django can set."""
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    store = documents_views.storages["lab_files"]
    store.open = storages["lab_files"].open  # the bytes are in the filesystem fixture
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp.status_code == 200 and b"".join(resp.streaming_content) == PDF
    assert resp["Content-Disposition"] == 'inline; filename="a.pdf"'
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Content-Security-Policy"] == "sandbox"
    assert resp["Cache-Control"] == "private, no-store"
    s3.assert_not_called()


@pytest.mark.parametrize("ctype", ["text/html", "image/svg+xml", "application/xhtml+xml"])
def test_presigned_downloads_are_always_attachments(setup, s3, ctype):
    lab, _, project, client = setup
    att_id = upload(client, lab, project, name="page.html", ctype=ctype).json()["id"]
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp.status_code == 302
    assert query(resp)["response-content-disposition"] == 'attachment; filename="page.html"'


def test_objects_are_stored_as_forced_downloads(settings):
    """D123: the bucket itself says octet-stream + attachment, whatever the client declared, so
    a provider that ignores the response-* overrides still can't render an upload."""
    store = LabFilesS3Storage(
        bucket_name="lab-bucket", access_key="a", secret_key="b", default_acl="private"
    )
    content = ContentFile(b"<script>1</script>")
    content.content_type = "text/html"
    params = store._get_write_parameters("labs/x/attachments/y", content)
    assert params["ContentType"] == "application/octet-stream"
    assert params["ContentDisposition"] == "attachment"
    assert params["CacheControl"] == "private, no-store"
    assert params["ACL"] == "private"


def test_the_bucket_setting_uses_that_storage():
    code = "from config import settings as s; print(s.STORAGES['lab_files']['BACKEND'])"
    env = {**os.environ, "LAB_FILES_BUCKET": "lab-bucket", "DEBUG": "True"}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    assert out.stdout.strip() == "documents.storage.LabFilesS3Storage"


def test_forbidden_and_cross_lab_requests_get_no_url(setup, s3, make_lab, make_user, join):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    target = url("attachment-download", lab, attachment_id=att_id)
    outsider = make_user()
    other = make_lab("Lab B")
    join(outsider, other, LabRole.PI)
    client.force_login(outsider)
    assert client.get(target).status_code == 404  # not a member of this lab
    other_url = url("attachment-download", other, attachment_id=att_id)
    assert client.get(other_url).status_code == 404  # lab B's scope has no such file
    client.logout()
    assert client.get(target).status_code in (401, 403)
    s3.assert_not_called()
    assert not AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_DOWNLOADED).exists()


def test_stream_setting_keeps_streaming(setup, s3, settings, monkeypatch):
    lab, _, project, client = setup
    att_id = upload(client, lab, project).json()["id"]
    monkeypatch.setattr("documents.views.storages", storages)  # the real (filesystem) alias
    settings.LAB_FILES_STREAM_DOWNLOADS = True
    resp = client.get(url("attachment-download", lab, attachment_id=att_id))
    assert resp.status_code == 200 and b"".join(resp.streaming_content) == PDF
    s3.assert_not_called()
