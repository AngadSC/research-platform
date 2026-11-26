"""Edit in Word, Excel or PowerPoint: a copy of an upload in the app folder of the person's own
OneDrive, linked back like Edit in Google (D273). Every Microsoft call goes through the patched
HTTP layer; nothing leaves the process."""

import datetime
from urllib.parse import parse_qs, urlsplit

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from assistant import privacy, tools
from audit.models import AuditAction, AuditEvent
from documents import office
from documents import services as document_services
from documents.models import Attachment, Folder
from integrations import services
from integrations.models import ConnectedAccount
from integrations.providers import onedrive
from integrations.tests.conftest import make_request, token_reply
from integrations.tests.fake import response
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
READ = "Files.Read.All offline_access"
ALL = f"{READ} {onedrive.EDIT_SCOPE}"
PUT_URL = (
    f"{onedrive.GRAPH}/me/drive/special/approot:/Notes.docx:/content"
    "?@microsoft.graph.conflictBehavior=rename"
)
WEB = "https://contoso-my.sharepoint.com/personal/ada_contoso_com/_layouts/15/Doc.aspx?file=Notes.docx"
ITEM = {
    "id": "01COPY",
    "name": "Notes.docx",
    "webUrl": WEB,
    "parentReference": {"driveId": "b!drv"},
}


@pytest.fixture(autouse=True)
def onedrive_configured(settings):
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "onedrive": {"client_id": "od-client", "client_secret": "od-secret"},
    }


@pytest.fixture
def world(transport, lab_users, make_project):
    lab, users = lab_users
    project = make_project(lab, "Sleep")
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["member"], role=ProjectRole.CONTRIBUTOR
    )
    return lab, users, project


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


def connect(transport, user, lab, *, scopes=None, granted=ALL):
    request = make_request(user)
    url = services.start_connect(request, lab, "onedrive", scopes=scopes)
    state = parse_qs(urlsplit(url).query)["state"][0]
    transport.on("POST", onedrive.PROVIDER.token_url, token_reply("od-at", "od-rt", granted))
    transport.on(
        "GET",
        onedrive.PROVIDER.identity_url,
        response(200, {"id": "b!drv", "owner": {"user": {"email": "ada@example.test"}}}),
    )
    services.complete_connect(request, state=state, code="code")
    return url


def upload(world, name="Notes.docx", **kw):
    lab, users, project = world
    f = SimpleUploadedFile(name, b"PK\x03\x04 fake docx", content_type=DOCX)
    return document_services.upload_attachment(project=project, user=users["pi"], file=f, **kw)


def edit(client, lab, att):
    return client.post(f"/api/labs/{lab.pk}/attachments/{att.pk}/edit-in-office/")


def err(r):
    value = r.json()["file"]
    return value[0] if isinstance(value, list) else value


def test_a_plain_connect_never_asks_to_write():
    """The extra scope is asked for only when the person clicks "Allow editing in Office"."""
    assert onedrive.EDIT_SCOPE not in onedrive.PROVIDER.required_scopes


def test_scopes_asked_for(transport, world):
    lab, users, _ = world
    plain = connect(transport, users["member"], lab, granted=READ)
    assert parse_qs(urlsplit(plain).query)["scope"] == ["Files.Read.All offline_access"]
    account = ConnectedAccount.objects.for_lab(lab).get(user=users["member"], provider="onedrive")
    assert onedrive.EDIT_SCOPE not in account.granted_scopes  # read-only, and still connected
    # the button: same account, same row, now allowed to save to its own folder
    upgrade = connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    assert onedrive.EDIT_SCOPE in parse_qs(urlsplit(upgrade).query)["scope"][0].split()
    account.refresh_from_db()
    assert onedrive.EDIT_SCOPE in account.granted_scopes
    assert ConnectedAccount.objects.for_lab(lab).filter(provider="onedrive").count() == 1


def test_edit_in_office_copies_into_your_onedrive_and_links_back(transport, world):
    lab, users, project = world
    folder = Folder.objects.create(lab=lab, project=project, name="Drafts", created_by=users["pi"])
    att = upload(world, folder=folder)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, response(201, ITEM))

    r = edit(api(users["member"]), lab, att)
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["copied_from"] == str(att.pk) and body["external_url"] == WEB
    assert body["folder"] == str(folder.pk) and body["drive_file_id"] == ""
    assert body["original_filename"] == "Notes.docx" and body["content_type"] == DOCX
    (sent,) = transport.sent("PUT", PUT_URL)
    assert sent["data"] == b"PK\x03\x04 fake docx"
    assert sent["headers"]["Authorization"] == "Bearer od-at"
    uploaded = AuditEvent.objects.get(
        action=AuditAction.ATTACHMENT_UPLOADED, metadata__copied_from=str(att.pk)
    )
    assert uploaded.actor == users["member"] and uploaded.metadata["source"] == "office_copy"
    sent_out = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=att.pk)
    assert sent_out.metadata == {
        "via": "office_copy",
        "onedrive_item": "b!drv.01COPY",
        "participant_data": False,
    }
    # opening the copy goes to Office on the web; there are no bytes here
    opened = api(users["member"]).get(f"/api/labs/{lab.pk}/attachments/{body['id']}/download/")
    assert opened.status_code == 302 and opened["Location"] == WEB


def test_an_expired_token_is_refreshed_first(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    account = ConnectedAccount.objects.for_lab(lab).get(user=users["member"], provider="onedrive")
    ConnectedAccount.objects.for_lab(lab).filter(pk=account.pk).update(
        token_expires_at=timezone.now() - datetime.timedelta(minutes=5)
    )
    transport.on("POST", onedrive.PROVIDER.token_url, token_reply("od-at-2", "od-rt-2", ALL))
    transport.on("PUT", PUT_URL, response(201, ITEM))
    assert edit(api(users["member"]), lab, att).status_code == 201
    (sent,) = transport.sent("PUT", PUT_URL)
    assert sent["headers"]["Authorization"] == "Bearer od-at-2"
    account.refresh_from_db()
    assert onedrive.EDIT_SCOPE in account.granted_scopes


def test_a_refused_token_is_refreshed_and_tried_again(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("POST", onedrive.PROVIDER.token_url, token_reply("od-at-2", "od-rt-2", ALL))
    transport.on("PUT", PUT_URL, response(401, {}), response(201, ITEM))
    assert edit(api(users["member"]), lab, att).status_code == 201
    _first, second = transport.sent("PUT", PUT_URL)
    assert second["headers"]["Authorization"] == "Bearer od-at-2"


def _no_call(transport, world, user, att):
    lab = world[0]
    before = len(transport.calls)
    r = edit(api(user), lab, att)
    assert len(transport.calls) == before, "nothing may reach Microsoft"
    assert not Attachment.objects.for_lab(lab).filter(copied_from=att).exists()
    return r


@pytest.mark.parametrize("where", ["file", "folder"])
def test_participant_data_is_refused_before_anything_leaves(transport, world, where):
    lab, users, project = world
    folder = Folder.objects.create(
        lab=lab,
        project=project,
        name="Raw",
        created_by=users["pi"],
        contains_participant_data=where == "folder",
    )
    att = upload(world, folder=folder, contains_participant_data=where == "file")
    if where == "folder":  # the folder alone counts
        Attachment.objects.for_lab(lab).filter(pk=att.pk).update(contains_participant_data=False)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    r = _no_call(transport, world, users["member"], att)
    assert r.status_code == 400 and "identifying participants" in err(r)


def test_a_viewer_cannot_edit_in_office(transport, world):
    lab, users, project = world
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["viewer"], role=ProjectRole.VIEWER
    )
    att = upload(world)
    connect(transport, users["viewer"], lab, scopes=list(onedrive.PROVIDER.scopes))
    assert _no_call(transport, world, users["viewer"], att).status_code == 403


def test_needs_your_own_connection_in_this_lab(transport, world, make_lab, join):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["pi"], lab, scopes=list(onedrive.PROVIDER.scopes))  # not yours
    other = make_lab()
    join(users["member"], other, "member")
    connect(transport, users["member"], other, scopes=list(onedrive.PROVIDER.scopes))  # elsewhere
    r = _no_call(transport, world, users["member"], att)
    assert r.status_code == 400 and err(r) == "Connect OneDrive first."


def test_a_read_only_connection_must_allow_editing_first(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, granted=READ)
    r = _no_call(transport, world, users["member"], att)
    assert r.status_code == 400 and err(r) == "Allow editing in Office first."


def test_a_file_too_large_is_refused(transport, world, monkeypatch):
    lab, users, _ = world
    monkeypatch.setattr(office, "MAX_BYTES", 8)
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    r = _no_call(transport, world, users["member"], att)
    assert r.status_code == 400 and "too large" in err(r)


@pytest.mark.parametrize("name", ["Protocol.pdf", "Old.doc", "noextension"])
def test_only_word_excel_and_powerpoint_files(transport, world, name):
    lab, users, _ = world
    att = upload(world, name=name)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    r = _no_call(transport, world, users["member"], att)
    assert r.status_code == 400 and "Word, Excel and PowerPoint" in err(r)


def test_a_copy_is_not_copied_again_to_office_or_google(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, response(201, ITEM))
    copy = Attachment.objects.for_lab(lab).get(pk=edit(api(users["member"]), lab, att).json()["id"])
    assert _no_call(transport, world, users["member"], copy).status_code == 400
    google = api(users["member"]).post(f"/api/labs/{lab.pk}/attachments/{copy.pk}/edit-in-google/")
    assert google.status_code == 400


def test_microsoft_refusing_the_write_asks_to_allow_again_and_is_recorded(transport, world):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, response(403, {"error": {"code": "accessDenied"}}))
    r = edit(api(users["member"]), lab, att)
    assert r.status_code == 400 and err(r) == "Allow editing in Office first."
    event = AuditEvent.objects.get(action=AuditAction.ATTACHMENT_DOWNLOADED, target_id=att.pk)
    assert event.metadata["outcome"] == "uncertain"
    assert not Attachment.objects.for_lab(lab).filter(copied_from=att).exists()


@pytest.mark.parametrize(
    "reply",
    [
        response(500, {}),
        response(201, {**ITEM, "webUrl": "https://evil.example.test/x"}),
        response(201, {"id": "x"}),
    ],
    ids=["error", "foreign link", "unreadable"],
)
def test_a_bad_answer_links_nothing(transport, world, reply):
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, reply)
    r = edit(api(users["member"]), lab, att)
    assert r.status_code == 400 and err(r) == "OneDrive did not answer. Try again."
    assert not Attachment.objects.for_lab(lab).filter(copied_from=att).exists()


def test_a_pi_only_file_stays_out_of_the_lab_admins_log(transport, world):
    lab, users, _ = world
    att = upload(world)
    Attachment.objects.for_lab(lab.pk).filter(pk=att.pk).update(pi_only=True)  # D244
    connect(transport, users["pi"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, response(201, ITEM))
    r = edit(api(users["pi"]), lab, att)
    assert r.status_code == 201, r.content
    assert Attachment.objects.for_lab(lab).get(pk=r.json()["id"]).pi_only is True
    admin_view = api(users["lab_admin"]).get(f"/api/labs/{lab.pk}/audit-events/")
    assert admin_view.status_code == 200 and "office_copy" not in admin_view.content.decode()


def test_names_onedrive_refuses_are_made_safe():
    assert office.safe_name('a/b:c*"?<>|#%', ".docx") == "a_b_c________.docx"
    assert office.safe_name(" . ", ".xlsx") == "file.xlsx"


def test_the_copy_follows_the_original_into_privacy_and_ai_never_opens_it(transport, world):
    """D273's finding: flagging the original later hides the copy from AI too."""
    lab, users, _ = world
    att = upload(world)
    connect(transport, users["member"], lab, scopes=list(onedrive.PROVIDER.scopes))
    transport.on("PUT", PUT_URL, response(201, ITEM))
    copy = Attachment.objects.for_lab(lab).get(pk=edit(api(users["member"]), lab, att).json()["id"])
    ctx = tools.Context(
        user=users["member"], lab_ids=frozenset({str(lab.pk)}), can_write=True, client="Test"
    )
    args = {"lab_id": str(lab.pk), "file_id": str(copy.pk)}
    with pytest.raises(tools.ToolError, match="OneDrive"):
        tools.call(ctx, "read_file", args)
    with pytest.raises(tools.ToolError, match="OneDrive"):
        tools.call(ctx, "get_file_link", args)

    qs = Attachment.objects.for_lab(lab).filter(pk__in=[att.pk, copy.pk])
    assert set(privacy.ai_visible(qs)) == {att, copy}
    privacy.set_flag(att, True, user=users["pi"])
    assert list(privacy.ai_visible(qs)) == []
    copy.refresh_from_db()
    assert privacy.is_flagged(copy)
