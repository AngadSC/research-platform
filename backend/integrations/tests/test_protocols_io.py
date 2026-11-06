"""protocols.io provider (D113): the contract plus id, URL and metadata-only rules. All HTTP is
the fake transport; nothing leaves the process."""

import re
from urllib.parse import urlencode

import pytest

from integrations.http import IntegrationError
from integrations.providers import protocols_io as pio
from integrations.tests.fake import response
from integrations.tests.provider_contract import KEY, ProviderContract

pytestmark = pytest.mark.django_db

SLUG = "sleep-protocol-bd5km2"
PROFILE = "https://www.protocols.io/api/v3/session/profile"
ITEM = f"{pio.API}/{SLUG}?{urlencode({'fields': pio.FIELDS})}"


def search_url(flt, key="data"):
    return (
        f"{pio.API}?{urlencode({'filter': flt, 'key': key, 'page_size': 20, 'fields': pio.FIELDS})}"
    )


def protocol(**over):
    return {
        "id": 98765,
        "title": "Sleep protocol",
        "uri": SLUG,
        "version_id": 1,
        "doi": "dx.doi.org/10.17504/protocols.io.bd5km2",
        "created_on": 1700000000,
        "published_on": 1700100000,
        "last_modified": 1700200000,
        **over,
    }


class TestProtocolsIo(ProviderContract):
    provider = pio.PROVIDER
    item_id = SLUG
    item_url = f"https://www.protocols.io/view/{SLUG}"
    title = "Sleep protocol"
    target = "document"
    replies = {
        "identity": [("GET", PROFILE, 200, {"user": {"id": 7, "username": "angad"}})],
        "item": [("GET", ITEM, 200, {"payload": protocol()})],
        "item_changed": [
            ("GET", ITEM, 200, {"payload": protocol(version_id=2, last_modified=1710000000)})
        ],
        "item_gone": [("GET", ITEM, 404, {"error_message": "not found"})],
        "search": [
            ("GET", search_url("user_private"), 200, {"items": [protocol()]}),
            ("GET", search_url("user_public"), 200, {"items": [protocol()]}),
            (
                "GET",
                search_url("public"),
                200,
                {"items": [protocol(uri="public-data-qq9z", title="Public data")]},
            ),
        ],
    }

    def test_bearer_token_and_only_protocols_io(self, w):
        self._w = w
        self.connect(w)
        method, url, kw = w.transport.calls[0]
        assert kw["headers"]["Authorization"] == f"Bearer {KEY}" and KEY not in url

    def test_search_covers_own_and_public_without_duplicates(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "search")
        found = pio.search_items(self.account(w), "data", "document")
        assert [r["id"] for r in found] == [SLUG, "public-data-qq9z"]
        assert found[0]["url"] == f"https://www.protocols.io/view/{SLUG}"

    def test_empty_query_searches_only_own(self, w):
        self._w = w
        self.connect(w)
        for flt in ("user_private", "user_public"):
            w.transport.on("GET", search_url(flt, ""), response(200, {"items": []}))
        assert pio.search_items(self.account(w), "", "document") == []

    def test_only_protocol_metadata_is_ever_requested(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "search")
        pio.search_items(self.account(w), "data", "document")
        self.create_link(w)
        for method, url, kw in w.transport.calls:
            if url == PROFILE:
                continue
            assert method == "GET" and url.startswith(pio.API)
            assert not kw.get("data") and not kw.get("json")
            assert not re.search(r"/(steps|materials|comments|files|download|export)", url, re.I)
            assert f"fields={pio.FIELDS.replace(',', '%2C')}" in url

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            (f"https://www.protocols.io/view/{SLUG}", SLUG),
            ("https://www.protocols.io/view/x", "x"),
            ("http://www.protocols.io/view/x", None),
            ("https://protocols.io.evil.net/view/x", None),
            ("https://www.protocols.io:8443/view/x", None),
            ("https://u@www.protocols.io/view/x", None),
            ("https://www.protocols.io/view/x/y", None),
            ("https://www.protocols.io/view/X?a=b", None),
            ("https://www.protocols.io/api/v4/protocols/x", None),
            ("https://www.protocols.io/view/../x", None),
            ("https://evil.example/view/x", None),
        ],
    )
    def test_pasted_urls(self, url, expected):
        assert self.provider.parse_url(url) == expected

    @pytest.mark.parametrize("pid", ["", "-x", "a/b", "A", "a b", "a?x=1", "a" * 201])
    def test_id_pattern(self, pid):
        assert not self.provider.valid_external_id(pid)

    def test_id_is_quoted_in_the_url(self, w):
        self._w = w
        self.connect(w)
        url = f"{pio.API}/a%2Fb?{urlencode({'fields': pio.FIELDS})}"
        w.transport.on("GET", url, response(404, {}))
        assert pio.fetch_item(self.account(w), "a/b") is None

    def test_metadata_fields_are_mapped(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "item")
        meta = pio.fetch_item(self.account(w), SLUG)
        assert meta["version"] == "1" and meta["modified_at"].year == 2023
        assert meta["doi"].endswith("bd5km2")

    def test_reply_url_is_ignored(self, w):
        self._w = w
        self.connect(w)
        w.transport.on(
            "GET", ITEM, response(200, {"payload": protocol(url="https://evil.example/x")})
        )
        assert pio.fetch_item(self.account(w), SLUG)["url"].startswith("https://www.protocols.io/")

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"payload": []},
            {"payload": {"uri": "x"}},
            {"payload": protocol(last_modified="soon")},
        ],
    )
    def test_unreadable_answers_become_integration_errors(self, w, body):
        self._w = w
        self.connect(w)
        w.transport.on("GET", ITEM, response(200, body))
        with pytest.raises(IntegrationError) as exc:
            pio.fetch_item(self.account(w), SLUG)
        assert KEY not in f"{exc.value!s} {exc.value!r}"

    def test_unreadable_search_and_server_error(self, w):
        self._w = w
        self.connect(w)
        w.transport.on("GET", search_url("user_private", ""), response(200, {"items": [{"x": 1}]}))
        with pytest.raises(IntegrationError):
            pio.search_items(self.account(w), "", "document")
        w.transport.on("GET", ITEM, response(500, {"error": f"x {KEY}"}))
        with pytest.raises(IntegrationError) as exc:
            pio.fetch_item(self.account(w), SLUG)
        assert KEY not in str(exc.value)
