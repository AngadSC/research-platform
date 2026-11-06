"""The provider contract (provider_contract.py) run against the fake provider in all four auth
types. A real provider's test module looks like one of these classes."""

from integrations.tests import fake
from integrations.tests.provider_contract import ProviderContract


def item(name, url, version="1", **over):
    return {
        "name": name,
        "url": url,
        "mimeType": "text/csv",
        "modifiedTime": "2030-01-01T10:00:00Z",
        "version": version,
        **over,
    }


class TestFakeOAuth(ProviderContract):
    provider = fake.FAKE
    item_id = "f1"
    item_url = "https://fake.test/f1"
    title = "raw.csv"
    target = "dataset"
    api = "https://api.fake.test/files/f1"
    replies = {
        "identity": [("GET", fake.FAKE.identity_url, 200, {"id": "ext-1", "email": "a@x.test"})],
        "item": [("GET", api, 200, item("raw.csv", item_url))],
        "item_changed": [("GET", api, 200, item("raw.csv", item_url, version="2"))],
        "item_gone": [("GET", api, 404, {})],
        "search": [
            (
                "GET",
                "https://api.fake.test/search?q=data",
                200,
                {"items": [{"id": "f1", "name": "raw.csv", "url": item_url}]},
            ),
            ("GET", "https://api.fake.test/search?q=x", 200, {"items": []}),
        ],
    }


class TestFakeApiKey(ProviderContract):
    """Self-hosted, key plus secret, a custom auth header, and an analysis target whose repo and
    commit the provider fills (D86)."""

    provider = fake.FAKE_KEY
    instance_url = "https://git.fake.test/"
    item_id = "42"
    item_url = "https://git.fake.test/items/42"
    title = "pipeline"
    target = "analysis"
    api = "https://git.fake.test/api/items/42"
    replies = {
        "identity": [("GET", "https://git.fake.test/api/me", 200, {"id": 7, "username": "ada"})],
        "item": [("GET", api, 200, item("pipeline", item_url, version="abc1234"))],
        "item_changed": [("GET", api, 200, item("pipeline", item_url, version="def5678"))],
        "item_gone": [("GET", api, 404, {})],
        "search": [
            (
                "GET",
                "https://git.fake.test/api/search?q=data",
                200,
                {"items": [{"id": "42", "name": "pipeline", "url": item_url, "path": "lab/x"}]},
            ),
            ("GET", "https://git.fake.test/api/search?q=x", 200, {"items": []}),
        ],
    }

    def test_apply_to_target_fills_empty_fields_once(self, w):
        from provenance.models import Analysis

        link = self.create_link(w)
        assert link["version_note"] == "copied"
        analysis = Analysis.objects.for_lab(w.lab).get(pk=link["analysis"])
        assert (analysis.code_repo_url, analysis.code_commit) == (self.item_url, "abc1234")
        # a second link with another commit never overwrites the record (D76)
        self.replies = {**self.replies, "item": self.replies["item_changed"]}
        self.reply(w, "item")
        again = w.call(
            "POST",
            f"projects/{w.project.pk}/external-links/",
            {"provider": self.provider.name, "external_id": "42", "analysis": str(analysis.pk)},
        ).json()
        assert again["version_note"] == "kept"
        analysis.refresh_from_db()
        assert analysis.code_commit == "abc1234"

    def test_links_and_credentials_stay_on_the_instance(self, w):
        link = self.create_link(w)
        assert link["url"].startswith("https://git.fake.test/")
        sent = [kw["headers"] for _, url, kw in w.transport.calls if "git.fake.test" in url]
        assert sent and all(h["X-Fake-Key"].startswith("CANARY-api-key") for h in sent)
        other = {**self.link_body(), "url": "https://elsewhere.test/items/42"}
        other.pop("external_id")
        resp = w.call("POST", f"projects/{w.project.pk}/external-links/", other)
        assert resp.status_code == 400 and "url" in resp.json()

    def test_any_lab_role_connects_one_server_account_at_a_time(self, w):
        from django.test import Client

        viewer = Client()
        viewer.force_login(w.users["viewer"])
        url = w.url(f"integrations/{self.provider.name}/connect/")
        body = {"api_key": "k1", "instance_url": self.instance_url}
        self.reply(w, "identity")
        first = viewer.post(url, body, "application/json")
        assert first.status_code == 200 and first.json()["account"]["status"] == "active"
        assert first.json()["authorization_url"] == "" and "k1" not in first.content.decode()
        w.transport.on("GET", "https://git.fake.test/api/me", fake.response(200, {"id": 8}))
        other = viewer.post(url, {**body, "api_key": "k2"}, "application/json")
        assert other.status_code == 400 and other.json()["code"] == "other_account_connected"


class TestFakeLinkOnly(ProviderContract):
    provider = fake.FAKE_LINK
    item_id = "0a1b2c3d"
    item_url = "https://links.fake.test/p/0a1b2c3d"
    target = "manuscript"

    def test_pasted_url_must_match_pattern_and_host(self, w):
        self._w = w
        for url in (
            "https://links.fake.test/p/NOT-HEX",
            "https://evil.test/p/0a1b2c3d",
            "http://links.fake.test/p/0a1b2c3d",
            "https://links.fake.test:8443/p/0a1b2c3d",
            "https://user@links.fake.test/p/0a1b2c3d",
        ):
            resp = w.call(
                "POST",
                f"projects/{w.project.pk}/external-links/",
                {"provider": self.provider.name, "url": url, "title": "T"},
            )
            assert resp.status_code == 400, url
        assert w.transport.calls == []  # a link_only provider never calls out

    def test_nothing_to_search(self, w):
        resp = w.call("GET", f"projects/{w.project.pk}/integrations/{self.provider.name}/search/")
        assert resp.status_code == 400

    def test_title_is_required(self, w):
        resp = w.call(
            "POST",
            f"projects/{w.project.pk}/external-links/",
            {"provider": self.provider.name, "url": self.item_url},
        )
        assert resp.status_code == 400


class TestFakePublic(ProviderContract):
    provider = fake.FAKE_PUBLIC
    item_id = "1234"
    item_url = "https://records.fake.test/r/1234"
    title = "Survey 2030"
    target = "dataset"
    api = "https://public.fake.test/records/1234"
    replies = {
        "item": [("GET", api, 200, item("Survey 2030", item_url, checksum="md5:" + "a" * 32))],
        "item_changed": [("GET", api, 200, item("Survey 2030", item_url, version="2"))],
        "item_gone": [("GET", api, 404, {})],
        "search": [
            (
                "GET",
                "https://public.fake.test/search?q=data",
                200,
                {"items": [{"id": "1234", "name": "Survey 2030", "url": item_url}]},
            ),
            ("GET", "https://public.fake.test/search?q=x", 200, {"items": []}),
        ],
    }

    def test_dataset_checksum_comes_from_the_record(self, w):
        from provenance.models import DatasetRecord

        link = self.create_link(w)
        assert link["version_note"] == "copied" and link["linker_connection_status"] is None
        dataset = DatasetRecord.objects.for_lab(w.lab).get(pk=link["dataset"])
        assert dataset.checksum == "md5:" + "a" * 32

    def test_daily_job_checks_public_links_without_an_account(self, w):
        from integrations.jobs import check_links

        self.create_link(w)
        self.reply(w, "item_gone")
        assert check_links()["checked"] == 1
        assert self.check_status(w) == "unavailable"

    def check_status(self, w):
        from integrations.models import ExternalLink

        return ExternalLink.objects.for_lab(w.lab).get().status
