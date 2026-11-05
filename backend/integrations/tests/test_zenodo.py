"""Zenodo (D116): the provider contract plus id and DOI parsing, URL quoting, the checksum rules
and the promise that no file is ever requested. Every Zenodo call is a mocked reply."""

import hashlib

import pytest

from integrations.http import IntegrationError
from integrations.providers import zenodo
from integrations.tests.fake import response
from integrations.tests.provider_contract import ProviderContract
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db

URL = "https://zenodo.org/api/records/123"
FILE_URL = "https://zenodo.org/api/records/123/files/data.csv/content"
MD5 = "d41d8cd98f00b204e9800998ecf8427e"
MD5_2 = "0cc175b9c0f1b6a831c399e269772661"


def record(files=None, **over):
    files = [{"key": "data.csv", "size": 10, "checksum": f"md5:{MD5}"}] if files is None else files
    return {
        "id": 123,
        "doi": "10.5281/zenodo.123",
        "updated": "2024-05-01T10:00:00.123456+00:00",
        "metadata": {"title": "Survey data", "version": "v1.2", "doi": "10.5281/zenodo.123"},
        "links": {"html": "https://zenodo.org/records/123", "self": URL},
        "files": [{**f, "links": {"self": FILE_URL}} for f in files],
        **over,
    }


class TestZenodo(ProviderContract):
    provider = zenodo.PROVIDER
    item_id = "123"
    item_url = "https://doi.org/10.5281/zenodo.123"
    title = "Survey data"
    target = "dataset"
    replies = {
        "item": [("GET", URL, 200, record())],
        "item_changed": [
            ("GET", URL, 200, record(updated="2025-01-01T10:00:00+00:00", metadata={
                "title": "Survey data", "version": "v1.3"}))  # fmt: skip
        ],
        "item_gone": [("GET", URL, 410, {})],
    }

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            ("https://zenodo.org/records/123", "123"),
            ("https://zenodo.org/records/123/", "123"),
            ("https://zenodo.org/record/123", "123"),
            ("https://doi.org/10.5281/zenodo.123", "123"),
            ("https://doi.org/10.5281/ZENODO.123", "123"),
            ("https://dx.doi.org/10.5281/zenodo.9876543", "9876543"),
            ("https://zenodo.org/records/123/files/data.csv", None),
            ("https://zenodo.org/records/abc", None),
            ("https://zenodo.org/records/1234567890123", None),
            ("https://doi.org/10.1234/zenodo.123", None),
            ("https://doi.org/10.5281/zenodo.123/extra", None),
            ("http://zenodo.org/records/123", None),
            ("https://zenodo.org:8443/records/123", None),
            ("https://zenodo.org.evil.test/records/123", None),
            ("https://evil.test/https://zenodo.org/records/123", None),
            ("https://user@zenodo.org/records/123", None),
            ("https://zenodo.org/records/123?x=1", None),
        ],
    )
    def test_paste_url_and_doi_parsing(self, pasted, expected):
        assert zenodo.PROVIDER.parse_url(pasted) == expected

    def test_ids_are_numbers_only(self):
        ok = zenodo.PROVIDER.valid_external_id
        assert ok("123") and not any(ok(x) for x in ("", "12a", "../1", "1/2", "1\n", "-1"))

    def test_the_id_is_quoted_into_the_url(self, w):
        w.transport.on("GET", "https://zenodo.org/api/records/1%2F..%2Fx", response(404, {}))
        assert zenodo.fetch_item(None, "1/../x") is None

    def test_no_file_is_ever_requested_and_nothing_is_signed(self, w):
        self.create_link(w)
        urls = [u for _, u, _ in w.transport.calls]
        assert urls and set(urls) == {URL}
        for _, _, kwargs in w.transport.calls:
            assert "Authorization" not in kwargs.get("headers", {})

    def test_one_file_gives_its_md5_several_give_a_manifest(self, w):
        self.reply(w, "item")
        one = zenodo.fetch_item(None, "123")
        assert one["checksum"] == f"md5:{MD5}" and one["version"] == "v1.2"
        assert one["url"] == "https://zenodo.org/records/123" and one["modified_at"].year == 2024
        files = [
            {"key": "b.csv", "checksum": f"md5:{MD5_2.upper()}"},
            {"key": "a.csv", "checksum": MD5},  # an older reply carries the bare hash
        ]
        w.transport.on("GET", URL, response(200, record(files)))
        many = zenodo.fetch_item(None, "123")["checksum"]
        manifest = hashlib.sha256(f"a.csv:{MD5}\nb.csv:{MD5_2}".encode()).hexdigest()
        assert many == f"zenodo-manifest:{manifest}"
        w.transport.on("GET", URL, response(200, record([])))
        assert zenodo.fetch_item(None, "123")["checksum"] == ""
        files[0]["checksum"] = "sha1:zz"
        w.transport.on("GET", URL, response(200, record(files)))
        assert zenodo.fetch_item(None, "123")["checksum"] == ""

    def test_an_empty_dataset_checksum_is_filled_and_the_label_kept(self, w):
        link = self.create_link(w)
        data = DatasetRecord.objects.for_lab(w.lab).get(project=w.project)
        assert data.checksum == f"md5:{MD5}" and data.version_label == "v1"
        assert link["version_note"] == "copied"

    def test_a_dataset_that_has_a_checksum_keeps_it(self, w):
        self._w = w
        self.reply(w, "item")
        data = DatasetRecord.objects.create(
            lab=w.lab, project=w.project, name="D", version_label="v1", created_by=w.pi,
            checksum="sha256:" + "ab" * 32,
        )  # fmt: skip
        body = {"provider": "zenodo", "external_id": "123", "dataset": str(data.pk)}
        resp = w.call("POST", f"projects/{w.project.pk}/external-links/", body)
        data.refresh_from_db()
        assert resp.json()["version_note"] == "kept" and data.checksum.startswith("sha256:")

    def test_other_targets_get_nothing(self):
        assert zenodo.apply_to_target("result", {"checksum": "md5:ab"}) == {}

    def test_unreadable_answers_are_integration_errors(self, w):
        for body in ({}, {"metadata": {}}, [], {**record(), "files": 5}):
            w.transport.on("GET", URL, response(200, body))
            with pytest.raises(IntegrationError):
                zenodo.fetch_item(None, "123")
