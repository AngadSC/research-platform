"""OneDrive and SharePoint on the integrations framework (D100 to D102). All Graph traffic is
mocked."""

import pytest

from integrations import http
from integrations.providers import onedrive
from integrations.tests.fake import response
from integrations.tests.provider_contract import ProviderContract

DRIVE = "b!Zx9-_aBc"
ITEM = "01BYE5RZ6QN3ZWBTUFOFD3GSPGOHDJD36K"
ITEM_ID = f"{DRIVE}.{ITEM}"
URL = f"{onedrive.GRAPH}/drives/b%21Zx9-_aBc/items/{ITEM}?$select={onedrive.FIELDS}"
WEB = "https://contoso-my.sharepoint.com/personal/ada_contoso_com/Documents/raw.csv"
SHA256 = "AB" * 32


def graph_item(**over):
    return {
        "id": ITEM,
        "name": "raw.csv",
        "webUrl": WEB,
        "lastModifiedDateTime": "2030-01-01T10:00:00Z",
        "eTag": '"{AAA},1"',
        "cTag": '"c:{AAA},1"',
        "file": {
            "mimeType": "text/csv",
            "hashes": {"quickXorHash": "AAAAAAAAAAAAAAAAAAAAAAAAAAA="},
        },
        "parentReference": {"driveId": DRIVE, "name": "Documents"},
        **over,
    }


class TestOneDrive(ProviderContract):
    provider = onedrive.PROVIDER
    item_id = ITEM_ID
    title = "raw.csv"
    target = "dataset"
    search_query = "data"
    replies = {
        "identity": [
            (
                "GET",
                onedrive.PROVIDER.identity_url,
                200,
                {"id": DRIVE, "owner": {"user": {"email": "ada@contoso.com"}}},
            )
        ],
        "item": [("GET", URL, 200, graph_item())],
        "item_changed": [("GET", URL, 200, graph_item(eTag='"{AAA},2"'))],
        "item_gone": [("GET", URL, 404, {"error": {"code": "itemNotFound"}})],
        "search": [
            (
                "GET",
                f"{onedrive.GRAPH}/me/drive/search(q='data')?$select={onedrive.FIELDS}&$top=20",
                200,
                {"value": [graph_item()]},
            ),
            (
                "GET",
                f"{onedrive.GRAPH}/me/drive/search(q='x')?$select={onedrive.FIELDS}&$top=20",
                200,
                {"value": []},
            ),
        ],
    }

    def test_least_scopes_and_hosts(self):
        p = self.provider
        assert p.scopes == ("Files.Read.All", "offline_access")  # D100: read-only, no User.Read
        assert p.api_hosts == {"login.microsoftonline.com", "graph.microsoft.com"}
        assert p.revoke_url == "" and p.revoke is None  # D102: Microsoft has no revoke endpoint
        assert "paste_url" not in p.link_methods  # D101

    def test_id_pattern_is_tight(self):
        p = self.provider
        assert p.valid_external_id(ITEM_ID) and p.valid_external_id("0123abcd.B0588A!12")
        for bad in ("", ITEM, "a.b.c", "a/b.c", "a.b?x=1", "a.b c", "..", f"{DRIVE}.{ITEM}\n"):
            assert not p.valid_external_id(bad), bad

    def test_ids_are_quoted_in_the_url(self, w):
        self.connect(w)
        w.transport.on("GET", URL, response(200, graph_item()))
        assert onedrive.fetch_item(self.account(w), ITEM_ID)["title"] == "raw.csv"
        sent = [u for _, u, _ in w.transport.calls if "/drives/" in u]
        assert sent == [URL] and "b%21Zx9-_aBc" in sent[0]

    def test_search_quotes_the_query(self, w):
        self.connect(w)
        q = "o%27%27brien%20%26%20x"
        url = f"{onedrive.GRAPH}/me/drive/search(q='{q}')?$select={onedrive.FIELDS}&$top=20"
        w.transport.on("GET", url, response(200, {"value": []}))
        assert onedrive.search_items(self.account(w), "o'brien & x", "dataset") == []
        assert onedrive.search_items(self.account(w), "  ", "dataset") == []  # no call, no match

    def test_gone_mapping(self, w):
        self.connect(w)
        acct = self.account(w)
        for status in (404, 403, 410):
            w.transport.on("GET", URL, response(status, {}))
            assert onedrive.fetch_item(acct, ITEM_ID) is None
        w.transport.on("GET", URL, response(200, graph_item(deleted={"state": "deleted"})))
        assert onedrive.fetch_item(acct, ITEM_ID) is None
        w.transport.on("GET", URL, response(400, {}))
        with pytest.raises(http.IntegrationError):
            onedrive.fetch_item(acct, ITEM_ID)

    @pytest.mark.parametrize(
        "body",
        [
            {},
            [],
            "text",
            {"name": "x"},
            graph_item(lastModifiedDateTime="not a date"),
            graph_item(webUrl="https://evil.example/raw.csv"),
            graph_item(webUrl="http://contoso.sharepoint.com/x"),
            graph_item(file=[]),
        ],
    )
    def test_parse_errors_become_integration_errors(self, w, body):
        self.connect(w)
        w.transport.on("GET", URL, response(200, body))
        with pytest.raises(http.IntegrationError) as exc:
            onedrive.fetch_item(self.account(w), ITEM_ID)
        assert "evil" not in str(exc.value)
        w.transport.on("GET", onedrive.PROVIDER.identity_url, response(200, {}))

    def test_search_parse_error(self, w):
        self.connect(w)
        url = f"{onedrive.GRAPH}/me/drive/search(q='data')?$select={onedrive.FIELDS}&$top=20"
        w.transport.on("GET", url, response(200, {"value": [{"name": "no ids"}]}))
        with pytest.raises(http.IntegrationError):
            onedrive.search_items(self.account(w), "data", "dataset")

    def test_shared_items_use_the_owners_drive(self, w):
        self.connect(w)
        url = f"{onedrive.GRAPH}/me/drive/search(q='data')?$select={onedrive.FIELDS}&$top=20"
        remote = {"id": "ignored", "name": "shared.csv", "remoteItem": graph_item(id="R1")}
        w.transport.on("GET", url, response(200, {"value": [remote]}))
        found = onedrive.search_items(self.account(w), "data", "dataset")
        assert found[0]["id"] == f"{DRIVE}.R1"

    def test_hashes_and_dataset_checksum(self):
        sha = {"file": {"hashes": {"sha256Hash": SHA256, "quickXorHash": "AAAA"}}}
        assert onedrive._checksum(sha["file"]) == "sha256:" + SHA256.lower()
        quick = {"quickXorHash": "AAAAAAAAAAAAAAAAAAAAAAAAAAA="}
        assert onedrive._checksum({"hashes": quick}).startswith("quickxor:")
        assert onedrive._checksum({}) == ""
        assert onedrive.apply_to_target("dataset", {"checksum": "sha256:" + "a" * 64}) == {
            "checksum": "sha256:" + "a" * 64
        }
        assert onedrive.apply_to_target("dataset", {"checksum": "quickxor:AAAA="}) == {}
        assert onedrive.apply_to_target("analysis", {"checksum": "sha256:" + "a" * 64}) == {}

    def test_dataset_checksum_filled_once(self, w):
        from provenance.models import DatasetRecord

        sha = graph_item(file={"mimeType": "text/csv", "hashes": {"sha256Hash": SHA256}})
        self.replies = {**self.replies, "item": [("GET", URL, 200, sha)]}
        link = self.create_link(w)
        assert link["version_note"] == "copied"
        dataset = DatasetRecord.objects.for_lab(w.lab).get(pk=link["dataset"])
        assert dataset.checksum == "sha256:" + SHA256.lower()

    def test_quickxor_never_goes_on_the_dataset(self, w):
        from provenance.models import DatasetRecord

        link = self.create_link(w)  # default item carries only a quickXor hash
        assert link["version_note"] == ""
        assert DatasetRecord.objects.for_lab(w.lab).get(pk=link["dataset"]).checksum == ""

    def test_no_content_url_is_ever_requested(self, w):
        link = self.create_link(w)
        self.reply(w, "search")
        w.call(
            "GET",
            f"projects/{w.project.pk}/integrations/onedrive/search/",
            q="data",
            target="dataset",
        )
        self.check(w, link)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and all(u.startswith(("https://graph.", "https://login.")) for u in urls)
        for bad in ("/content", "/preview", "/thumbnails", "download", "/versions", "@microsoft"):
            assert not [u for u in urls if bad in u.lower()], bad
        assert all("$select=" in u for u in urls if "/items/" in u)

    def test_tenant_is_validated(self):
        from django.core.exceptions import ImproperlyConfigured

        assert onedrive.tenant("") == onedrive.tenant(None) == "common"
        assert onedrive.tenant("contoso.onmicrosoft.com") == "contoso.onmicrosoft.com"
        assert onedrive.tenant("0b3e2b3a-1111-2222-3333-444455556666")
        for bad in ("evil.example/../x", "a b", "x?y=1", "https://x.com", "localhost"):
            with pytest.raises(ImproperlyConfigured):
                onedrive.tenant(bad)
        assert "/common/" in onedrive.PROVIDER.token_url or onedrive.TENANT != "common"
