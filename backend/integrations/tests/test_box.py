"""Box on the integrations framework (D100, D104). All Box traffic is mocked."""

from urllib.parse import urlencode

import pytest

from integrations import http
from integrations.providers import box
from integrations.tests.fake import response
from integrations.tests.provider_contract import CLIENT_SECRET, REFRESH, ProviderContract

ITEM = "123456789012"
URL = f"{box.API}/files/{ITEM}?fields={box.FIELDS}"
SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def search_url(query):
    params = {"query": query, "type": "file", "limit": 20, "fields": "id,name,modified_at,parent"}
    return f"{box.API}/search?{urlencode(params)}"


def file_json(**over):
    return {
        "type": "file",
        "id": ITEM,
        "name": "raw.csv",
        "sha1": SHA1.upper(),
        "etag": "3",
        "modified_at": "2030-01-01T10:00:00-08:00",
        "item_status": "active",
        **over,
    }


class TestBox(ProviderContract):
    provider = box.PROVIDER
    item_id = ITEM
    item_url = f"https://app.box.com/{'file'}/{ITEM}"
    title = "raw.csv"
    target = "dataset"
    replies = {
        "identity": [("GET", box.PROVIDER.identity_url, 200, {"id": "u1", "login": "a@uni.edu"})],
        "item": [("GET", URL, 200, file_json())],
        "item_changed": [("GET", URL, 200, file_json(etag="4"))],
        "item_gone": [("GET", URL, 404, {"code": "not_found"})],
        "search": [
            (
                "GET",
                search_url("data"),
                200,
                {"entries": [{**file_json(), "parent": {"name": "Lab"}}], "total_count": 1},
            ),
            ("GET", search_url("x"), 200, {"entries": []}),
        ],
    }

    def test_least_scope_hosts_and_web_link(self):
        p = self.provider
        assert p.scopes == ("root_readonly",)
        assert p.api_hosts == {"api.box.com"} and p.link_hosts == {"app.box.com"}
        assert box._web_url(ITEM) == self.item_url

    def test_id_pattern_is_tight(self):
        p = self.provider
        assert p.valid_external_id(ITEM)
        for bad in ("", "abc", "12/34", "1 2", "1?fields=x", "0" * 21, "1\n", "../1"):
            assert not p.valid_external_id(bad), bad

    def test_pasted_url_parsing(self):
        p = self.provider
        assert p.parse_url(self.item_url) == ITEM
        for bad in (
            f"http://app.box.com/file/{ITEM}",
            f"https://evil.example/file/{ITEM}",
            f"https://app.box.com:8443/file/{ITEM}",
            f"https://app.box.com/folder/{ITEM}",
            f"https://app.box.com/file/{ITEM}/../x",
            "https://app.box.com/file/abc",
        ):
            assert p.parse_url(bad) is None, bad

    def test_fields_are_explicit_and_id_is_quoted(self, w):
        self.connect(w)
        w.transport.on("GET", URL, response(200, file_json()))
        box.fetch_item(self.account(w), ITEM)
        assert [u for _, u, _ in w.transport.calls if "/files/" in u] == [URL]
        assert box.FIELDS == "id,name,sha1,etag,modified_at,item_status"
        w.transport.on("GET", f"{box.API}/files/1%2F2?fields={box.FIELDS}", response(404, {}))
        assert box.fetch_item(self.account(w), "1/2") is None  # quoted, never a path

    def test_gone_mapping(self, w):
        self.connect(w)
        acct = self.account(w)
        for status in (404, 403, 410):
            w.transport.on("GET", URL, response(status, {}))
            assert box.fetch_item(acct, ITEM) is None
        for state in ("trashed", "deleted"):
            w.transport.on("GET", URL, response(200, file_json(item_status=state)))
            assert box.fetch_item(acct, ITEM) is None
        w.transport.on("GET", URL, response(500, {}))
        with pytest.raises(http.IntegrationError):
            box.fetch_item(acct, ITEM)

    @pytest.mark.parametrize(
        "body",
        [
            {},
            [],
            "x",
            {"id": ITEM},
            file_json(modified_at="nope"),
            file_json(sha1=5),
            file_json(id=None),
        ],
    )
    def test_parse_errors_become_integration_errors(self, w, body):
        self.connect(w)
        w.transport.on("GET", URL, response(200, body))
        with pytest.raises(http.IntegrationError):
            box.fetch_item(self.account(w), ITEM)

    def test_search_parse_error_and_empty_query(self, w):
        self.connect(w)
        w.transport.on("GET", search_url("x"), response(200, {"entries": [{"name": "no id"}]}))
        with pytest.raises(http.IntegrationError):
            box.search_items(self.account(w), "x", "dataset")
        assert box.search_items(self.account(w), "", "dataset") == []

    def test_search_quotes_the_query(self, w):
        self.connect(w)
        query = "a&b=c d"
        w.transport.on("GET", search_url(query), response(200, {"entries": []}))
        assert box.search_items(self.account(w), query, "dataset") == []
        assert "query=a%26b%3Dc+d" in w.transport.calls[-1][1]

    def test_dataset_checksum_is_the_sha1(self, w):
        from provenance.models import DatasetRecord

        link = self.create_link(w)
        assert link["version_note"] == "copied"
        dataset = DatasetRecord.objects.for_lab(w.lab).get(pk=link["dataset"])
        assert dataset.checksum == f"sha1:{SHA1}"
        assert box.apply_to_target("analysis", {"checksum": "sha1:x"}) == {}
        assert box.apply_to_target("dataset", {"checksum": ""}) == {"checksum": ""}

    def test_no_content_url_is_ever_requested(self, w):
        link = self.create_link(w)
        self.reply(w, "search")
        w.call(
            "GET", f"projects/{w.project.pk}/integrations/box/search/", q="data", target="dataset"
        )
        self.check(w, link)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and all(
            u.startswith(("https://api.box.com/", "https://account.")) for u in urls
        )
        for bad in ("/content", "download", "/thumbnail", "/versions"):
            assert not [u for u in urls if bad in u], bad
        assert all("fields=" in u for u in urls if "/files/" in u)

    def test_revoke_sends_client_credentials_and_reports_failure(self, w):
        self.connect(w)
        w.transport.on("POST", self.provider.revoke_url, response(200, {}))
        assert box.revoke(REFRESH) is True
        (kwargs,) = w.transport.sent("POST", self.provider.revoke_url)
        assert kwargs["data"] == {
            "token": REFRESH,
            "client_id": "contract-client",
            "client_secret": CLIENT_SECRET,
        }
        w.transport.on("POST", self.provider.revoke_url, response(400, {}))
        assert box.revoke(REFRESH) is False
