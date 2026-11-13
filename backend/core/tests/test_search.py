"""Lab-wide search (D93): permissions, soft delete, restricted ethics, throttle, text extraction."""

import datetime
import uuid

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.search import AI_TYPES, SPECS, search
from documents.models import Attachment, Document
from documents.services import create_document, save_document
from documents.text import extract_text
from ethics.models import EthicsApproval
from labs.models import LabRole, Meeting
from papers import services as paper_services
from projects.models import ChatMessage, ProjectMembership, ProjectRole, Task
from provenance import services as prov

pytestmark = pytest.mark.django_db
WORD = "zebrafish"
DAY = datetime.date(2030, 1, 1)
LATER = datetime.date(2031, 1, 1)


class W:
    pass


@pytest.fixture
def w(make_lab, make_user, make_project, join):
    w = W()
    w.lab, w.other = make_lab("A"), make_lab("B")
    w.u = {}
    for name, role in [
        ("pi", LabRole.PI),
        ("member", LabRole.MEMBER),
        ("nonproj", LabRole.MEMBER),
        ("viewer", LabRole.VIEWER),
    ]:
        w.u[name] = make_user()
        join(w.u[name], w.lab, role)
    w.u["bpi"] = make_user()
    join(w.u["bpi"], w.other, LabRole.PI)
    w.p1 = make_project(w.lab, f"{WORD} open", description=f"about {WORD}")
    w.p2 = make_project(w.lab, f"{WORD} hidden")  # only the PI sees it
    for who in ("member", "viewer"):
        ProjectMembership.objects.create(
            lab=w.lab, project=w.p1, user=w.u[who], role=ProjectRole.CONTRIBUTOR
        )
    return w


def get(w, who, q=WORD, lab=None, **params):
    client = APIClient()
    client.force_login(w.u[who])
    url = reverse("core:search", kwargs={"lab_id": (lab or w.lab).pk})
    return client.get(url, {"q": q, **params})


def run(w, who, q=WORD, **params):
    r = get(w, who, q, **params)
    assert r.status_code == 200, r.content
    return r.json()["results"]


def titles(hits):
    return {h["title"] for h in hits}


def attach(w, project, name, **kw):
    kw.setdefault("content_type", "text/csv")
    return Attachment.objects.create(
        lab=w.lab,
        project=project,
        storage_key=f"k/{uuid.uuid4()}",
        original_filename=name,
        size_bytes=1,
        sha256="",
        uploaded_by=w.u["pi"],
        **kw,
    )


def meeting(w, title, *people):
    start = datetime.datetime(2030, 1, 1, 9, tzinfo=datetime.UTC)
    m = Meeting.objects.create(
        lab=w.lab,
        title=title,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=1),
        created_by=people[0],
    )
    m.attendees.set(people)
    return m


def say(w, project, who, body):
    return ChatMessage.objects.create(lab=w.lab, project=project, author=w.u[who], body=body)


def approval(w, number, restricted=False, title=f"{WORD} eth", board="Board"):
    a = EthicsApproval.objects.create(
        lab=w.lab,
        approval_number=number,
        board=board,
        title=title,
        approval_date=DAY,
        expiry_date=LATER,
        created_by=w.u["pi"],
        restricted=restricted,
    )
    a.projects.add(w.p2)
    return a


def test_every_type_is_found_with_a_spa_url(w):
    u = w.u["pi"]
    Task.objects.create(lab=w.lab, project=w.p1, title=f"{WORD} task", created_by=u)
    para = [{"type": "paragraph", "content": [{"type": "text", "text": f"the {WORD} ran"}]}]
    doc = create_document(project=w.p1, user=u, title="Notes", content=para)
    ds = prov.create(
        "dataset", project=w.p1, user=u, data={"name": f"{WORD} data", "version_label": "v1"}
    )
    an = prov.create(
        "analysis",
        project=w.p1,
        user=u,
        data={
            "title": f"{WORD} fit",
            "code_repo_url": "https://git.example/x",
            "code_commit": "abc1234",
        },
    )
    prov.create("result", project=w.p1, user=u, data={"title": f"{WORD} out", "analysis": an.pk})
    prov.create("decision", project=w.p1, user=u, data={"title": f"{WORD} choice"})
    prov.create(
        "manuscript",
        project=w.p1,
        user=u,
        data={"title": f"{WORD} paper", "url": "https://x.example/p"},
    )
    prov.create("funding", project=w.p1, user=u, data={"funder": f"{WORD} fund"})
    prov.create("review", project=w.p1, user=u, data={"title": f"{WORD} signoff"})
    paper = paper_services.create_paper(w.lab, user=u, data={"title": f"{WORD} in vivo"})
    paper_services.add_note(paper, author=u, body=f"the {WORD} result")
    approval(w, "Z-1")
    attach(w, w.p1, f"{WORD} raw.csv")
    meeting(w, f"{WORD} sync", w.u["pi"])
    say(w, w.p1, "pi", f"the **{WORD}** ran")
    hits = run(w, "pi")
    assert {h["type"] for h in hits} == {s.type for s in SPECS if s.type != "link"}
    by = {h["type"]: h for h in hits}
    assert by["document"]["url"] == f"/labs/{w.lab.pk}/projects/{w.p1.pk}/documents/{doc.pk}"
    assert by["dataset"]["url"].endswith(f"/workflow/data/datasets/{ds.pk}")
    assert by["ethics"]["project"] is None
    assert by["ethics"]["url"].startswith(f"/labs/{w.lab.pk}/ethics/")
    assert by["document"]["project"] == {"id": str(w.p1.pk), "name": w.p1.name}
    assert by["paper_note"]["title"] == f"Note on {paper.title}"
    assert by["paper_note"]["url"] == f"/labs/{w.lab.pk}/papers/{paper.pk}"
    assert by["file"]["url"] == f"/labs/{w.lab.pk}/projects/{w.p1.pk}/documents"
    assert by["meeting"]["url"] == f"/labs/{w.lab.pk}/calendar"
    assert WORD in by["document"]["snippet"]
    assert by["chat"]["title"] == f"the {WORD} ran"  # markdown marks dropped
    assert by["chat"]["url"] == f"/labs/{w.lab.pk}/projects/{w.p1.pk}/overview?chat=1"
    assert by["chat"]["snippet"] == (w.u["pi"].display_name or w.u["pi"].email)
    assert {h["type"] for h in run(w, "pi", types="task")} == {"task"}


def test_other_lab_content_never_appears(w, make_project):
    make_project(w.other, f"{WORD} lab b")
    assert all("lab b" not in t for t in titles(run(w, "pi")))
    assert get(w, "bpi").status_code == 404  # not a member of Lab A


def test_non_member_project_content_is_hidden(w):
    Task.objects.create(lab=w.lab, project=w.p2, title=f"{WORD} secret", created_by=w.u["pi"])
    assert run(w, "nonproj") == []
    seen = titles(run(w, "member"))
    assert w.p1.name in seen
    assert w.p2.name not in seen and f"{WORD} secret" not in seen
    assert {w.p2.name, f"{WORD} secret"} <= titles(run(w, "pi"))


def test_restricted_ethics_hidden_from_those_who_cannot_see_it(w):
    approval(w, "R-1", restricted=True, title=f"{WORD} restricted")
    approval(w, "R-2", restricted=False, title=f"{WORD} open")
    assert f"{WORD} restricted" not in titles(run(w, "member"))
    assert f"{WORD} open" in titles(run(w, "member"))
    assert f"{WORD} restricted" in titles(run(w, "pi"))
    assert run(w, "member", q="R-1") == []  # number and board are searchable, but not for them
    hit = run(w, "pi", q="R-1")[0]
    assert "R-1" in hit["snippet"]


def test_soft_deleted_items_are_excluded(w):
    doc = create_document(project=w.p1, user=w.u["pi"], title=f"{WORD} doc", content=[])
    a = approval(w, "D-1")
    assert {f"{WORD} doc", f"{WORD} eth", w.p2.name} <= titles(run(w, "pi"))
    now = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    w.p2.deleted_at = now
    w.p2.save()
    Document.objects.for_lab(w.lab).filter(pk=doc.pk).update(deleted_at=now)
    EthicsApproval.objects.for_lab(w.lab).filter(pk=a.pk).update(deleted_at=now)
    assert not {f"{WORD} doc", f"{WORD} eth", w.p2.name} & titles(run(w, "pi"))


def test_lab_viewer_sees_only_what_they_can_view(w):
    Task.objects.create(lab=w.lab, project=w.p2, title=f"{WORD} p2 task", created_by=w.u["pi"])
    assert titles(run(w, "viewer")) == {w.p1.name}


def test_document_text_is_stored_and_kept_current(w):
    def blocks(t):
        return [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "link",
                        "href": "https://h.example",
                        "content": [{"type": "text", "text": t}],
                    }
                ],
                "children": [{"type": "paragraph", "content": [{"type": "text", "text": "child"}]}],
            }
        ]

    assert extract_text(blocks("hello")) == "hello child"
    doc = create_document(project=w.p1, user=w.u["pi"], title="T", content=blocks("alpha"))
    assert doc.search_text == "alpha child"
    assert run(w, "pi", q="alpha")[0]["type"] == "document"
    doc = save_document(
        doc, user=w.u["pi"], title="T", content=blocks("omega"), base_version=doc.version
    )
    assert doc.search_text == "omega child"
    assert run(w, "pi", q="alpha") == []


def test_short_query_is_empty_and_snippets_are_bounded(w):
    assert run(w, "pi", q="z") == []
    assert all(len(h["snippet"]) < 200 for h in run(w, "pi"))


def test_search_is_throttled(w, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "search", "2/minute")
    assert [get(w, "pi").status_code for _ in range(3)] == [200, 200, 429]


def test_files_are_found_by_name_with_the_file_lists_rules(w):
    """Uploads and Drive files by name. A file in a project you are not on, a grant letter (D244)
    and a deleted file stay hidden, exactly as in the project's file list."""
    attach(w, w.p1, "Tester doc.docx")
    google_doc = "application/vnd.google-apps.document"
    attach(w, w.p1, "Tester doc", drive_file_id="d1", content_type=google_doc)
    attach(w, w.p1, "Tester doc grant.pdf", pi_only=True)
    attach(w, w.p2, "Tester doc hidden.pdf")
    gone = attach(w, w.p1, "Tester doc old.pdf")
    Attachment.objects.for_lab(w.lab).filter(pk=gone.pk).update(
        deleted_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    )
    member = run(w, "member", q="tester doc", types="file")
    assert sorted(h["title"] for h in member) == ["Tester doc", "Tester doc.docx"]
    assert all(h["project"]["id"] == str(w.p1.pk) for h in member)
    assert titles(run(w, "viewer", q="tester doc")) == {"Tester doc", "Tester doc.docx"}
    assert run(w, "nonproj", q="tester doc") == []
    assert titles(run(w, "pi", q="tester doc")) == {
        "Tester doc",
        "Tester doc.docx",
        "Tester doc grant.pdf",
        "Tester doc hidden.pdf",
    }


def test_identifying_files_show_in_the_app_but_never_to_ai(w):
    """In the app a flagged file shows to whoever can see it in the file list (it carries its
    badge there); AI search leaves it out, also when its folder is the flagged one."""
    from documents.models import Folder

    attach(w, w.p1, f"{WORD} own.csv", contains_participant_data=True)
    box = Folder.objects.create(
        lab=w.lab, project=w.p1, name="Box", created_by=w.u["pi"], contains_participant_data=True
    )
    attach(w, w.p1, f"{WORD} in box.csv", folder=box)
    attach(w, w.p1, f"{WORD} plain.csv")
    app = {h["title"] for h in run(w, "member", types="file")}
    assert app == {f"{WORD} own.csv", f"{WORD} in box.csv", f"{WORD} plain.csv"}
    ai = {h["title"] for h in search(w.u["member"], w.lab, WORD, {"file"}, for_ai=True)}
    assert ai == {f"{WORD} plain.csv"}


def test_meetings_only_for_the_people_on_them_and_never_for_ai(w):
    meeting(w, f"{WORD} lab meeting", w.u["pi"], w.u["member"])
    assert f"{WORD} lab meeting" in titles(run(w, "member"))
    assert f"{WORD} lab meeting" not in titles(run(w, "nonproj"))
    assert search(w.u["member"], w.lab, WORD, {"meeting"}, for_ai=True) == []


def test_chat_follows_the_chat_endpoint_and_never_reaches_ai(w, make_project):
    say(w, w.p1, "pi", f"{WORD} in open")
    say(w, w.p2, "pi", f"{WORD} in hidden")
    other = make_project(w.other, "B project")
    ChatMessage.objects.create(lab=w.other, project=other, author=w.u["bpi"], body=f"{WORD} in B")
    for who in ("member", "viewer"):  # viewers can read the chat (D206)
        assert titles(run(w, who, types="chat")) == {f"{WORD} in open"}
    assert titles(run(w, "pi", types="chat")) == {f"{WORD} in open", f"{WORD} in hidden"}
    assert run(w, "nonproj", types="chat") == []
    assert "chat" not in AI_TYPES
    assert search(w.u["pi"], w.lab, WORD, {"chat"}, for_ai=True) == []
    assert search(w.u["pi"], w.lab, WORD, None, for_ai=True) != []
    assert all(h["type"] != "chat" for h in search(w.u["pi"], w.lab, WORD, None, for_ai=True))
