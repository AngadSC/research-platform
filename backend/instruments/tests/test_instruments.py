"""Instrument files and drop links: where files land, parsing, link scope and lifetime,
cross-lab isolation, participant data."""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from assistant import privacy
from assistant.services import revoke_all
from assistant.tests.reauth import sign_in
from audit.models import AuditAction, AuditEvent
from documents.models import Attachment, Folder
from instruments import jobs, views
from instruments.models import InstrumentDropLink, InstrumentFile, ParseStatus
from labs import services as lab_services
from labs.models import InventoryItem, LabMembership, LabRole, hash_token
from projects import services as project_services
from projects.models import ProjectMembership, ProjectRole

pytestmark = pytest.mark.django_db
DROP = "/api/instrument-drop/"


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Glyco Lab")
    users = {}
    for name, role in [("pi", LabRole.PI), ("ann", LabRole.MEMBER), ("vic", LabRole.MEMBER)]:
        users[name] = make_user(display_name=name.title(), email=f"{name}@example.test")
        join(users[name], lab, role)
    project = make_project(lab, "Sialyltransferase")
    other = make_project(lab, "Other project")
    for name, role in [("ann", ProjectRole.CONTRIBUTOR), ("vic", ProjectRole.VIEWER)]:
        ProjectMembership.objects.create(lab=lab, project=project, user=users[name], role=role)
    reader = InventoryItem.objects.create(
        lab=lab, name="Plate reader", category="equipment", instrument_software="agilent_gen5"
    )
    return lab, users, project, other, reader


def api(user, *, fresh=True):
    c = APIClient()
    return sign_in(c, user) if fresh else (c.force_login(user) or c)


def drop_url(lab, project, item):
    return f"/api/labs/{lab.pk}/projects/{project.pk}/instruments/{item.pk}/files/"


def a_file(name="read1.csv", body=b"Well,OD\nA1,0.12\n", ctype="text/csv"):
    return SimpleUploadedFile(name, body, content_type=ctype)


def make_link(client, lab, item, project, **extra):
    r = client.post(
        f"/api/labs/{lab.pk}/instruments/{item.pk}/drop-links/",
        {"project": str(project.pk), "label": "Core PC", **extra},
        format="json",
    )
    assert r.status_code == 201, r.content
    return r.json()


def token_of(link_json):
    return link_json["url"].rsplit("/drop/", 1)[1]


# ---------------------------------------------------------------- the signed-in drop page


def test_drop_files_land_in_instrument_folder_and_parse(
    world, django_capture_on_commit_callbacks, monkeypatch
):
    lab, users, project, _, reader = world
    seen = []

    def fake_parse(data, filename, software=""):
        seen.append((data, filename, software))
        return {"status": "ok", "kind": "plate", "title": "Read 1"}

    monkeypatch.setattr(jobs, "parse_file", fake_parse)
    with django_capture_on_commit_callbacks(execute=True):
        r = api(users["ann"]).post(
            drop_url(lab, project, reader),
            {"file": a_file(), "acknowledged_notice": "true"},
            format="multipart",
        )
    assert r.status_code == 201, r.content
    item = InstrumentFile.objects.for_lab(lab).get(pk=r.json()["id"])
    assert item.status == ParseStatus.OK and item.summary["title"] == "Read 1"
    assert seen == [(b"Well,OD\nA1,0.12\n", "read1.csv", "agilent_gen5")]
    assert item.dropped_by == users["ann"] and item.uploaded_via == "page"
    att = item.attachment
    assert att.project_id == project.pk and att.uploaded_by == users["ann"]
    assert att.folder.name == "Plate reader" and att.folder.parent.name == "Instrument data"
    # a second drop reuses the same folders
    with django_capture_on_commit_callbacks(execute=True):
        api(users["ann"]).post(
            drop_url(lab, project, reader),
            {"file": a_file("read2.csv"), "acknowledged_notice": "true"},
            format="multipart",
        )
    assert Folder.objects.for_lab(lab).filter(project=project).count() == 2
    detail = api(users["vic"]).get(f"/api/labs/{lab.pk}/instrument-files/{item.pk}/").json()
    assert detail["summary"]["kind"] == "plate" and detail["filename"] == "read1.csv"


def test_parse_failure_never_blocks_the_upload(
    world, django_capture_on_commit_callbacks, monkeypatch
):
    lab, users, project, _, reader = world

    def boom(*a, **k):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(jobs, "parse_file", boom)
    with django_capture_on_commit_callbacks(execute=True):
        r = api(users["ann"]).post(
            drop_url(lab, project, reader),
            {"file": a_file(), "acknowledged_notice": "true"},
            format="multipart",
        )
    assert r.status_code == 201
    assert InstrumentFile.objects.for_lab(lab).get().status == ParseStatus.FAILED


def test_drop_needs_the_notice_and_a_contributor(world):
    lab, users, project, other, reader = world
    url = drop_url(lab, project, reader)
    r = api(users["ann"]).post(url, {"file": a_file()}, format="multipart")
    assert r.status_code == 400 and "acknowledged_notice" in r.json()
    r = api(users["vic"]).post(
        url, {"file": a_file(), "acknowledged_notice": "true"}, format="multipart"
    )
    assert r.status_code == 403  # a project viewer
    r = api(users["ann"]).post(
        drop_url(lab, other, reader),
        {"file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert r.status_code == 404  # not on that project
    consumable = InventoryItem.objects.create(lab=lab, name="Tips", category="consumable")
    r = api(users["ann"]).post(
        drop_url(lab, project, consumable),
        {"file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert r.status_code == 404  # only equipment collects data
    assert not Attachment.objects.for_lab(lab).exists()


def test_participant_flag_is_kept_and_inherited(world):
    lab, users, project, _, reader = world
    r = api(users["ann"]).post(
        drop_url(lab, project, reader),
        {"file": a_file(), "acknowledged_notice": "true", "contains_participant_data": "true"},
        format="multipart",
    )
    flagged = InstrumentFile.objects.for_lab(lab).get(pk=r.json()["id"]).attachment
    assert flagged.contains_participant_data and privacy.is_flagged(flagged)
    assert r.json()["contains_participant_data"] is True
    # flag the instrument's folder: the next file is flagged without being asked
    Folder.objects.for_lab(lab).filter(name="Plate reader").update(contains_participant_data=True)
    r = api(users["ann"]).post(
        drop_url(lab, project, reader),
        {"file": a_file("b.csv"), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert (
        InstrumentFile.objects.for_lab(lab)
        .get(pk=r.json()["id"])
        .attachment.contains_participant_data
    )


def test_content_type_and_name_are_not_taken_from_the_browser(world):
    lab, users, project, _, reader = world
    r = api(users["ann"]).post(
        drop_url(lab, project, reader),
        {
            "file": a_file("evil.html", b"<script>alert(1)</script>", "application/pdf"),
            "acknowledged_notice": "true",
        },
        format="multipart",
    )
    att = InstrumentFile.objects.for_lab(lab).get(pk=r.json()["id"]).attachment
    assert att.content_type == "text/html"  # downloads are forced, with nosniff and a sandbox
    r = api(users["ann"]).post(
        drop_url(lab, project, reader),
        {
            "file": a_file("fake.pdf", b"not a pdf", "application/pdf"),
            "acknowledged_notice": "true",
        },
        format="multipart",
    )
    att = InstrumentFile.objects.for_lab(lab).get(pk=r.json()["id"]).attachment
    assert att.content_type == "application/octet-stream"  # never shown inline
    r = api(users["ann"]).post(
        drop_url(lab, project, reader),
        {"file": a_file("..\\..\\run‮1.csv"), "acknowledged_notice": "true"},
        format="multipart",
    )
    name = InstrumentFile.objects.for_lab(lab).get(pk=r.json()["id"]).attachment.original_filename
    assert name == "run1.csv"


def test_list_shows_only_what_the_viewer_may_see(world, make_user, join):
    lab, users, project, other, reader = world
    api(users["ann"]).post(
        drop_url(lab, project, reader),
        {"file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    api(users["pi"]).post(
        drop_url(lab, other, reader),
        {"file": a_file("other.csv"), "acknowledged_notice": "true"},
        format="multipart",
    )
    url = f"/api/labs/{lab.pk}/instrument-files/?instrument={reader.pk}"
    assert len(api(users["pi"]).get(url).json()) == 2
    names = [f["filename"] for f in api(users["ann"]).get(url).json()]
    assert names == ["read1.csv"]  # not on "Other project"
    by_project = api(users["pi"]).get(f"/api/labs/{lab.pk}/instrument-files/?project={other.pk}")
    assert [f["filename"] for f in by_project.json()] == ["other.csv"]
    assert api(users["pi"]).get(f"/api/labs/{lab.pk}/instrument-files/?project=nope").json() == []
    # a file later linked to funding is PI-only (D244), here too
    Attachment.objects.for_lab(lab).filter(original_filename="read1.csv").update(pi_only=True)
    assert api(users["ann"]).get(url).json() == []
    # a deleted file leaves the list
    Attachment.objects.for_lab(lab).update(deleted_at=timezone.now())
    assert api(users["pi"]).get(url).json() == []


def test_cross_lab_is_404(world, make_lab, make_user, make_project, join):
    lab, users, project, _, reader = world
    lab_b = make_lab("Other Lab")
    boss = make_user(email="boss@example.test")
    join(boss, lab_b, LabRole.PI)
    p_b = make_project(lab_b, "B project")
    item_b = InventoryItem.objects.create(lab=lab_b, name="B reader", category="equipment")
    link_b = make_link(api(boss), lab_b, item_b, p_b)
    pi = api(users["pi"])
    assert pi.get(f"/api/labs/{lab.pk}/instruments/{item_b.pk}/drop-links/").status_code == 404
    assert pi.delete(f"/api/labs/{lab.pk}/instrument-drop-links/{link_b['id']}/").status_code == 404
    assert pi.get(f"/api/labs/{lab_b.pk}/instrument-files/").status_code == 404
    r = pi.post(
        drop_url(lab, p_b, reader),
        {"file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert r.status_code == 404
    r = pi.post(
        drop_url(lab, project, item_b),
        {"file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert r.status_code == 404
    # a link into another lab's project cannot be made
    r = pi.post(
        f"/api/labs/{lab.pk}/instruments/{reader.pk}/drop-links/",
        {"project": str(p_b.pk)},
        format="json",
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- drop links


def test_link_creation_needs_recent_sign_in_and_stores_only_a_hash(world):
    lab, users, project, _, reader = world
    url = f"/api/labs/{lab.pk}/instruments/{reader.pk}/drop-links/"
    stale = api(users["ann"], fresh=False).post(url, {"project": str(project.pk)}, format="json")
    assert stale.status_code == 401 and "flows" in stale.json()["data"]
    assert not InstrumentDropLink.objects.for_lab(lab).exists()
    made = make_link(api(users["ann"]), lab, reader, project, expires_in_days=7)
    token = token_of(made)
    assert len(token) >= 43  # 256 bits
    link = InstrumentDropLink.objects.for_lab(lab).get()
    assert link.token_hash == hash_token(token) and token not in str(link.__dict__)
    event = AuditEvent.objects.get(action=AuditAction.INSTRUMENT_DROP_LINK_CREATED)
    assert token not in str(event.metadata) and token not in event.target_repr
    listed = api(users["ann"]).get(url).json()
    assert [x["id"] for x in listed] == [made["id"]] and "url" not in listed[0]
    # viewers of the project cannot make one
    r = api(users["vic"]).post(url, {"project": str(project.pk)}, format="json")
    assert r.status_code == 403
    # others see only their own; a PI sees everyone's
    assert api(users["vic"]).get(url).json() == []
    assert len(api(users["pi"]).get(url).json()) == 1


def test_public_drop_shows_names_only_and_uploads_into_the_bound_project(
    world, django_capture_on_commit_callbacks
):
    lab, users, project, other, reader = world
    token = token_of(make_link(api(users["ann"]), lab, reader, project))
    anon = APIClient()
    r = anon.get(DROP, {"token": token})
    assert r.status_code == 200
    assert r.json() == {
        "instrument": "Plate reader",
        "project": "Sialyltransferase",
        "max_bytes": 50 * 1024 * 1024,
    }
    assert (
        r["X-Content-Type-Options"] == "nosniff"
        and "default-src 'none'" in r["Content-Security-Policy"]
    )
    assert r["Cache-Control"] == "private, no-store" and r["Referrer-Policy"] == "no-referrer"
    with django_capture_on_commit_callbacks(execute=True):
        r = anon.post(
            DROP,
            {
                "token": token,
                "file": a_file(),
                "acknowledged_notice": "true",
                "project": str(other.pk),  # ignored: the link names the project
            },
            format="multipart",
        )
    assert r.status_code == 201, r.content
    assert r.json() == {"name": "read1.csv", "size_bytes": 16}  # no ids, nothing to read back
    item = InstrumentFile.objects.for_lab(lab).get()
    assert item.project_id == project.pk and item.uploaded_via == "link"
    assert item.dropped_by is None and item.attachment.uploaded_by == users["ann"]
    assert item.status == ParseStatus.UNSUPPORTED  # the stub parser
    assert AuditEvent.objects.filter(action=AuditAction.INSTRUMENT_DROP_LINK_USED).count() == 1
    assert InstrumentDropLink.objects.for_lab(lab).get().last_used_at is not None
    # the notice still has to be acknowledged
    r = anon.post(DROP, {"token": token, "file": a_file()}, format="multipart")
    assert r.status_code == 400


def test_a_session_does_not_stand_in_for_the_token(world):
    lab, users, project, _, reader = world
    make_link(api(users["ann"]), lab, reader, project)
    for client in (api(users["pi"]), APIClient()):
        assert client.get(DROP).status_code == 401
        assert client.get(DROP, {"token": "x" * 43}).status_code == 401
        r = client.post(DROP, {"file": a_file(), "acknowledged_notice": "true"}, format="multipart")
        assert r.status_code == 401
    assert not InstrumentFile.objects.for_lab(lab).exists()


def test_revoked_and_expired_links_stop(world):
    lab, users, project, _, reader = world
    ann = api(users["ann"])
    made = make_link(ann, lab, reader, project)
    token = token_of(made)
    assert ann.delete(f"/api/labs/{lab.pk}/instrument-drop-links/{made['id']}/").status_code == 204
    assert APIClient().get(DROP, {"token": token}).status_code == 410
    assert AuditEvent.objects.filter(action=AuditAction.INSTRUMENT_DROP_LINK_REVOKED).count() == 1
    # revoking twice is fine and audits once
    assert ann.delete(f"/api/labs/{lab.pk}/instrument-drop-links/{made['id']}/").status_code == 204
    assert AuditEvent.objects.filter(action=AuditAction.INSTRUMENT_DROP_LINK_REVOKED).count() == 1
    assert ann.get(f"/api/labs/{lab.pk}/instruments/{reader.pk}/drop-links/").json() == []

    made = make_link(ann, lab, reader, project, expires_in_days=1)
    InstrumentDropLink.objects.for_lab(lab).filter(pk=made["id"]).update(
        expires_at=timezone.now() - datetime.timedelta(minutes=1)
    )
    r = APIClient().post(
        DROP,
        {"token": token_of(made), "file": a_file(), "acknowledged_notice": "true"},
        format="multipart",
    )
    assert r.status_code == 410
    # someone else's link cannot be revoked by a member; a PI can
    made = make_link(ann, lab, reader, project)
    url = f"/api/labs/{lab.pk}/instrument-drop-links/{made['id']}/"
    assert api(users["vic"]).delete(url).status_code == 404
    assert api(users["pi"]).delete(url).status_code == 204


def test_links_end_when_the_maker_loses_access(world):
    lab, users, project, _, reader = world
    ann = api(users["ann"])
    t1 = token_of(make_link(ann, lab, reader, project))
    membership = ProjectMembership.objects.for_lab(lab).get(project=project, user=users["ann"])
    project_services.remove_member(membership=membership, by=users["pi"])
    link = InstrumentDropLink.objects.for_lab(lab).get()
    assert link.revoked_at is not None
    assert APIClient().get(DROP, {"token": t1}).status_code == 410

    # leaving the lab ends it too
    ProjectMembership.objects.create(
        lab=lab, project=project, user=users["ann"], role=ProjectRole.CONTRIBUTOR
    )
    t2 = token_of(make_link(api(users["ann"]), lab, reader, project))
    lab_services.remove_member(
        membership=LabMembership.objects.for_lab(lab).get(user=users["ann"]), by=users["pi"]
    )
    assert APIClient().get(DROP, {"token": t2}).status_code == 410


def test_use_rechecks_access_even_without_revocation(world):
    """Revocation is bookkeeping; every use reads the maker's access again."""
    lab, users, project, _, reader = world
    token = token_of(make_link(api(users["ann"]), lab, reader, project))
    ProjectMembership.objects.for_lab(lab).filter(user=users["ann"]).update(role=ProjectRole.VIEWER)
    assert APIClient().get(DROP, {"token": token}).status_code == 403
    ProjectMembership.objects.for_lab(lab).filter(user=users["ann"]).delete()
    assert APIClient().get(DROP, {"token": token}).status_code == 404
    project.deleted_at = timezone.now()
    project.save()
    assert APIClient().get(DROP, {"token": token}).status_code == 404


def test_a_password_change_ends_every_link(world):
    lab, users, project, _, reader = world
    token = token_of(make_link(api(users["ann"]), lab, reader, project))
    revoke_all(users["ann"], reason="password_changed")
    assert APIClient().get(DROP, {"token": token}).status_code == 410


def test_each_link_is_rate_limited(world, monkeypatch):
    lab, users, project, _, reader = world
    token = token_of(make_link(api(users["ann"]), lab, reader, project))
    monkeypatch.setattr(
        views.DropLinkThrottle, "THROTTLE_RATES", {"instrument_drop_link": "2/hour"}
    )
    codes = [
        APIClient()
        .post(
            DROP,
            {"token": token, "file": a_file(f"{i}.csv"), "acknowledged_notice": "true"},
            format="multipart",
        )
        .status_code
        for i in range(3)
    ]
    assert codes == [201, 201, 429]


def test_software_is_checked_against_the_parsers(world):
    lab, users, _, _, reader = world
    pi = api(users["pi"])
    url = f"/api/labs/{lab.pk}/inventory/{reader.pk}/"
    assert pi.patch(url, {"instrument_software": "nonsense"}, format="json").status_code == 400
    r = pi.patch(url, {"instrument_software": "thermo_nanodrop_one"}, format="json")
    assert r.status_code == 200 and r.json()["instrument_software"] == "thermo_nanodrop_one"
    choices = pi.get("/api/instrument-software/").json()
    assert {"value": "cytiva_unicorn", "label": "Cytiva UNICORN (ÄKTA)"} in choices


def test_demo_seed(world):
    from instruments import demo

    lab, users, *_ = world
    demo.seed(lab, users)
    demo.seed(lab, users)
    names = set(InventoryItem.objects.for_lab(lab).values_list("name", flat=True))
    assert {"NanoDrop One", "ÄKTA pure 25"} <= names
    assert (
        InventoryItem.objects.for_lab(lab).filter(instrument_software="cytiva_unicorn").count() == 1
    )
