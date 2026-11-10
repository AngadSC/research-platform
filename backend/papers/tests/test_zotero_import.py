"""Importing papers from a person's own Zotero library (D242). Every Zotero reply is faked."""

import pytest
from rest_framework.test import APIClient

from audit.models import AuditAction, AuditEvent
from integrations import http
from integrations.models import ConnectedAccount
from integrations.tests.fake import FakeTransport, response
from papers.models import Paper

pytestmark = pytest.mark.django_db

API = "https://api.zotero.org"
ITEM_URL = f"{API}/users/7/items/ABCD2345"
ITEM_ID = "u7:ABCD2345"


@pytest.fixture
def transport(monkeypatch):
    fake = FakeTransport()
    monkeypatch.setattr(http, "_session", fake)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(http, "_resolve", lambda host: ["93.184.216.34"])
    return fake


@pytest.fixture
def world(make_lab, make_user, join):
    lab = make_lab()
    user = make_user()
    join(user, lab, "member")
    return lab, user


def connect(lab, user):
    row = ConnectedAccount(
        lab=lab,
        user=user,
        provider="zotero",
        external_account_id="7",
        external_email="jdoe",
        connected_at="2030-01-01T00:00:00Z",
    )
    row.set_tokens(access="key", refresh="", expires_at=None)
    row.save()


def item(**data):
    return {
        "key": "ABCD2345",
        "version": 3,
        "library": {"type": "user", "id": 7},
        "links": {"alternate": {"href": "https://www.zotero.org/jdoe/items/ABCD2345"}},
        "meta": {"parsedDate": "2021-06-01"},
        "data": {
            "key": "ABCD2345",
            "itemType": "journalArticle",
            "title": "Sleep and memory",
            "creators": [
                {"creatorType": "author", "lastName": "Smith", "firstName": "Ann"},
                {"creatorType": "author", "name": "WHO"},
                {"creatorType": "editor", "lastName": "Nope"},
            ],
            "publicationTitle": "Sleep Journal",
            "DOI": "https://doi.org/10.1000/xyz",
            "url": "https://example.org/p",
            "abstractNote": "An abstract.",
            "dateModified": "2030-01-01T00:00:00Z",
            **data,
        },
    }


def post(user, lab, ids):
    c = APIClient()
    c.force_authenticate(user)
    return c.post(f"/api/labs/{lab.pk}/papers/zotero/", {"ids": ids}, format="json")


def test_import_fills_the_library_and_is_audited(world, transport):
    lab, user = world
    connect(lab, user)
    transport.on("GET", ITEM_URL, response(200, item()))
    assert post(user, lab, [ITEM_ID]).json() == {"created": 1, "skipped": 0}
    paper = Paper.objects.for_lab(lab).get()
    assert paper.authors == ["Smith, Ann", "WHO,"]
    assert (paper.year, paper.venue, paper.doi) == (2021, "Sleep Journal", "10.1000/xyz")
    assert paper.added_by == user
    event = AuditEvent.objects.get(action=AuditAction.PAPERS_IMPORTED)
    assert event.metadata == {"provider": "zotero", "created": 1, "skipped": 0}


def test_the_same_paper_is_not_added_twice(world, transport):
    lab, user = world
    connect(lab, user)
    transport.on("GET", ITEM_URL, response(200, item()))
    post(user, lab, [ITEM_ID])
    assert post(user, lab, [ITEM_ID]).json() == {"created": 0, "skipped": 1}
    assert Paper.objects.for_lab(lab).count() == 1


def test_notes_and_another_persons_library_are_skipped(world, transport):
    lab, user = world
    connect(lab, user)
    transport.on("GET", ITEM_URL, response(200, item(itemType="note")))
    assert post(user, lab, [ITEM_ID, "u9:ABCD2345"]).json() == {"created": 0, "skipped": 2}
    assert len(transport.calls) == 1  # the other library was never asked for


def test_no_key_is_a_404_and_another_members_key_is_not_used(world, transport, make_user, join):
    lab, user = world
    other = make_user()
    join(other, lab, "member")
    connect(lab, other)
    assert post(user, lab, [ITEM_ID]).status_code == 404
    assert transport.calls == []


def test_zotero_being_down_is_a_clean_502(world, transport):
    lab, user = world
    connect(lab, user)
    transport.on("GET", ITEM_URL, response(500, {}))
    assert post(user, lab, [ITEM_ID]).status_code == 502
    assert Paper.objects.for_lab(lab).count() == 0
