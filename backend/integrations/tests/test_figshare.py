"""Figshare (D117): the provider contract plus URL and DOI parsing, URL quoting, the checksum rule
and the promise that no file is requested. Every Figshare call is a mocked reply."""

import pytest

from integrations.http import IntegrationError
from integrations.providers import figshare
from integrations.tests.fake import response
from integrations.tests.provider_contract import ProviderContract
from provenance.models import DatasetRecord

pytestmark = pytest.mark.django_db

URL = "https://api.figshare.com/v2/articles/12345678"
FILE_URL = "https://ndownloader.figshare.com/files/999"
MD5 = "d41d8cd98f00b204e9800998ecf8427e"
PAGE = "https://figshare.com/articles/dataset/Survey_data/12345678"


def article(files=None, **over):
    files = [{"name": "data.csv", "computed_md5": MD5, "size": 5}] if files is None else files
    return {
        "id": 12345678,
        "title": "Survey data",
        "doi": "10.6084/m9.figshare.12345678.v2",
        "version": 2,
        "modified_date": "2024-05-01T10:00:00Z",
        "url_public_html": PAGE,
        "files": [{**f, "download_url": FILE_URL} for f in files],
        **over,
    }


class TestFigshare(ProviderContract):
    provider = figshare.PROVIDER
    item_id = "12345678"
    item_url = f"{PAGE}/2"
    title = "Survey data"
    target = "dataset"
    replies = {
        "item": [("GET", URL, 200, article())],
        "item_changed": [
            ("GET", URL, 200, article(version=3, modified_date="2025-01-01T00:00:00Z"))
        ],
        "item_gone": [("GET", URL, 404, {})],
    }

    @pytest.mark.parametrize(
        ("pasted", "expected"),
        [
            (PAGE, "12345678"),
            (f"{PAGE}/2", "12345678"),
            (f"{PAGE}/", "12345678"),
            ("https://figshare.com/articles/figure/A_figure_2020/987/1", "987"),
            ("https://figshare.com/articles/dataset/123/456", None),  # no title slug: not a page
            ("https://doi.org/10.6084/m9.figshare.12345678", "12345678"),
            ("https://doi.org/10.6084/m9.figshare.12345678.v3", "12345678"),
            ("https://doi.org/10.6084/M9.FIGSHARE.12345678", "12345678"),
            ("https://dx.doi.org/10.6084/m9.figshare.5", "5"),
            ("https://doi.org/10.1234/m9.figshare.5", None),
            ("https://figshare.com/articles/dataset/Survey_data/abc", None),
            ("https://figshare.com/s/0123456789abcdef", None),  # a private share link
            ("http://figshare.com/articles/dataset/x/1", None),
            ("https://figshare.com:444/articles/dataset/x/1", None),
            ("https://figshare.com.evil.test/articles/dataset/x/1", None),
            ("https://evil.test/articles/dataset/x/1", None),
            ("https://api.figshare.com/v2/articles/1", None),
        ],
    )
    def test_paste_url_and_doi_parsing(self, pasted, expected):
        assert figshare.PROVIDER.parse_url(pasted) == expected

    def test_ids_are_numbers_only(self):
        ok = figshare.PROVIDER.valid_external_id
        assert ok("12345678") and not any(ok(x) for x in ("", "1a", "../1", "1/files", "1\n"))

    def test_the_id_is_quoted_into_the_url(self, w):
        w.transport.on("GET", "https://api.figshare.com/v2/articles/1%2F..%2Fx", response(404, {}))
        assert figshare.fetch_item(None, "1/../x") is None

    def test_the_article_record_is_read_and_no_file_is_requested(self, w):
        self.create_link(w)
        assert {u for _, u, _ in w.transport.calls} == {URL}
        for _, _, kwargs in w.transport.calls:
            assert "Authorization" not in kwargs.get("headers", {})

    def test_metadata_fields(self, w):
        self.reply(w, "item")
        meta = figshare.fetch_item(None, "12345678")
        assert meta["url"] == PAGE and meta["version"] == "2" and meta["modified_at"].year == 2024
        assert meta["checksum"] == f"md5:{MD5}" and meta["doi"] == "10.6084/m9.figshare.12345678.v2"
        many = [{"name": "a", "computed_md5": MD5}, {"name": "b", "computed_md5": MD5}]
        w.transport.on("GET", URL, response(200, article(many)))
        assert figshare.fetch_item(None, "12345678")["checksum"].startswith("figshare-manifest:")
        w.transport.on("GET", URL, response(200, article([{"name": "a", "computed_md5": ""}])))
        assert figshare.fetch_item(None, "12345678")["checksum"] == ""

    def test_an_empty_dataset_checksum_is_filled_and_the_label_kept(self, w):
        link = self.create_link(w)
        data = DatasetRecord.objects.for_lab(w.lab).get(project=w.project)
        assert data.checksum == f"md5:{MD5}" and data.version_label == "v1"
        assert link["version_note"] == "copied"

    def test_an_unpublished_article_is_not_linkable(self, w):
        w.transport.on("GET", URL, response(403, {}))
        assert figshare.fetch_item(None, "12345678") is None

    def test_unreadable_answers_are_integration_errors(self, w):
        for body in ({}, {"title": "x"}, [], {**article(), "files": 5}):
            w.transport.on("GET", URL, response(200, body))
            with pytest.raises(IntegrationError):
                figshare.fetch_item(None, "12345678")
