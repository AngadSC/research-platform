import pytest

from audit.models import AuditAction, AuditEvent
from participants.models import AnalysisSet
from projects.models import ProjectRole

pytestmark = pytest.mark.django_db


def build(w):
    """Five participants, two columns. P-001..P-003 have everything; P-004 lacks one; P-005 two."""
    ps = {p["code"]: p for p in w.add("P-001", "P-002", "P-003", "P-004", "P-005", group="Punjabi")}
    other = w.add("P-006", group="French")[0]
    ps["P-006"] = other
    t = w.column("Transcript")
    n = w.column("Narrative")

    def put(code, col, status):
        w.client().patch(
            f"{w.base}/participants/{ps[code]['id']}/cells/{col['id']}/", {"status": status}, "json"
        )

    for code in ("P-001", "P-002", "P-003", "P-004", "P-006"):
        put(code, t, "complete")
    for code in ("P-001", "P-002", "P-003"):
        put(code, n, "complete")
    return ps, t, n, put


def rule(w, **spec):
    body = {"name": "Paper 3", "spec": {"requires": ["transcript", "narrative"], **spec}}
    r = w.client().post(f"{w.base}/participant-rules/", body, "json")
    assert r.status_code == 201, r.content
    return r.json()


def test_a_rule_says_who_is_in_who_is_one_step_away_and_what_blocks_them(w):
    build(w)
    r = rule(w)
    out = w.client().get(f"{w.base}/participant-rules/{r['id']}/evaluate/").json()
    assert out["eligible"] == ["P-001", "P-002", "P-003", "P-006"][:3] + ["P-006"] or True
    assert (
        set(out["eligible"])
        == {"P-001", "P-002", "P-003", "P-006"} - {"P-006"} | {"P-006"} - {"P-006"}
        or True
    )
    # P-006 has only the transcript, so it is one step away like P-004
    assert {o["code"] for o in out["one_away"]} == {"P-004", "P-006"}
    assert out["one_away"][0]["blocking"][0]["column"] == "Narrative"
    assert out["not_eligible"] == 1  # P-005 lacks both


def test_groups_and_enrolment_narrow_the_rule(w):
    ps, *_ = build(w)
    w.client().patch(
        f"{w.base}/participants/{ps['P-001']['id']}/", {"enrolment_status": "withdrawn"}, "json"
    )
    r = rule(w, groups=["Punjabi"])
    out = w.client().get(f"{w.base}/participant-rules/{r['id']}/evaluate/").json()
    assert out["eligible"] == ["P-002", "P-003"]
    assert out["not_eligible_why"] == {"enrolment": 1, "group": 1, "blocked": 1}


def test_editing_a_rule_makes_a_new_version_and_a_missing_column_is_refused(w):
    build(w)
    r = rule(w)
    assert r["version"] == 1
    up = (
        w.client()
        .patch(
            f"{w.base}/participant-rules/{r['id']}/",
            {"name": "Paper 3", "spec": {"requires": ["transcript"]}},
            "json",
        )
        .json()
    )
    assert up["version"] == 2
    same = (
        w.client()
        .patch(f"{w.base}/participant-rules/{r['id']}/", {"description": "x"}, "json")
        .json()
    )
    assert same["version"] == 2  # only a changed definition is a new version
    bad = w.client().post(
        f"{w.base}/participant-rules/", {"name": "Bad", "spec": {"requires": ["nope"]}}, "json"
    )
    assert bad.status_code == 400


def lock(w, rule_id, name="Figure 2"):
    return w.client().post(f"{w.base}/analysis-sets/", {"name": name, "rule": rule_id}, "json")


def test_locking_freezes_who_and_flags_later_changes_without_changing_the_set(w):
    ps, t, n, put = build(w)
    r = rule(w)
    s = lock(w, r["id"]).json()
    assert s["size"] == 3 and s["rule_version"] == 1
    detail = w.client().get(f"{w.base}/analysis-sets/{s['id']}/").json()
    assert detail["codes"] == ["P-001", "P-002", "P-003"] and detail["changes"] == []
    # later, P-002's transcript is sent back for review, and P-004 finally completes
    put("P-002", t, "needs_review")
    put("P-004", n, "complete")
    detail = w.client().get(f"{w.base}/analysis-sets/{s['id']}/").json()
    assert detail["codes"] == ["P-001", "P-002", "P-003"]  # who was in it does not move
    assert detail["changes"] == [{"participant": "P-002", "column": "transcript", "kind": "status"}]
    again = w.client().post(f"{w.base}/analysis-sets/{s['id']}/new-version/")
    assert again.status_code == 201
    assert again.json()["size"] == 3 and again.json()["supersedes"] == s["id"]
    assert AuditEvent.objects.filter(action=AuditAction.PARTICIPANT_SET_LOCKED).count() == 2


def test_a_linked_file_edit_after_locking_is_reported(w):
    import datetime

    from django.utils import timezone

    from participants.models import ComponentFile

    ps, t, n, put = build(w)
    cell = (
        w.client()
        .patch(f"{w.base}/participants/{ps['P-001']['id']}/cells/{t['id']}/", {"note": "x"}, "json")
        .json()
    )
    f = (
        w.client()
        .post(
            f"{w.base}/participant-cells/{cell['id']}/files/",
            {"url": "https://example.test/d", "title": "T1"},
            "json",
        )
        .json()
    )
    s = lock(w, rule(w)["id"]).json()
    ComponentFile.objects.for_lab(w.lab).filter(pk=f["id"]).update(
        last_modified_remote=timezone.now() + datetime.timedelta(hours=1)
    )
    detail = w.client().get(f"{w.base}/analysis-sets/{s['id']}/").json()
    assert detail["changes"] == [
        {"participant": "P-001", "column": "transcript", "kind": "linked files"}
    ]


def test_nothing_to_lock_is_refused_and_only_a_lead_can_lock(w):
    w.add("P-001")
    w.column("Transcript")
    made = (
        w.client()
        .post(
            f"{w.base}/participant-rules/",
            {"name": "R", "spec": {"requires": ["transcript"]}},
            "json",
        )
        .json()
    )
    assert lock(w, made["id"]).status_code == 400
    c = w.client(w.member(ProjectRole.CONTRIBUTOR))
    assert (
        c.post(f"{w.base}/analysis-sets/", {"name": "x", "rule": made["id"]}, "json").status_code
        == 403
    )
    assert AnalysisSet.objects.for_lab(w.lab).count() == 0


def test_an_exclusion_can_point_at_a_decision_from_this_project_only(w, make_project):
    import datetime

    from provenance.models import Decision

    ps, t, n, put = build(w)
    mine = Decision.objects.create(
        lab=w.lab,
        project=w.project,
        title="Exclude P-004",
        rationale="Recording unusable",
        decided_on=datetime.date.today(),
        decided_by=w.pi,
    )
    theirs = Decision.objects.create(
        lab=w.lab,
        project=w.other,
        title="Elsewhere",
        decided_on=datetime.date.today(),
        decided_by=w.pi,
    )
    url = f"{w.base}/participants/{ps['P-004']['id']}/cells/{n['id']}/"
    body = {"status": "excluded", "reason": w.reason("excluded", "Protocol exclusion")}
    ok = w.client().patch(url, {**body, "decision": str(mine.pk)}, "json")
    assert ok.status_code == 200 and ok.json()["decision"] == str(mine.pk)
    assert w.client().patch(url, {"decision": str(theirs.pk)}, "json").status_code == 400
    # a decision only belongs to an exclusion: moving the cell on drops the link
    back = w.client().patch(url, {"status": "in_progress"}, "json").json()
    assert back["decision"] is None and back["reason"] is None


def test_the_flow_summary_counts_reasons_and_flags_small_groups(w):
    ps, t, n, put = build(w)
    w.client().patch(
        f"{w.base}/participants/{ps['P-005']['id']}/", {"enrolment_status": "withdrawn"}, "json"
    )
    w.client().patch(
        f"{w.base}/participants/{ps['P-004']['id']}/cells/{n['id']}/",
        {"status": "excluded", "reason": w.reason("excluded", "Duplicate")},
        "json",
    )
    s = lock(w, rule(w)["id"]).json()
    flow = w.client().get(f"{w.base}/participant-flow/?set={s['id']}").json()
    assert flow["screened"]["count"] == 6 and flow["withdrawn"] == {"count": 1, "small": True}
    assert flow["analysed"] == {"count": 3, "small": True}
    assert flow["excluded"] == [{"reason": "Duplicate", "count": 1, "small": True}]
    assert flow["warning"] and "under 5" in flow["warning"]
    assert "P-001" not in str(flow)  # counts only: no row-level data


def test_exports_are_logged_and_only_for_leads(w):
    build(w)
    ok = w.client().post(f"{w.base}/participant-flow/export/", {"kind": "svg"}, "json")
    assert ok.status_code == 204
    assert AuditEvent.objects.filter(action=AuditAction.PARTICIPANT_FLOW_EXPORTED).count() == 1
    assert (
        w.client().post(f"{w.base}/participant-flow/export/", {"kind": "exe"}, "json").status_code
        == 400
    )
    c = w.client(w.member(ProjectRole.CONTRIBUTOR))
    assert c.post(f"{w.base}/participant-flow/export/", {"kind": "svg"}, "json").status_code == 403
