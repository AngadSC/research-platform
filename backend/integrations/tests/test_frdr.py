"""FRDR (D184): the provider contract plus DOI and page-address parsing, the DataCite search for
a pasted page address, URL quoting and the promise that frdr-dfdr.ca itself is never called.
Every call is mocked."""

from urllib.parse import quote

import pytest

from integrations.http import IntegrationError
from integrations.providers import frdr
from integrations.tests.fake import response
from integrations.tests.provider_contract import ProviderContract

pytestmark = pytest.mark.django_db

DOI = "10.20383/101.011"
UUID = "39e86b8b-57ef-d798-ad3e-9d15273bcc65"
PAGE = f"https://www.frdr-dfdr.ca/repo/dataset/{UUID}"
URL = "https://api.datacite.org/dois/10.20383%2F101.011"
SEARCH = (
    "https://api.datacite.org/dois?query="
    + quote(f'url:"{PAGE}" OR url:"https://frdr-dfdr.ca/repo/dataset/{UUID}"', safe="")
    + "&page%5Bsize%5D=1"
)


def row(**over):
    """A DataCite REST API record (api.datacite.org), trimmed to what the provider reads."""
    attrs = {
        "doi": DOI,
        "url": PAGE,
        "titles": [{"title": "Bow River at Banff (05BB001) Stage"}],
        "version": None,
        "updated": "2026-08-31T01:40:17.000Z",
        "state": "findable",
        "publisher": "Federated Research Data Repository",
        **over,
    }
    return {"id": attrs["doi"], "type": "dois", "attributes": attrs}


class TestFrdr(ProviderContract):
    provider = frdr.PROVIDER
    item_id = DOI
    item_url = f"https://doi.org/{DOI}"
    title = "Bow River at Banff (05BB001) Stage"
    target = "dataset"
    replies = {
        "item": [("GET", URL, 200, {"data": row()})],
        "item_changed": [
            ("GET", URL, 200, {"data": row(version="2", updated="2026-10-01T00:00:00.000Z")})
        ],
        "item_gone": [("GET", URL, 404, {"errors": [{"status": "404"}]})],
    }

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            (f"https://doi.org/{DOI}", DOI),
            ("https://dx.doi.org/10.20383/103.01818", "10.20383/103.01818"),
            (PAGE, UUID),
            (f"https://frdr-dfdr.ca/repo/dataset/{UUID}/", UUID),
            ("https://doi.org/10.5683/SP4/UBVBL1", None),
            (f"https://www.frdr-dfdr.ca/repo/dataset/{UUID.upper()}", None),
            ("https://www.frdr-dfdr.ca/repo/dataset/not-a-uuid", None),
            (f"https://www.frdr-dfdr.ca/repo/dataset/{UUID}/files", None),
            (f"https://www.frdr-dfdr.ca/repo/dataset/{UUID}?x=1", None),
            (f"http://www.frdr-dfdr.ca/repo/dataset/{UUID}", None),
            (f"https://www.frdr-dfdr.ca.evil.test/repo/dataset/{UUID}", None),
            (f"https://www.frdr-dfdr.ca:8443/repo/dataset/{UUID}", None),
        ],
    )
    def test_paste_url_and_doi_parsing(self, pasted, expected):
        assert frdr.PROVIDER.parse_url(pasted) == expected

    def test_ids_are_frdr_dois_or_page_uuids(self):
        ok = frdr.PROVIDER.valid_external_id
        assert ok(DOI) and ok(UUID)
        bad = ("", "10.5683/SP4/X", "10.20383/", "10.20383/a b", "10.20383/a?x=1", UUID + "x")
        assert not any(ok(x) for x in (*bad, DOI + "\n", "../" + DOI, DOI + "/.."))

    def test_the_doi_is_quoted_into_the_url(self, w):
        w.transport.on("GET", "https://api.datacite.org/dois/10.20383%2Fa%26b", response(404, {}))
        assert frdr.fetch_item(None, "10.20383/a&b") is None

    def test_only_datacite_is_called_and_nothing_is_signed(self, w):
        self.create_link(w)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and set(urls) == {URL}
        for _, _, kwargs in w.transport.calls:
            assert "Authorization" not in kwargs.get("headers", {})

    def test_metadata_fields(self, w):
        self.reply(w, "item")
        meta = frdr.fetch_item(None, DOI)
        assert meta["doi"] == DOI and meta["url"] == PAGE and meta["version"] == ""
        assert meta["modified_at"].year == 2026 and meta["checksum"] == ""

    def test_a_page_uuid_is_resolved_by_one_datacite_search(self, w):
        w.transport.on("GET", SEARCH, response(200, {"data": [row()]}))
        meta = frdr.fetch_item(None, UUID)
        assert meta["doi"] == DOI and [u for _, u, _ in w.transport.calls] == [SEARCH]
        w.transport.on("GET", SEARCH, response(200, {"data": []}))
        assert frdr.fetch_item(None, UUID) is None

    def test_a_record_from_another_repository_is_not_ours(self, w):
        w.transport.on("GET", URL, response(200, {"data": row(doi="10.5683/sp4/x")}))
        assert frdr.fetch_item(None, DOI) is None

    def test_a_missing_page_address_falls_back_to_the_doi_link(self, w):
        w.transport.on("GET", URL, response(200, {"data": row(url=None)}))
        assert frdr.fetch_item(None, DOI)["url"] == f"https://doi.org/{DOI}"

    def test_unreadable_answers_are_integration_errors(self, w):
        for body in ({}, [], {"data": {}}, {"data": row(titles=[])}):
            w.transport.on("GET", URL, response(200, body))
            with pytest.raises(IntegrationError):
                frdr.fetch_item(None, DOI)
