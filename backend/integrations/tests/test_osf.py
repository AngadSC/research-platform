"""OSF (D118): the provider contract plus id and URL parsing, the token header, file hashes and
the promise that no file or storage service is ever contacted. Every OSF call is a mocked reply."""

import pytest

from integrations.http import IntegrationError
from integrations.providers import osf
from integrations.tests.fake import response
from integrations.tests.provider_contract import KEY, ProviderContract
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db

API = "https://api.osf.io/v2"
FILE_ID = "5f8a1b2c3d4e5f6a7b8c9d0e"
SHA = "ab" * 32
STORAGE = "https://files.osf.io/v1/resources/abcde/providers/osfstorage/" + FILE_ID


def node(**attrs):
    return {
        "data": {
            "id": "abcde",
            "type": "nodes",
            "attributes": {
                "title": "Sleep study",
                "public": False,
                "date_modified": "2024-05-01T10:00:00.123456",  # OSF sends no zone: UTC
                **attrs,
            },
            "links": {"html": "https://osf.io/abcde/", "self": f"{API}/nodes/abcde/"},
        }
    }


def stored_file(**over):
    data = {
        "id": FILE_ID,
        "type": "files",
        "attributes": {
            "kind": "file",
            "name": "data.csv",
            "guid": None,
            "current_version": 3,
            "date_modified": "2024-05-01T10:00:00.000000",
            "extra": {"hashes": {"md5": "d41d8cd98f00b204e9800998ecf8427e", "sha256": SHA.upper()}},
        },
        "relationships": {"node": {"links": {"related": {"href": f"{API}/nodes/abcde/"}}}},
        "links": {"info": f"{API}/files/{FILE_ID}/", "move": STORAGE, "upload": STORAGE},
        **over,
    }
    return {"data": data}


class TestOsf(ProviderContract):
    provider = osf.PROVIDER
    item_id = "abcde"
    item_url = "https://osf.io/abcde/"
    title = "Sleep study"
    target = "dataset"
    replies = {
        "identity": [
            (
                "GET",
                f"{API}/users/me/",
                200,
                {"data": {"id": "u1b2c", "attributes": {"full_name": "Jo"}}},
            )
        ],
        "item": [("GET", f"{API}/nodes/abcde/", 200, node())],
        "item_changed": [
            ("GET", f"{API}/nodes/abcde/", 200, node(date_modified="2025-01-01T00:00:00.000000"))
        ],
        "item_gone": [("GET", f"{API}/nodes/abcde/", 403, {})],
    }

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            ("https://osf.io/abcde", "abcde"),
            ("https://osf.io/abcde/", "abcde"),
            ("https://osf.io/a1b2c/", "a1b2c"),
            (f"https://osf.io/abcde/files/osfstorage/{FILE_ID}", FILE_ID),
            (f"https://osf.io/{FILE_ID}/", FILE_ID),
            ("https://osf.io/abcdef", None),
            ("https://osf.io/ABCDE", None),
            ("https://osf.io/abcde/wiki", None),
            ("https://osf.io/abcde?view_only=secret", None),
            ("https://osf.io/search?q=abcde", None),
            ("http://osf.io/abcde", None),
            ("https://osf.io:444/abcde", None),
            ("https://osf.io.evil.test/abcde", None),
            ("https://api.osf.io/v2/nodes/abcde/", None),
        ],
    )
    def test_paste_url_parsing(self, pasted, expected):
        assert osf.PROVIDER.parse_url(pasted) == expected

    def test_ids(self):
        ok = osf.PROVIDER.valid_external_id
        assert ok("abcde") and ok(FILE_ID)
        bad = [
            "",
            "abcd",
            "abcdef",
            "ABCDE",
            "abc/e",
            "../x",
            FILE_ID.upper(),
            FILE_ID + "0",
            "abcde\n",
        ]
        assert not any(ok(b) for b in bad)

    def test_the_token_is_a_bearer_header_never_in_a_url_and_only_metadata_is_read(self, w):
        self.create_link(w)
        for method, url, kwargs in w.transport.calls:
            assert method == "GET" and url.startswith(f"{API}/"), url
            assert KEY not in url and "files.osf.io" not in url
            assert kwargs["headers"]["Authorization"] == f"Bearer {KEY}"

    def test_a_file_gives_sha256_and_current_version(self, w):
        self.connect(w)
        w.transport.on("GET", f"{API}/files/{FILE_ID}/", response(200, stored_file()))
        meta = osf.fetch_item(self.account(w), FILE_ID)
        assert meta["checksum"] == f"sha256:{SHA}" and meta["version"] == "3"
        assert meta["title"] == "data.csv" and meta["modified_at"].year == 2024
        # no link in the reply is followed: the storage URLs are never requested
        assert all("files.osf.io" not in u for _, u, _ in w.transport.calls)
        assert meta["url"] == f"https://osf.io/abcde/files/osfstorage/{FILE_ID}"

    def test_a_file_page_comes_from_its_link_or_guid_first(self, w):
        self.connect(w)
        for patch, page in (
            ({"links": {"html": "https://osf.io/zzzzz/"}}, "https://osf.io/zzzzz/"),
            (
                {"attributes": {**stored_file()["data"]["attributes"], "guid": "gu1d5"}},
                "https://osf.io/gu1d5/",
            ),
        ):
            w.transport.on("GET", f"{API}/files/{FILE_ID}/", response(200, stored_file(**patch)))
            assert osf.fetch_item(self.account(w), FILE_ID)["url"] == page

    def test_a_dataset_takes_the_file_hash_only_while_empty(self, w):
        self.connect(w)
        w.transport.on("GET", f"{API}/files/{FILE_ID}/", response(200, stored_file()))
        data = DatasetRecord.objects.create(
            lab=w.lab, project=w.project, name="D", version_label="v1", created_by=w.pi
        )
        body = {"provider": "osf", "external_id": FILE_ID, "dataset": str(data.pk)}
        resp = w.call("POST", f"projects/{w.project.pk}/external-links/", body)
        data.refresh_from_db()
        assert resp.status_code == 201 and data.checksum == f"sha256:{SHA}"
        assert data.version_label == "v1" and resp.json()["version_note"] == "copied"

    def test_a_project_proposes_nothing(self):
        assert osf.apply_to_target("dataset", {"checksum": ""}) == {"checksum": ""}
        assert osf.apply_to_target("analysis", {"checksum": "sha256:ab"}) == {}

    def test_unreadable_answers_are_integration_errors(self, w):
        self.connect(w)
        for body in ({}, {"data": {}}, [], {"data": {"attributes": {"title": "x"}}}):
            w.transport.on("GET", f"{API}/nodes/abcde/", response(200, body))
            with pytest.raises(IntegrationError):
                osf.fetch_item(self.account(w), "abcde")
