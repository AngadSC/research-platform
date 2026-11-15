"""Statistics results sent straight to the person's own Google Drive (nothing is stored here)."""

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditAction, AuditEvent
from documents.models import Attachment
from integrations import http
from integrations.http import IntegrationError
from integrations.providers import google_drive
from integrations.tests.fake import response
from integrations.tests.test_from_drive import api, connect_drive
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def drive_configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "google_drive": {"client_id": "gd-client", "client_secret": "gd-secret"},
    }


@pytest.fixture
def world(transport, lab_users, make_project):
    lab, users = lab_users
    project = make_project(lab, "Sleep")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["member"], role=ProjectRole.CONTRIBUTOR
    )
    return lab, users, project


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def url(lab, project):
    return f"/api/labs/{lab.pk}/projects/{project.pk}/drive-export/"


def post(client, lab, project, filename="results.xlsx", data=b"PK\x03\x04x", **extra):
    return client.post(
        url(lab, project),
        {"file": SimpleUploadedFile(filename, data, content_type=XLSX), **extra},
        format="multipart",
    )


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake(account, **kw):
        calls.append(kw)
        return "g-new-1"

    monkeypatch.setattr(google_drive, "create_export", fake)
    return calls


def test_a_workbook_becomes_a_google_sheet_and_nothing_is_stored(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    before = Attachment.objects.for_lab(lab).count()
    r = post(api(users["pi"]), lab, project, filename="Score by arm.xlsx")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["id"] == "g-new-1"
    assert body["url"] == "https://docs.google.com/spreadsheets/d/g-new-1/edit"
    assert sent[0]["extension"] == ".xlsx" and sent[0]["name"] == "Score by arm"
    assert Attachment.objects.for_lab(lab).count() == before


def test_a_chart_picture_opens_in_the_drive_viewer(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    r = post(api(users["pi"]), lab, project, filename="chart.png", data=b"\x89PNG")
    assert r.status_code == 201
    assert r.json()["url"] == "https://drive.google.com/file/d/g-new-1/view"


def test_the_send_is_audited_with_the_participant_mark(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    post(api(users["pi"]), lab, project, participant_data="true")
    post(api(users["pi"]), lab, project)
    events = AuditEvent.objects.filter(action=AuditAction.ATTACHMENT_DOWNLOADED).order_by(
        "occurred_at"
    )
    flags = [
        e.metadata["participant_data"] for e in events if e.metadata.get("via") == "stats_export"
    ]
    assert flags == [True, False]
    assert events[0].metadata["drive_file_id"] == "g-new-1"


def test_the_chosen_name_is_cleaned(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    post(api(users["pi"]), lab, project, filename="a.xlsx", name="../x/Table\\1")
    assert sent[0]["name"] == "..xTable1"


@pytest.mark.parametrize("filename", ["run.exe", "notes.docx", "noextension", "x.xlsx.php"])
def test_only_sheets_csv_and_pictures_may_go(transport, world, sent, filename):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    r = post(api(users["pi"]), lab, project, filename=filename)
    assert r.status_code == 400 and "Only Excel, CSV, PNG and SVG" in str(r.json())
    assert sent == []


def test_a_file_over_the_limit_is_refused(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)
    big = b"0" * (google_drive.CONVERT_MAX_BYTES + 1)
    r = post(api(users["pi"]), lab, project, data=big)
    assert r.status_code == 400 and "too large" in str(r.json())
    assert sent == []


def test_without_a_connected_google_account_it_says_so(world, sent):
    lab, users, project = world
    r = post(api(users["pi"]), lab, project)
    assert r.status_code == 400 and "Connect Google in Integrations" in str(r.json())


def test_a_google_failure_is_a_clear_error_and_the_attempt_is_audited(
    transport, world, monkeypatch
):
    lab, users, project = world
    connect_drive(transport, users["pi"], lab)

    def boom(account, **kw):
        raise IntegrationError("down")

    monkeypatch.setattr(google_drive, "create_export", boom)
    r = post(api(users["pi"]), lab, project)
    assert r.status_code == 400 and "did not answer" in str(r.json())
    event = AuditEvent.objects.get(metadata__via="stats_export")
    assert event.metadata["outcome"] == "uncertain" and "drive_file_id" not in event.metadata


def test_a_contributor_cannot_send_results_out(transport, world, sent):
    lab, users, project = world
    connect_drive(transport, users["member"], lab)
    assert post(api(users["member"]), lab, project).status_code == 403
    assert sent == []


def test_each_file_type_goes_up_as_the_right_google_type(transport, world, monkeypatch):
    lab, users, project = world
    account = connect_drive(transport, users["pi"], lab)
    seen = []

    def send(method, address, **kw):
        seen.append(kw["data"].decode("latin-1"))
        return response(200, {"id": "g9"})

    monkeypatch.setattr(http, "send", send)
    for ext in (".xlsx", ".csv", ".png", ".svg"):
        google_drive.create_export(account, name="T", extension=ext, data=b"data")
    sheet, csv, png, svg = seen
    assert "application/vnd.google-apps.spreadsheet" in sheet
    assert "application/vnd.google-apps.spreadsheet" in csv and "Content-Type: text/csv" in csv
    assert "mimeType" not in json.dumps(png.split("\r\n")[3]) and "image/png" in png
    assert "mimeType" not in svg.split("\r\n")[3] and "image/svg+xml" in svg
