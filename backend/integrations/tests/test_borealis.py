"""Borealis (D183): the provider contract plus DOI and address parsing, URL quoting and the
promise that only the published-version metadata call is ever made. Every call is mocked."""

import pytest

from integrations.http import IntegrationError
from integrations.providers import borealis
from integrations.tests.fake import response
from integrations.tests.provider_contract import ProviderContract

pytestmark = pytest.mark.django_db

DOI = "10.5683/SP4/UBVBL1"
URL = (
    "https://borealisdata.ca/api/datasets/:persistentId/versions/:latest-published"
    "?persistentId=doi%3A10.5683%2FSP4%2FUBVBL1&excludeFiles=true"
)


def version(**over):
    """A reply shaped like the Dataverse native API version object (guides.dataverse.org)."""
    data = {
        "id": 77,
        "datasetId": 12,
        "datasetPersistentId": f"doi:{DOI}",
        "versionNumber": 1,
        "versionMinorNumber": 2,
        "versionState": "RELEASED",
        "lastUpdateTime": "2025-03-04T15:30:10Z",
        "releaseTime": "2025-03-04T15:30:10Z",
        "createTime": "2025-02-01T09:00:00Z",
        "metadataBlocks": {
            "citation": {
                "displayName": "Citation Metadata",
                "fields": [
                    {"typeName": "subtitle", "multiple": False, "value": "x"},
                    {"typeName": "title", "multiple": False, "value": "Colostrum  trial\ndata"},
                ],
            }
        },
        **over,
    }
    return {"status": "OK", "data": data}


class TestBorealis(ProviderContract):
    provider = borealis.PROVIDER
    item_id = DOI
    item_url = f"https://borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}"
    title = "Colostrum trial data"
    target = "dataset"
    replies = {
        "item": [("GET", URL, 200, version())],
        "item_changed": [
            ("GET", URL, 200, version(versionMinorNumber=3, lastUpdateTime="2025-09-01T10:00:00Z"))
        ],
        "item_gone": [("GET", URL, 404, {"status": "ERROR", "message": "not found"})],
    }

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            (f"https://borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}", DOI),
            (f"https://borealisdata.ca/dataset.xhtml?persistentId=doi%3A{DOI}", DOI),
            (f"https://borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}&version=1.0", DOI),
            (f"https://borealisdata.ca/citation?persistentId=doi:{DOI}", DOI),
            (f"https://doi.org/{DOI}", DOI),
            ("https://doi.org/10.5683/SP/30JPOR", "10.5683/SP/30JPOR"),
            ("https://dx.doi.org/10.5683/SP2/ABC123", "10.5683/SP2/ABC123"),
            ("https://doi.org/10.5281/zenodo.123", None),
            ("https://borealisdata.ca/dataset.xhtml?persistentId=doi:10.5072/FK2/ABC", None),
            ("https://borealisdata.ca/dataset.xhtml?persistentId=hdl:10.5683/SP4/X", None),
            (f"https://borealisdata.ca/api/access/datafile/1?persistentId=doi:{DOI}", None),
            (f"https://borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}&x=../../a", None),
            (f"http://borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}", None),
            (f"https://borealisdata.ca.evil.test/dataset.xhtml?persistentId=doi:{DOI}", None),
            (f"https://dataverse.scholarsportal.info/citation?persistentId=doi:{DOI}", None),
            (f"https://borealisdata.ca:8443/dataset.xhtml?persistentId=doi:{DOI}", None),
            (f"https://u@borealisdata.ca/dataset.xhtml?persistentId=doi:{DOI}", None),
            ("https://doi.org/10.5683/SP4/../../x", None),
        ],
    )
    def test_paste_url_and_doi_parsing(self, pasted, expected):
        assert borealis.PROVIDER.parse_url(pasted) == expected

    def test_ids_are_borealis_dois_only(self):
        ok = borealis.PROVIDER.valid_external_id
        assert ok(DOI) and ok("10.5683/SP/30JPOR")
        bad = ("", "doi:" + DOI, "10.5281/zenodo.1", "10.5683/", "10.5683/a b", "10.5683/a?x=1")
        assert not any(ok(x) for x in (*bad, DOI + "\n", "../" + DOI, DOI + "/../.."))

    def test_the_doi_is_quoted_into_the_url(self, w):
        w.transport.on("GET", URL.replace("SP4%2FUBVBL1", "SP4%2FA%26b%3D1"), response(404, {}))
        # the id pattern keeps such ids out in practice; the quoting is the second wall
        assert borealis.fetch_item(None, "10.5683/SP4/A&b=1") is None

    def test_only_the_published_metadata_call_is_made_and_nothing_is_signed(self, w):
        self.create_link(w)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and set(urls) == {URL}
        assert "excludeFiles=true" in URL and "/api/access" not in "".join(urls)
        for _, _, kwargs in w.transport.calls:
            assert "Authorization" not in kwargs.get("headers", {})
            assert "X-Dataverse-key" not in kwargs.get("headers", {})

    def test_metadata_fields(self, w):
        self.reply(w, "item")
        meta = borealis.fetch_item(None, DOI)
        assert meta["version"] == "1.2" and meta["doi"] == DOI and meta["checksum"] == ""
        assert meta["modified_at"].year == 2025 and meta["title"] == "Colostrum trial data"
        assert meta["url"] == (
            "https://borealisdata.ca/dataset.xhtml?persistentId=doi%3A10.5683%2FSP4%2FUBVBL1"
        )

    def test_a_draft_or_deaccessioned_version_reads_as_gone(self, w):
        for state in ("DRAFT", "DEACCESSIONED"):
            w.transport.on("GET", URL, response(200, version(versionState=state)))
            assert borealis.fetch_item(None, DOI) is None
        w.transport.on("GET", URL, response(403, {}))
        assert borealis.fetch_item(None, DOI) is None

    def test_only_the_version_label_is_offered_to_a_dataset(self):
        meta = {"version": "2.0", "checksum": ""}
        assert borealis.apply_to_target("dataset", meta) == {"version_label": "2.0"}
        assert borealis.apply_to_target("result", meta) == {}

    def test_unreadable_answers_are_integration_errors(self, w):
        bad = (
            {},
            [],
            {"data": {}},
            version(versionNumber="x"),
            version(metadataBlocks={}),
            version(metadataBlocks={"citation": {"fields": []}}),
        )
        for body in bad:
            w.transport.on("GET", URL, response(200, body))
            with pytest.raises(IntegrationError):
                borealis.fetch_item(None, DOI)
