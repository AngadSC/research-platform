"""From Drive (D257): a Google Drive file attached by reference wherever a file can be uploaded.
Every Google call goes through the patched HTTP layer; nothing leaves the process."""

import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from documents.models import Attachment
from ethics.models import EthicsApproval
from integrations import registry, services
from integrations.providers import google_drive
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response
from papers import services as paper_services
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db

FILE_ID = "1AbC-dEf_9"
FILE_URL = f"https://www.googleapis.com/drive/v3/files/{FILE_ID}?fields={google_drive.FIELDS}"
WEB = f"https://drive.google.com/file/d/{FILE_ID}/view"


@pytest.fixture(autouse=True)
def drive_configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
    }


def drive_file(**over):
    return {
        "id": FILE_ID,
        "name": "Protocol v3.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": "2030-01-01T10:00:00.000Z",
        "version": "7",
        "webViewLink": WEB,
        "trashed": False,
        **over,
    }


def err(r, field="drive_file_id") -> str:
    """A field error: DRF gives a list, the documents services a plain string."""
    value = r.json()[field]
    return value[0] if isinstance(value, list) else value


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def connect_drive(transport, user, lab):
    request = make_request(user)
    url = services.start_connect(request, lab, "google_drive")
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on(
        "POST",
        google_drive.PROVIDER.token_url,
        token_reply("d-at", "d-rt", " ".join(registry.bundle_scopes(google_drive.PROVIDER))),
    )
    transport.on(
        "GET",
        google_drive.PROVIDER.identity_url,
        response(200, {"user": {"permissionId": "p1", "emailAddress": "a@uni.edu"}}),
    )
    return services.complete_connect(request, state=state, code="code")


@pytest.fixture
def world(transport, lab_users, make_project):
    lab, users = lab_users
    project = make_project(lab, "Sleep")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["member"], role=ProjectRole.CONTRIBUTOR
    )
    return lab, users, project


def files_url(lab, project):
    return f"/api/labs/{lab.pk}/projects/{project.pk}/attachments/"


def test_a_project_file_from_drive_takes_drive_own_name_and_link(transport, world):
    lab, users, project = world
    connect_drive(transport, users["member"], lab)
    transport.on("GET", FILE_URL, response(200, drive_file()))
    r = api(users["member"]).post(
        files_url(lab, project),
        {"drive_file_id": FILE_ID, "original_filename": "evil.exe"},
        format="multipart",
    )
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["original_filename"] == "Protocol v3.pdf"
    assert body["external_url"] == WEB and body["drive_file_id"] == FILE_ID
    assert body["notice_acknowledged_at"] is None and body["size_bytes"] == 0
    event = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_UPLOADED)
    assert event.metadata["source"] == "google_drive"


def test_opening_a_drive_file_goes_to_drive_and_is_audited(transport, world):
    lab, users, project = world
    connect_drive(transport, users["member"], lab)
    transport.on("GET", FILE_URL, response(200, drive_file()))
    client = api(users["member"])
    att = client.post(
        files_url(lab, project), {"drive_file_id": FILE_ID}, format="multipart"
    ).json()
    r = client.get(f"/api/labs/{lab.pk}/attachments/{att['id']}/download/")
    assert r.status_code == 302 and r["Location"] == WEB
    assert AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_DOWNLOADED).count() == 1


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (response(404, {}), "not available"),
        (response(200, drive_file(trashed=True)), "not available"),
        (response(200, drive_file(webViewLink="https://evil.example/x")), "unexpected link"),
    ],
    ids=["gone", "trashed", "foreign link"],
)
def test_a_file_drive_will_not_vouch_for_is_refused(transport, world, reply, message):
    lab, users, project = world
    connect_drive(transport, users["member"], lab)
    transport.on("GET", FILE_URL, reply)
    r = api(users["member"]).post(
        files_url(lab, project), {"drive_file_id": FILE_ID}, format="multipart"
    )
    assert r.status_code == 400 and message in err(r)
    assert Attachment.objects.for_lab(lab).count() == 0


def test_drive_needs_your_own_connection(transport, world):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)  # someone else's connection does not count
    r = api(users["member"]).post(
        files_url(lab, project), {"drive_file_id": FILE_ID}, format="multipart"
    )
    assert r.status_code == 400 and "Connect Google Drive" in err(r)


@pytest.mark.parametrize(
    "data",
    [{}, {"drive_file_id": FILE_ID, "acknowledged_notice": "true", "file": "upload"}],
    ids=["neither", "both"],
)
def test_exactly_one_of_a_file_or_a_drive_file(transport, world, data):
    lab, users, project = world
    if data.get("file"):
        data["file"] = SimpleUploadedFile("a.txt", b"hi", content_type="text/plain")
    r = api(users["member"]).post(files_url(lab, project), data, format="multipart")
    assert r.status_code == 400 and "file" in r.json()


def test_an_upload_still_needs_the_notice(transport, world):
    lab, users, project = world
    f = SimpleUploadedFile("a.txt", b"hi", content_type="text/plain")
    r = api(users["member"]).post(files_url(lab, project), {"file": f}, format="multipart")
    assert r.status_code == 400 and "acknowledged_notice" in r.json()


def test_a_viewer_cannot_attach_from_drive_either(transport, world):
    lab, users, project = world
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["viewer"], role=ProjectRole.VIEWER
    )
    r = api(users["viewer"]).post(
        files_url(lab, project), {"drive_file_id": FILE_ID}, format="multipart"
    )
    assert r.status_code == 403
    assert transport.calls == []  # refused before Google is asked anything


def test_an_ethics_approval_takes_a_drive_file(transport, world):
    lab, users, project = world
    approval = EthicsApproval.objects.create(
        lab=lab,
        approval_number="IRB-1",
        board="Board",
        title="Approval",
        approval_date=datetime.date(2030, 1, 1),
        expiry_date=datetime.date(2031, 1, 1),
        created_by=users["pi"],
    )
    approval.projects.add(project)
    connect_drive(transport, users["pi"], lab)
    transport.on("GET", FILE_URL, response(200, drive_file()))
    r = api(users["pi"]).post(
        f"/api/labs/{lab.pk}/ethics-approvals/{approval.pk}/attachments/",
        {"drive_file_id": FILE_ID},
        format="multipart",
    )
    assert r.status_code == 201, r.content
    assert Attachment.objects.for_lab(lab).get().ethics_approval_id == approval.pk


def test_a_paper_takes_a_drive_pdf_only_and_explains_it_cannot_be_read(transport, world):
    lab, users, _ = world
    client = api(users["member"])
    paper = client.post(f"/api/labs/{lab.pk}/papers/", {"title": "A paper"}, "json")
    assert paper.status_code == 201, paper.content
    pdf_url = f"/api/labs/{lab.pk}/papers/{paper.json()['id']}/pdf/"
    connect_drive(transport, users["member"], lab)

    transport.on("GET", FILE_URL, response(200, drive_file(mimeType="text/csv")))
    r = client.post(pdf_url, {"drive_file_id": FILE_ID}, format="multipart")
    assert r.status_code == 400 and "PDF" in err(r)
    assert Attachment.objects.for_lab(lab).count() == 0  # the refusal kept nothing

    transport.on("GET", FILE_URL, response(200, drive_file()))
    assert client.post(pdf_url, {"drive_file_id": FILE_ID}, format="multipart").status_code == 201
    from papers.models import Paper

    p = Paper.objects.for_lab(lab).get()
    with pytest.raises(paper_services.PdfTextError, match="in Google Drive"):
        paper_services.read_pdf_text(p, first=1, last=1)


# ---- "Edit in Google" (VISION B3): a Word, Excel or PowerPoint upload copied into Drive

COPY_ID = "gCopy-1"
COPY_URL = f"https://www.googleapis.com/drive/v3/files/{COPY_ID}?fields={google_drive.FIELDS}"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(world, name="Notes.docx", **kw):
    from documents import services as document_services

    lab, users, project = world
    f = SimpleUploadedFile(name, b"PK\x03\x04 fake docx", content_type=DOCX)
    return document_services.upload_attachment(project=project, user=users["pi"], file=f, **kw)


def edit_in_google(client, lab, att):
    return client.post(f"/api/labs/{lab.pk}/attachments/{att.pk}/edit-in-google/")


def test_edit_in_google_copies_into_your_drive_and_links_back(transport, world):
    lab, users, project = world
    from documents.models import Folder

    folder = Folder.objects.create(lab=lab, project=project, name="Drafts", created_by=users["pi"])
    att = upload(world, folder=folder)
    connect_drive(transport, users["member"], lab)
    transport.on("POST", google_drive.UPLOAD_URL, response(200, {"id": COPY_ID}))
    google_doc = "application/vnd.google-apps.document"
    copy = drive_file(id=COPY_ID, name="Notes", mimeType=google_doc, webViewLink=WEB)
    transport.on("GET", COPY_URL, response(200, copy))

    r = edit_in_google(api(users["member"]), lab, att)
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["copied_from"] == str(att.pk) and body["drive_file_id"] == COPY_ID
    assert body["folder"] == str(folder.pk) and body["content_type"] == google_doc
    (sent,) = transport.sent("POST", google_drive.UPLOAD_URL)
    assert sent["headers"]["Content-Type"].startswith("multipart/related; boundary=")
    assert b'"mimeType": "application/vnd.google-apps.document"' in sent["data"]
    assert b"PK\x03\x04 fake docx" in sent["data"] and b'"name": "Notes"' in sent["data"]
    event = AuditEvent.objects.get(
        action=AuditAction.ATTACHMENT_UPLOADED, metadata__copied_from=str(att.pk)
    )
    assert event.actor == users["member"] and event.metadata["drive_file_id"] == COPY_ID
    assert event.metadata["source"] == "google_copy"
    sent_out = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=att.pk)
    assert sent_out.metadata == {"via": "google_copy", "drive_file_id": COPY_ID}


def test_edit_in_google_of_a_pi_only_file_stays_out_of_the_lab_admins_log(transport, world):
    lab, users, project = world
    att = upload(world)
    # a grant letter (D244)
    Attachment.objects.for_lab(lab.pk).filter(pk=att.pk).update(pi_only=True)
    connect_drive(transport, users["pi"], lab)
    transport.on("POST", google_drive.UPLOAD_URL, response(200, {"id": COPY_ID}))
    google_doc = "application/vnd.google-apps.document"
    copy = drive_file(id=COPY_ID, name="Notes", mimeType=google_doc, webViewLink=WEB)
    transport.on("GET", COPY_URL, response(200, copy))

    r = edit_in_google(api(users["pi"]), lab, att)
    assert r.status_code == 201, r.content
    copy_row = Attachment.objects.for_lab(lab.pk).get(pk=r.json()["id"])
    assert copy_row.pi_only is True
    # neither the copy nor the send-out is a file event: funding.* is hidden from lab admins
    assert not AuditEvent.objects.filter(
        action__in=[AuditAction.ATTACHMENT_UPLOADED, AuditAction.ATTACHMENT_DOWNLOADED]
    ).exists()
    assert AuditEvent.objects.filter(action=AuditAction.FUNDING_UPDATED).count() == 2
    admin_view = api(users["lab_admin"]).get(f"/api/labs/{lab.pk}/audit-events/")
    assert admin_view.status_code == 200
    assert "google_copy" not in admin_view.content.decode()


def test_edit_in_google_needs_your_own_google_connection(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect_drive(transport, users["pi"], lab)  # someone else's connection does not count
    before = len(transport.calls)
    r = edit_in_google(api(users["member"]), lab, att)
    assert r.status_code == 400 and err(r, "file") == "Connect Google in Integrations first."
    assert len(transport.calls) == before


@pytest.mark.parametrize("where", ["file", "folder"])
def test_participant_data_never_goes_to_google(transport, world, where):
    lab, users, project = world
    from documents.models import Folder

    folder = Folder.objects.create(
        lab=lab,
        project=project,
        name="Raw",
        created_by=users["pi"],
        contains_participant_data=where == "folder",
    )
    att = upload(world, folder=folder, contains_participant_data=where == "file")
    if where == "folder":  # moved in after upload: the folder alone counts
        Attachment.objects.for_lab(lab).filter(pk=att.pk).update(contains_participant_data=False)
    connect_drive(transport, users["member"], lab)
    before = len(transport.calls)
    r = edit_in_google(api(users["member"]), lab, att)
    assert r.status_code == 400
    assert err(r, "file") == "Files marked as participant data stay in labbenchos."
    assert len(transport.calls) == before


def test_a_viewer_cannot_edit_in_google(transport, world):
    lab, users, project = world
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["viewer"], role=ProjectRole.VIEWER
    )
    att = upload(world)
    connect_drive(transport, users["viewer"], lab)
    before = len(transport.calls)
    assert edit_in_google(api(users["viewer"]), lab, att).status_code == 403
    assert len(transport.calls) == before


def test_a_file_too_large_for_google_is_refused(transport, world, monkeypatch):
    lab, users, _ = world
    monkeypatch.setattr(google_drive, "CONVERT_MAX_BYTES", 8)
    att = upload(world)
    connect_drive(transport, users["member"], lab)
    before = len(transport.calls)
    r = edit_in_google(api(users["member"]), lab, att)
    assert r.status_code == 400 and "too large" in err(r, "file")
    assert len(transport.calls) == before


def test_only_word_excel_and_powerpoint_files_can_be_edited_in_google(transport, world):
    lab, users, _ = world
    att = upload(world, name="Protocol.pdf")
    connect_drive(transport, users["member"], lab)
    r = edit_in_google(api(users["member"]), lab, att)
    assert r.status_code == 400 and "Word, Excel and PowerPoint" in err(r, "file")
