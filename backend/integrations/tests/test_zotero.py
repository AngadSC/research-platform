"""Zotero (D115): the provider contract plus the key rules, id parsing, no file requests and the
decision reference append. Every Zotero call is a mocked reply."""

import pytest

from audit.models import AuditEvent
from integrations.http import IntegrationError
from integrations.providers import zotero
from integrations.tests.fake import response
from integrations.tests.provider_contract import KEY, ProviderContract
from provenance.models import Decision

pytestmark = pytest.mark.django_db

API = "https://api.zotero.org"
ITEM = "u123:ABCD2345"
SEARCH = f"{API}/users/123/items/top?limit=20&sort=dateModified&direction=desc"
READ_ONLY = {
    "user": {"library": True, "files": True, "notes": True, "write": False},
    "groups": {"all": {"library": True, "write": False}},
}


def key_reply(access=READ_ONLY):
    return {"key": "x", "userID": 123, "username": "jdoe", "access": access}


def item(key="ABCD2345", version=12, **data):
    return {
        "key": key,
        "version": version,
        "library": {"type": "user", "id": 123, "name": "jdoe"},
        "links": {"alternate": {"href": f"https://www.zotero.org/jdoe/items/{key}"}},
        "meta": {"creatorSummary": "Smith", "parsedDate": "2020-05-01"},
        "data": {
            "key": key,
            "itemType": "journalArticle",
            "title": "Sleep and memory",
            "DOI": "10.1000/xyz123",
            "url": "https://example.org/paper",
            "dateModified": "2024-05-01T10:00:00Z",
            **data,
        },
    }


class TestZotero(ProviderContract):
    provider = zotero.PROVIDER
    item_id = ITEM
    title = "Sleep and memory"
    target = "decision"
    replies = {
        "identity": [("GET", f"{API}/keys/current", 200, key_reply())],
        "item": [("GET", f"{API}/users/123/items/ABCD2345", 200, item())],
        "item_changed": [
            (
                "GET",
                f"{API}/users/123/items/ABCD2345",
                200,
                item(version=13, dateModified="2025-01-01T10:00:00Z"),
            )
        ],
        "item_gone": [("GET", f"{API}/users/123/items/ABCD2345", 404, {})],
        "search": [
            ("GET", f"{SEARCH}&q=data&qmode=titleCreatorYear", 200, [item()]),
            ("GET", f"{API}/users/123/groups?limit=5", 200, [{"id": 456}]),
            (
                "GET",
                f"{API}/groups/456/items/top?limit=20&sort=dateModified&direction=desc"
                "&q=data&qmode=titleCreatorYear",
                200,
                [item("WXYZ6789")],
            ),
        ],
    }

    def test_ids(self):
        ok = zotero.PROVIDER.valid_external_id
        assert ok("u123:ABCD2345") and ok("g9:WXYZ6789")
        bad = ["x1:ABCD2345", "u:ABCD2345", "u1:abcd2345", "u1:ABCD234", "u1:ABCD2340"]
        bad += ["u1:ABCD2345/x", "u1/../x:ABCD2345", "u1:ABCD2345\n"]
        assert not any(ok(b) for b in bad)

    def test_search_covers_the_library_and_groups(self, w):
        self.connect(w)
        self.reply(w, "search")
        found = zotero.PROVIDER.search_items(self.account(w), "data", "decision")
        assert [r["id"] for r in found] == [ITEM, "g456:WXYZ6789"]
        assert found[0]["subtitle"] == "Smith - 2020-05-01"
        assert found[0]["url"] == "https://www.zotero.org/jdoe/items/ABCD2345"

    def test_only_item_records_are_requested_with_the_key_in_a_header(self, w):
        self.create_link(w)
        for method, url, kwargs in w.transport.calls:
            assert method == "GET" and url.startswith(API), url
            assert not any(x in url.lower() for x in ("file", "download", "attachment")), url
            assert KEY not in url and kwargs["headers"]["Zotero-API-Key"] == KEY

    def test_a_key_that_can_write_or_read_nothing_is_refused(self, w):
        for access in (
            {**READ_ONLY, "user": {**READ_ONLY["user"], "write": True}},
            {"user": {"library": True}, "groups": {"7": {"library": True, "write": True}}},
            {"user": {"library": False}},
        ):
            w.transport.on("GET", f"{API}/keys/current", response(200, key_reply(access)))
            resp = w.call("POST", "integrations/zotero/connect/", {"api_key": KEY})
            assert resp.status_code == 400 and resp.json()["code"] == "identity_failed"

    def test_unknown_key_is_403_and_means_invalid_key(self, w):
        self.reply(w, "identity", status=403)
        resp = w.call("POST", "integrations/zotero/connect/", {"api_key": KEY})
        assert resp.status_code == 400 and resp.json()["code"] == "invalid_key"

    def test_other_libraries_bad_ids_and_notes_are_not_fetched(self, w):
        self.connect(w)
        account = self.account(w)
        before = len(w.transport.calls)
        assert zotero.fetch_item(account, "u999:ABCD2345") is None  # not the key's own library
        assert len(w.transport.calls) == before
        with pytest.raises(IntegrationError):
            zotero.fetch_item(account, "u123:../../keys")
        w.transport.on(
            "GET",
            f"{API}/users/123/items/ABCD2345",
            response(200, item(itemType="note", note="<p>x</p>")),
        )
        assert zotero.fetch_item(account, ITEM) is None

    def test_fetch_returns_item_metadata(self, w):
        self.connect(w)
        self.reply(w, "item")
        meta = zotero.fetch_item(self.account(w), ITEM)
        assert (meta["title"], meta["version"]) == ("Sleep and memory", "12")
        assert (meta["doi"], meta["item_url"]) == ("10.1000/xyz123", "https://example.org/paper")
        assert meta["checksum"] == "" and meta["modified_at"].year == 2024

    # ---- decision references (D115)

    def decision(self, w, refs=()):
        return Decision.objects.create(
            lab=w.lab,
            project=w.project,
            title="D",
            decided_on="2030-01-01",
            decided_by=w.pi,
            references=list(refs),
        )

    def link(self, w, decision, key, **data):
        w.transport.on("GET", f"{API}/users/123/items/{key}", response(200, item(key, **data)))
        body = {"provider": "zotero", "external_id": f"u123:{key}", "decision": str(decision.pk)}
        resp = w.call("POST", f"projects/{w.project.pk}/external-links/", body)
        assert resp.status_code == 201, resp.content
        decision.refresh_from_db()
        return resp.json()["version_note"]

    def test_link_appends_a_reference_and_keeps_the_existing_ones(self, w):
        self.connect(w)
        old = {"title": "Old", "url": "", "doi": ""}
        d = self.decision(w, [old])
        assert self.link(w, d, "ABCD2345") == "copied"
        new = {"title": "Sleep and memory", "url": "https://example.org/paper"}
        assert d.references == [old, {**new, "doi": "10.1000/xyz123"}]
        assert AuditEvent.objects.filter(action="decision.updated", lab=w.lab).exists()

    def test_the_same_work_is_not_added_twice(self, w):
        self.connect(w)
        d = self.decision(w, [{"title": "Other title", "url": "", "doi": "10.1000/XYZ123"}])
        assert self.link(w, d, "ABCD2345") == "same"  # same DOI, case aside
        assert len(d.references) == 1
        d2 = self.decision(w)
        assert self.link(w, d2, "ABCD2345") == "copied"
        assert self.link(w, d2, "WXYZ6789") == "same" and len(d2.references) == 1

    def test_unsafe_values_are_cleaned_or_refused(self, w):
        self.connect(w)
        d = self.decision(w)
        note = self.link(
            w,
            d,
            "ABCD2345",
            title="Two\nlines  here",
            url="javascript:alert(1)",
            DOI="https://doi.org/10.1000/abc",
        )
        assert note == "copied"
        assert d.references == [{"title": "Two lines here", "url": "", "doi": "10.1000/abc"}]
        d2 = self.decision(w)
        self.link(w, d2, "WXYZ6789", DOI="not a doi", url="ftp://example.org/x")
        assert d2.references[0]["doi"] == "" and d2.references[0]["url"] == ""

    def test_a_full_list_is_left_alone(self, w):
        self.connect(w)
        full = [{"title": f"R{i}", "url": "", "doi": ""} for i in range(50)]
        d = self.decision(w, full)
        assert self.link(w, d, "ABCD2345") == "kept" and d.references == full

    def test_other_targets_get_nothing(self):
        assert zotero.apply_to_target("manuscript", {"title": "t"}) == {}
