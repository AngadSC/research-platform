import pytest

from audit.models import AuditAction, AuditEvent
from participants.models import ComponentFile, Participant, ParticipantComponent

pytestmark = pytest.mark.django_db

DOC = "https://docs.google.com/document/d/abcdefghij12345/edit"
SHEET = (
    "Code,Language,English narrative,Transcript,Translation\n"
    f"P-001,Punjabi,done,{DOC},\n"
    "P-002,Spanish,in progress,,\n"
    "P-003,French,,,\n"
    "P-004,,,,\n"
)
MAP = {
    "code": "Code",
    "group": "Language",
    "components": [
        {"column": "English narrative"},
        {"column": "Transcript"},
        {"column": "Translation"},
    ],
}


def post(w, csv, mapping=None, dry_run=True, client=None):
    return (client or w.client()).post(
        f"{w.base}/participant-imports/",
        {"csv": csv, "mapping": mapping or MAP, "dry_run": dry_run},
        "json",
    )


def test_preview_shows_headers_links_and_flags_name_columns(w):
    r = w.client().post(
        f"{w.base}/participant-imports/preview/",
        {"csv": SHEET.replace("Language", "Child name")},
        "json",
    )
    body = r.json()
    assert r.status_code == 200 and body["total"] == 4
    assert body["blocked_headers"] == ["Child name"]
    assert body["link_columns"] == ["Transcript"]


def test_dry_run_saves_nothing_and_matches_the_real_run(w):
    dry = post(w, SHEET).json()
    assert dry["dry_run"] and dry["created"] == 3  # P-004 has no data
    assert dry["skipped"] == 1 and dry["links"] == 1
    assert not Participant.objects.for_lab(w.lab).exists()
    real = post(w, SHEET, dry_run=False).json()
    assert (real["created"], real["skipped"], real["links"]) == (3, 1, 1)
    assert Participant.objects.for_lab(w.lab).count() == 3
    cell = ParticipantComponent.objects.for_lab(w.lab).get(
        participant__code="P-001", component__key="transcript"
    )
    assert cell.files.get().provider == "google_drive" and cell.files.get().role == "transcript"
    done = ParticipantComponent.objects.for_lab(w.lab).get(
        participant__code="P-001", component__key="english-narrative"
    )
    assert done.status == "complete" and done.verified_at


def test_reimporting_updates_and_never_duplicates(w):
    post(w, SHEET, dry_run=False)
    again = post(w, SHEET, dry_run=False).json()
    assert again["created"] == 0
    assert Participant.objects.for_lab(w.lab).count() == 3
    assert ComponentFile.objects.for_lab(w.lab).count() == 1


def test_a_name_like_column_or_code_is_refused_and_not_logged(w):
    r = post(w, SHEET.replace("Language", "Email"), {**MAP, "group": "Email"})
    assert r.status_code == 400
    bad = (
        "Code,Language,Transcript\nJane Doe,Punjabi,done\n"
        "P-004,jane@example.com,done\nP-005,Punjabi,done\n"
    )
    out = post(
        w,
        bad,
        {"code": "Code", "group": "Language", "components": [{"column": "Transcript"}]},
        dry_run=False,
    )
    body = out.json()
    assert body["created"] == 1 and body["skipped"] == 2
    text = str(body)
    assert "Jane" not in text and "jane@" not in text
    event = AuditEvent.objects.filter(action=AuditAction.PARTICIPANT_IDENTIFIER_BLOCKED).last()
    assert "Jane" not in str(event.metadata) and "jane@" not in str(event.metadata)


def test_duplicate_blank_and_empty_rows_are_reported(w):
    sheet = "Code,Transcript\nP-001,done\nP-001,done\n,done\nP-002,\n"
    body = post(w, sheet, {"code": "Code", "components": [{"column": "Transcript"}]}).json()
    assert body["created"] == 1 and body["skipped"] == 3
    messages = " ".join(a["message"] for a in body["attention"])
    assert "earlier in the file" in messages and "No participant code" in messages
    assert "No data" in messages


def test_limits(w):
    big = "Code,T\n" + "".join(f"P-{i},done\n" for i in range(1001))
    r = post(w, big, {"code": "Code", "components": [{"column": "T"}]})
    assert r.status_code == 400


def test_only_a_lead_imports_and_a_viewer_is_refused(w):
    from projects.models import ProjectRole

    c = w.client(w.member(ProjectRole.CONTRIBUTOR))
    assert post(w, SHEET, client=c).status_code == 403


def test_undo_removes_what_the_import_made_and_only_the_latest(w):
    first = post(w, SHEET, dry_run=False).json()
    second = post(
        w,
        "Code,Transcript\nP-050,done\n",
        {"code": "Code", "components": [{"column": "Transcript"}]},
        dry_run=False,
    ).json()
    history = w.client().get(f"{w.base}/participant-imports/").json()
    assert [h["can_undo"] for h in history] == [True, False]
    stale = w.client().post(f"{w.base}/participant-imports/{first['run']}/undo/")
    assert stale.status_code == 409
    ok = w.client().post(f"{w.base}/participant-imports/{second['run']}/undo/")
    assert ok.status_code == 200
    assert not Participant.objects.for_lab(w.lab).filter(code="P-050").exists()
    assert Participant.objects.for_lab(w.lab).filter(code="P-001").exists()


def test_matching_drive_files_by_name_with_confidence(w):
    w.add("P-017", "P-018")
    w.column("Transcript")
    w.column("Translation")
    files = [
        {"name": "P-017_Transcript.docx", "url": DOC},
        {"name": "P-018_translation", "url": DOC + "2"},
        {"name": "P-099_Transcript", "url": DOC + "3"},
        {"name": "random notes", "url": DOC + "4"},
    ]
    r = w.client().post(
        f"{w.base}/participant-file-matches/",
        {"files": files, "pattern": "P-{number}_{component}"},
        "json",
    )
    by_name = {m["name"]: m for m in r.json()["matches"]}
    assert by_name["P-017_Transcript.docx"]["confidence"] == "high"
    assert by_name["P-018_translation"]["confidence"] == "high"
    assert by_name["P-099_Transcript"]["confidence"] == "low"  # no such participant
    assert by_name["random notes"]["confidence"] == "none"
    items = [
        {"participant": m["participant"], "component": m["component"], "url": m["url"]}
        for m in by_name.values()
        if m["confidence"] == "high"
    ]
    out = w.client().post(f"{w.base}/participant-file-matches/attach/", {"items": items}, "json")
    assert out.json() == {"attached": 2, "skipped": 0}
    again = w.client().post(f"{w.base}/participant-file-matches/attach/", {"items": items}, "json")
    assert again.json() == {"attached": 0, "skipped": 2}  # never duplicates a link


def test_an_attached_title_that_looks_like_contact_details_is_refused(w):
    (p,) = w.add("P-017")
    c = w.column("Transcript")
    r = w.client().post(
        f"{w.base}/participant-file-matches/attach/",
        {
            "items": [
                {
                    "participant": p["id"],
                    "component": c["id"],
                    "url": DOC,
                    "title": "me@example.com",
                }
            ]
        },
        "json",
    )
    assert r.status_code == 400


def test_link_health_counts_and_flags_a_document_changed_after_it_was_verified(w):
    import datetime

    from django.utils import timezone

    (p,) = w.add("P-001")
    c = w.column()
    cell = (
        w.client()
        .patch(f"{w.base}/participants/{p['id']}/cells/{c['id']}/", {"status": "complete"}, "json")
        .json()
    )
    f = (
        w.client()
        .post(
            f"{w.base}/participant-cells/{cell['id']}/files/",
            {"url": DOC, "link_state": "ok"},
            "json",
        )
        .json()
    )
    health = w.client().get(f"{w.base}/participant-link-health/").json()
    assert health["counts"]["total"] == 1 and health["counts"]["changed_since_verified"] == 0
    ComponentFile.objects.for_lab(w.lab).filter(pk=f["id"]).update(
        last_modified_remote=timezone.now() + datetime.timedelta(days=1), link_state="not_found"
    )
    health = w.client().get(f"{w.base}/participant-link-health/").json()
    assert health["counts"]["problems"] == 1 and health["counts"]["changed_since_verified"] == 1
    assert health["problems"][0]["participant"] == "P-001"
    cells = w.client().get(f"{w.base}/participant-cells/").json()
    assert cells[0]["changed_since_verified"] is True and cells[0]["status"] == "complete"
    # confirming again clears the flag
    w.client().patch(
        f"{w.base}/participants/{p['id']}/cells/{c['id']}/", {"verified": True}, "json"
    )
    # (the flag compares against the new verified time, so a later edit would flag it again)
    cells = w.client().get(f"{w.base}/participant-cells/").json()
    assert cells[0]["verified_at"]


def test_refreshing_links_needs_a_connected_google_account(w):
    r = w.client().post(f"{w.base}/participant-link-health/refresh/")
    assert r.status_code == 404


def test_a_sheet_with_blank_and_repeated_headers_imports(w):
    """Real sheets repeat a heading under each character and leave spacer columns blank."""
    sheet = (
        "Source\tParticipant ID\tHome Language\t\tOutcome\tOutcome\tRecording\n"
        f"MCHB\t2A1\tEnglish, Amharic\t\t\t\t{DOC}\n"
        "ABC\t1H1\tEnglish, Arabic\t\t\t\tno data\n"
    )
    pv = w.client().post(f"{w.base}/participant-imports/preview/", {"csv": sheet}, "json").json()
    assert pv["headers"] == [
        "Source",
        "Participant ID",
        "Home Language",
        "Column 4",
        "Outcome",
        "Outcome (2)",
        "Recording",
    ]
    mapping = {
        "code": "Participant ID",
        "group": "Home Language",
        "components": [{"column": "Recording"}, {"column": "Outcome"}, {"column": "Outcome (2)"}],
    }
    out = post(w, sheet, mapping, dry_run=False)
    assert out.status_code == 200, out.content
    body = out.json()
    assert body["created"] == 2 and body["links"] == 1
    assert Participant.objects.for_lab(w.lab).filter(code="2A1", group="English, Amharic").exists()
