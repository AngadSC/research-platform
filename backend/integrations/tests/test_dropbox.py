"""Dropbox on the integrations framework (D100, D103). All Dropbox traffic is mocked."""

import json

import pytest

from integrations import http
from integrations.providers import dropbox
from integrations.tests.fake import response
from integrations.tests.provider_contract import REFRESH, ProviderContract, _strings

ITEM = "id:a4ayc_80_OEAAAAAAAAAXw"
GET = f"{dropbox.API}/2/files/get_metadata"
SEARCH = f"{dropbox.API}/2/files/search_v2"
HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def meta(**over):
    return {
        ".tag": "file",
        "name": "raw data.csv",
        "id": ITEM,
        "path_display": "/Lab data/raw data.csv",
        "server_modified": "2030-01-01T10:00:00Z",
        "rev": "5c0a1b2c3d",
        "content_hash": HASH.upper(),
        **over,
    }


class TestDropbox(ProviderContract):
    provider = dropbox.PROVIDER
    item_id = ITEM
    title = "raw data.csv"
    target = "dataset"
    replies = {
        "identity": [
            (
                "POST",
                dropbox.PROVIDER.identity_url,
                200,
                {"account_id": "dbid:AAH4f99T0", "email": "ada@uni.edu"},
            )
        ],
        "item": [("POST", GET, 200, meta())],
        "item_changed": [("POST", GET, 200, meta(rev="9f8e7d6c5b"))],
        "item_gone": [
            (
                "POST",
                GET,
                409,
                {
                    "error_summary": "path/not_found/..",
                    "error": {".tag": "path", "path": {".tag": "not_found"}},
                },
            )
        ],
        "search": [
            (
                "POST",
                SEARCH,
                200,
                {
                    "matches": [{"metadata": {".tag": "metadata", "metadata": meta()}}],
                    "has_more": False,
                },
            )
        ],
    }

    def test_least_scopes_hosts_and_offline_access(self):
        p = self.provider
        assert p.scopes == ("account_info.read", "files.metadata.read")
        assert p.api_hosts == {"api.dropboxapi.com"}
        assert p.authorize_params == {"token_access_type": "offline"}
        assert p.identity_method == "POST"

    def test_id_pattern_is_tight(self):
        p = self.provider
        assert p.valid_external_id(ITEM)
        for bad in ("", "a4ayc", "id:", "id:a b", "id:a/b", "/path/x", "rev:abc", "ns:1", "id:a\n"):
            assert not p.valid_external_id(bad), bad

    def test_request_uses_the_id_in_a_json_body_on_the_rpc_host(self, w):
        self.connect(w)
        w.transport.on("POST", GET, response(200, meta()))
        dropbox.fetch_item(self.account(w), ITEM)
        (kwargs,) = w.transport.sent("POST", GET)
        assert json.loads(kwargs["data"]) == {"path": ITEM}
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")

    def test_search_body_and_empty_query(self, w):
        self.connect(w)
        w.transport.on("POST", SEARCH, response(200, {"matches": []}))
        assert dropbox.search_items(self.account(w), 'a "b"', "dataset") == []
        (kwargs,) = w.transport.sent("POST", SEARCH)
        body = json.loads(kwargs["data"])
        assert body["query"] == 'a "b"' and body["options"]["max_results"] == 20
        assert dropbox.search_items(self.account(w), "", "dataset") == []
        assert len(w.transport.sent("POST", SEARCH)) == 1

    def test_gone_mapping(self, w):
        self.connect(w)
        acct = self.account(w)
        w.transport.on("POST", GET, response(403, {}))
        assert dropbox.fetch_item(acct, ITEM) is None
        w.transport.on("POST", GET, response(200, meta(**{".tag": "deleted"})))
        assert dropbox.fetch_item(acct, ITEM) is None
        other = {"error": {".tag": "other"}}
        w.transport.on("POST", GET, response(409, other))
        with pytest.raises(http.IntegrationError):
            dropbox.fetch_item(acct, ITEM)
        w.transport.on("POST", GET, response(500, {}))
        with pytest.raises(http.IntegrationError):
            dropbox.fetch_item(acct, ITEM)

    @pytest.mark.parametrize(
        "body",
        [{}, [], "x", {"name": "x"}, meta(server_modified="not a date"), meta(path_display=5)],
    )
    def test_parse_errors_become_integration_errors(self, w, body):
        self.connect(w)
        w.transport.on("POST", GET, response(200, body))
        try:
            dropbox.fetch_item(self.account(w), ITEM)
        except http.IntegrationError:
            return
        # a path of the wrong type is tolerated (the link falls back to the home page)
        assert isinstance(body, dict) and not isinstance(body.get("path_display"), str)

    def test_search_parse_error(self, w):
        self.connect(w)
        w.transport.on("POST", SEARCH, response(200, {"matches": [{"metadata": {}}]}))
        with pytest.raises(http.IntegrationError):
            dropbox.search_items(self.account(w), "x", "dataset")

    def test_web_link_is_on_the_pinned_host_and_quoted(self):
        url = dropbox._web_url("/Lab data/a&b#c.csv")
        assert url == "https://www.dropbox.com/home/Lab%20data?preview=a%26b%23c.csv"
        assert dropbox._web_url("/x.csv") == "https://www.dropbox.com/home?preview=x.csv"
        assert dropbox._web_url(None) == "https://www.dropbox.com/home"

    def test_dataset_checksum_is_the_content_hash(self, w):
        from provenance.models import DatasetRecord

        link = self.create_link(w)
        assert link["version_note"] == "copied"
        dataset = DatasetRecord.objects.for_lab(w.lab).get(pk=link["dataset"])
        assert dataset.checksum == f"dropbox-content-hash:{HASH}"
        assert dropbox.apply_to_target("analysis", {"checksum": "x"}) == {}

    def test_no_content_host_or_path_is_ever_requested(self, w):
        link = self.create_link(w)
        self.reply(w, "search")
        w.call(
            "GET",
            f"projects/{w.project.pk}/integrations/dropbox/search/",
            q="data",
            target="dataset",
        )
        self.check(w, link)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and all(u.startswith("https://api.dropboxapi.com/") for u in urls)
        assert not [u for u in urls if "content" in u.split("/")[2] or "/files/download" in u]
        assert "content.dropboxapi.com" not in " ".join(_strings(dropbox))

    def test_revoke_trades_the_refresh_token_then_revokes_with_bearer(self, w):
        self.connect(w)
        w.transport.on("POST", self.provider.token_url, response(200, {"access_token": "NEW-AT"}))
        w.transport.on("POST", self.provider.revoke_url, response(200, {}))
        assert dropbox.revoke(REFRESH) is True
        (kwargs,) = w.transport.sent("POST", self.provider.revoke_url)
        assert kwargs["headers"] == {"Authorization": "Bearer NEW-AT"}

    def test_revoke_with_an_access_token_falls_back_and_failure_is_false(self, w):
        self.connect(w)
        w.transport.on("POST", self.provider.token_url, response(400, {"error": "invalid_grant"}))
        w.transport.on("POST", self.provider.revoke_url, response(401, {}))
        assert dropbox.revoke("some-access-token") is False
        (kwargs,) = w.transport.sent("POST", self.provider.revoke_url)
        assert kwargs["headers"] == {"Authorization": "Bearer some-access-token"}
