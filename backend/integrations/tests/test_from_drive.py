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
from integrations.providers import google_calendar, google_drive
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
    transport.on("GET", google_calendar.PROVIDER.identity_url, response(200, {"id": "a@uni.edu"}))
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
