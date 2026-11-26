"""Sample registry and freezer boxes: codes, lineage, tubes, import/export, files, handover,
search, viewer read-only, cross-lab and inventory switched off."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from core.search import search
from labs.models import LabMembership, LabRole
from projects.handover import build_report
from projects.models import ProjectMembership, ProjectRole
from samples import demo
from samples.models import Sample, Tube
from samples.serializers import primer_tm

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(make_lab, make_user, make_project, join):
    lab = make_lab("Glyco Lab")
    users = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("ann", LabRole.MEMBER),
        ("bob", LabRole.MEMBER),
        ("vic", LabRole.VIEWER),
    ]:
        users[name] = make_user(display_name=name.title())
        join(users[name], lab, role)
    other = make_lab("Other Lab")
    users["eve"] = make_user(display_name="Eve")
    join(users["eve"], other, LabRole.PI)
    return lab, other, users


def api(user):
    c = APIClient()
    c.force_login(user)
    return c


def u(lab, path=""):
    return f"/api/labs/{lab.pk}/{path}"


def add(lab, user, **data):
    r = api(user).post(u(lab, "samples/"), {"kind": "plasmid", "name": "pX", **data}, format="json")
    assert r.status_code == 201, r.data
    return r.data


def box(lab, user):
    unit = api(user).post(u(lab, "storage/"), {"name": "-80", "temperature": "-80 °C"})
    assert unit.status_code == 201, unit.data
    r = api(user).post(u(lab, "storage/boxes/"), {"unit": unit.data["id"], "name": "Box 1"})
    assert r.status_code == 201, r.data
    return r.data


def place(lab, user, b, sample, row=1, col=1):
    return api(user).post(
        u(lab, "storage/tubes/"),
        {"box": b["id"], "row": row, "col": col, "sample": sample["id"]},
        format="json",
    )


def test_primer_tm():
    assert primer_tm("") is None
    assert primer_tm("ACGTN") is None  # ambiguous base
    assert primer_tm("ACGT") == 12.0  # Wallace: 2*2 + 4*2
    assert primer_tm("ATGAAGCTGCTGGTTAACGGC") == pytest.approx(54.4, abs=0.05)


def test_codes_are_suggested_per_kind_and_unique(world):
    lab, _, users = world
    assert add(lab, users["ann"])["code"] == "P0001"
    assert add(lab, users["ann"], code="p0010")["code"] == "P0010"
    assert add(lab, users["ann"])["code"] == "P0011"
    assert add(lab, users["ann"], kind="strain")["code"] == "S0001"
    codes = api(users["vic"]).get(u(lab, "samples/next-codes/")).data
    assert codes["plasmid"] == "P0012" and codes["primer"] == "PR0001"
    r = api(users["ann"]).post(
        u(lab, "samples/"), {"kind": "plasmid", "name": "dup", "code": "P0010"}, format="json"
    )
    assert r.status_code == 400 and "code" in r.data
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.SAMPLE_CREATED).count() == 4


def test_viewer_reads_but_cannot_write(world):
    lab, _, users = world
    s = add(lab, users["ann"])
    vic = api(users["vic"])
    assert vic.get(u(lab, "samples/")).status_code == 200
    assert vic.get(u(lab, f"samples/{s['id']}/")).status_code == 200
    assert vic.get(u(lab, "storage/")).status_code == 200
    assert vic.post(u(lab, "samples/"), {"kind": "plasmid", "name": "x"}).status_code == 403
    assert vic.patch(u(lab, f"samples/{s['id']}/"), {"name": "y"}).status_code == 403
    assert vic.post(u(lab, "storage/"), {"name": "fridge"}).status_code == 403


def test_other_lab_sees_nothing_and_cannot_link(world):
    lab, other, users = world
    s = add(lab, users["ann"])
    eve = api(users["eve"])
    assert eve.get(u(lab, f"samples/{s['id']}/")).status_code == 404
    assert eve.get(u(other, f"samples/{s['id']}/")).status_code == 404
    theirs = add(other, users["eve"])
    r = api(users["ann"]).patch(
        u(lab, f"samples/{s['id']}/"), {"parents": [theirs["id"]]}, format="json"
    )
    assert r.status_code == 400
    b = box(lab, users["ann"])
    assert place(other, users["eve"], b, theirs).status_code == 400  # not their box


def test_inventory_off_turns_samples_off(world):
    lab, _, users = world
    lab.inventory_enabled = False
    lab.save()
    assert api(users["ann"]).get(u(lab, "samples/")).status_code == 403
    assert api(users["ann"]).get(u(lab, "storage/")).status_code == 403


def test_lineage_refuses_cycles_and_keeps_hidden_links(world, make_project):
    lab, _, users = world
    plasmid = add(lab, users["ann"])
    strain = add(lab, users["ann"], kind="strain", parents=[plasmid["id"]])
    detail = api(users["ann"]).get(u(lab, f"samples/{plasmid['id']}/")).data
    assert [c["code"] for c in detail["children"]] == [strain["code"]]
    r = api(users["ann"]).patch(
        u(lab, f"samples/{plasmid['id']}/"), {"parents": [strain["id"]]}, format="json"
    )
    assert r.status_code == 400
    # A project bob cannot see stays linked when bob edits the list.
    secret = make_project(lab, "Secret")
    ProjectMembership.objects.create(
        lab=lab, project=secret, user=users["ann"], role=ProjectRole.LEAD
    )
    api(users["ann"]).patch(
        u(lab, f"samples/{plasmid['id']}/"), {"projects": [str(secret.pk)]}, format="json"
    )
    assert api(users["bob"]).get(u(lab, f"samples/{plasmid['id']}/")).data["projects"] == []
    api(users["bob"]).patch(u(lab, f"samples/{plasmid['id']}/"), {"projects": []}, format="json")
    assert list(Sample.objects.for_lab(lab).get(pk=plasmid["id"]).projects.all()) == [secret]


def test_tubes_place_move_take_out(world):
    lab, _, users = world
    s = add(lab, users["ann"])
    b = box(lab, users["ann"])
    t = place(lab, users["ann"], b, s)
    assert t.status_code == 201 and t.data["position"] == "A1"
    assert t.data["owner"]["id"] == str(users["ann"].pk)
    assert place(lab, users["bob"], b, s).status_code == 400  # A1 is taken
    assert place(lab, users["bob"], b, s, row=10).status_code == 400  # outside a 9x9 box
    where = api(users["vic"]).get(u(lab, "samples/"), {"q": s["code"]}).data[0]["tubes"]
    assert [(x["box_name"], x["position"]) for x in where] == [("Box 1", "A1")]
    r = api(users["bob"]).patch(u(lab, f"storage/tubes/{t.data['id']}/"), {"row": 2, "col": 3})
    assert r.status_code == 200 and r.data["position"] == "B3"
    moved = AuditEvent.objects.get(lab=lab, action=AuditAction.TUBE_MOVED)
    assert moved.metadata["from"] == "Box 1 A1" and moved.metadata["to"] == "Box 1 B3"
    # a sample with a tube, and a box with a tube, cannot be deleted
    assert api(users["ann"]).delete(u(lab, f"samples/{s['id']}/")).status_code == 409
    assert api(users["ann"]).delete(u(lab, f"storage/boxes/{b['id']}/")).status_code == 409
    assert api(users["ann"]).delete(u(lab, f"storage/tubes/{t.data['id']}/")).status_code == 204
    assert api(users["ann"]).delete(u(lab, f"samples/{s['id']}/")).status_code == 204
    assert api(users["ann"]).get(u(lab, f"samples/{s['id']}/")).status_code == 404
    actions = set(AuditEvent.objects.filter(lab=lab).values_list("action", flat=True))
    assert {"tube.placed", "tube.moved", "tube.removed", "sample.deleted"} <= actions


def test_import_preview_then_commit_and_export(world):
    lab, _, users = world
    add(lab, users["ann"])  # P0001
    text = (
        "Kind,Code,Name,Sequence,Owner\n"
        "Plasmid,,pNew,,Ann\nprimer,,fwd,acgt acgt,\nCell line,,HEK,,\n"
    )

    def post(commit):
        f = SimpleUploadedFile("s.csv", text.encode(), content_type="text/csv")
        return api(users["ann"]).post(u(lab, "samples/import/"), {"file": f, "commit": commit})

    preview = post(False)
    assert preview.status_code == 200, preview.data
    assert [r["code"] for r in preview.data["rows"]] == ["P0002", "PR0001", "CL0001"]
    assert preview.data["ignored_columns"] == ["owner"]
    assert Sample.objects.for_lab(lab).count() == 1
    assert post(True).data["imported"] == 3
    assert Sample.objects.for_lab(lab).get(code="PR0001").sequence == "ACGTACGT"
    text = "Kind,Name\nfreezer,bad\n"
    assert post(True).status_code == 400
    r = api(users["vic"]).get(u(lab, "samples/export/"))
    body = b"".join(r.streaming_content if r.streaming else [r.content]).decode("utf-8-sig")
    assert "P0002" in body and "CL0001" in body
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.SAMPLES_EXPORTED).exists()
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.SAMPLES_IMPORTED).count() == 1


def test_files_upload_open_and_remove(world):
    lab, other, users = world
    s = add(lab, users["ann"])
    f = SimpleUploadedFile("map.png", b"\x89PNG fake", content_type="image/png")
    r = api(users["ann"]).post(
        u(lab, f"samples/{s['id']}/files/"), {"file": f, "acknowledged_notice": "true"}
    )
    assert r.status_code == 201, r.data
    fid = r.data["id"]
    files = api(users["vic"]).get(u(lab, f"samples/{s['id']}/")).data["files"]
    assert [x["name"] for x in files] == ["map.png"] and files[0]["on_sample"]
    assert api(users["vic"]).get(u(lab, f"samples/{s['id']}/files/{fid}/")).status_code == 200
    assert api(users["eve"]).get(u(lab, f"samples/{s['id']}/files/{fid}/")).status_code == 404
    assert api(users["vic"]).delete(u(lab, f"samples/{s['id']}/files/{fid}/")).status_code == 403
    assert api(users["ann"]).delete(u(lab, f"samples/{s['id']}/files/{fid}/")).status_code == 204
    assert api(users["ann"]).get(u(lab, f"samples/{s['id']}/")).data["files"] == []


def test_handover_lists_samples_and_tubes(world):
    lab, _, users = world
    s = add(lab, users["ann"], owner=str(users["bob"].pk))
    place(lab, users["bob"], box(lab, users["pi"]), s)
    membership = LabMembership.objects.for_lab(lab).get(user=users["bob"])
    report = build_report(requester=users["pi"], lab=lab, membership=membership)
    section = next(x for x in report["sections"] if x["key"] == "samples")
    assert [i["kind"] for i in section["items"]] == ["sample", "tube"]
    lab.inventory_enabled = False
    lab.save()
    report = build_report(requester=users["pi"], lab=lab, membership=membership)
    assert "samples" not in [x["key"] for x in report["sections"]]


def test_search_finds_samples_by_code_not_for_ai(world):
    lab, _, users = world
    s = add(lab, users["ann"], name="pCW-MalE-CST06")
    hits = search(users["vic"], lab, s["code"])
    assert [h["type"] for h in hits] == ["sample"]
    assert hits[0]["url"] == f"/labs/{lab.pk}/samples/{s['id']}"
    assert search(users["vic"], lab, s["code"], for_ai=True) == []
    assert search(users["eve"], lab, s["code"]) == []


def test_demo_seed(world):
    lab, _, users = world
    demo.seed(lab, {"pi": users["pi"], "lead": users["ann"], "student": users["bob"]})
    assert Sample.objects.for_lab(lab).filter(kind="plasmid").count() == 2
    assert Tube.objects.for_lab(lab).count() == 7


# ---------------------------------------------------------------- review fixes (D386)


def _upload(lab, user, s, **extra):
    f = SimpleUploadedFile("map.png", b"\x89PNG fake", content_type="image/png")
    return api(user).post(
        u(lab, f"samples/{s['id']}/files/"), {"file": f, "acknowledged_notice": "true", **extra}
    )


def test_m1_sample_files_keep_the_participant_flag_and_refuse_pi_only(world):
    from assistant.privacy import ai_visible, is_flagged
    from documents.models import Attachment

    lab, _, users = world
    s = add(lab, users["ann"])
    r = _upload(lab, users["ann"], s, contains_participant_data="true")
    assert r.status_code == 201, r.data
    att = Attachment.objects.for_lab(lab).get(pk=r.data["id"])
    assert att.contains_participant_data and is_flagged(att) and not att.pi_only
    assert not ai_visible(Attachment.objects.for_lab(lab).filter(pk=att.pk)).exists()
    assert _upload(lab, users["ann"], s).data["contains_participant_data"] is False
    # a PI-only file belongs on a project: refuse, never drop the box without a word
    before = Attachment.objects.for_lab(lab).count()
    r = _upload(lab, users["ann"], s, pi_only="true")
    assert r.status_code == 400 and "pi_only" in r.json()
    assert Attachment.objects.for_lab(lab).count() == before


def test_m2_file_audit_names_the_sample_and_delete_audits_each_file(world, monkeypatch):
    from documents.models import Attachment
    from integrations.models import ConnectedAccount
    from integrations.providers import google_drive

    lab, _, users = world
    s = add(lab, users["ann"])
    r = _upload(lab, users["ann"], s)
    ConnectedAccount.objects.create(
        lab=lab,
        user=users["ann"],
        provider="google_drive",
        external_account_id="p1",
        connected_at=timezone.now(),
    )
    monkeypatch.setattr(
        google_drive,
        "fetch_item",
        lambda account, file_id: {
            "title": "Gel.png",
            "url": "https://drive.google.com/file/d/1AbC-dEf_9/view",
            "mime_type": "image/png",
        },
    )
    drive = api(users["ann"]).post(
        u(lab, f"samples/{s['id']}/files/"), {"drive_file_id": "1AbC-dEf_9"}
    )
    assert drive.status_code == 201, drive.data
    uploaded = AuditEvent.objects.filter(lab=lab, action=AuditAction.ATTACHMENT_UPLOADED)
    assert sorted(e.metadata["sample"] for e in uploaded) == [s["id"], s["id"]]
    assert api(users["ann"]).delete(u(lab, f"samples/{s['id']}/")).status_code == 204
    deleted = AuditEvent.objects.filter(lab=lab, action=AuditAction.ATTACHMENT_DELETED)
    assert deleted.count() == 2 and {str(e.target_id) for e in deleted} == {
        r.data["id"],
        drive.data["id"],
    }
    assert not Attachment.objects.for_lab(lab).filter(deleted_at__isnull=True).exists()
    assert AuditEvent.objects.filter(lab=lab, action=AuditAction.SAMPLE_DELETED).count() == 1


def test_m3_box_resize_and_sample_delete_take_their_locks(world, monkeypatch):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    lab, _, users = world
    s = add(lab, users["ann"])
    b = box(lab, users["pi"])
    with CaptureQueriesContext(connection) as q:
        r = api(users["ann"]).patch(u(lab, f"storage/boxes/{b['id']}/"), {"rows": 4}, format="json")
    assert r.status_code == 200
    assert sum("FOR UPDATE" in x["sql"] and "storagebox" in x["sql"] for x in q) >= 1
    with CaptureQueriesContext(connection) as q:
        assert place(lab, users["ann"], b, s).status_code == 201
    assert any("FOR UPDATE" in x["sql"] and "samples_sample" in x["sql"] for x in q)
    api(users["ann"]).delete(u(lab, f"storage/tubes/{Tube.objects.for_lab(lab).get().pk}/"))
    with CaptureQueriesContext(connection) as q:
        assert api(users["ann"]).delete(u(lab, f"samples/{s['id']}/")).status_code == 204
    assert any("FOR UPDATE" in x["sql"] and "samples_sample" in x["sql"] for x in q)


def test_m4_sample_uploads_are_refused_by_length_before_the_body_is_read(world, settings):
    lab, _, users = world
    s = add(lab, users["ann"])
    settings.ATTACHMENT_MAX_BYTES = 1000
    for path in (f"samples/{s['id']}/files/", "samples/import/"):
        r = api(users["ann"]).post(
            u(lab, path), data=b"x" * 200_000, content_type="multipart/form-data; boundary=b"
        )
        assert r.status_code == 413, path
