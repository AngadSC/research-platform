"""REDCap provider (D110, D111): the contract plus the rules that matter for participant data.
All HTTP is the fake transport; nothing leaves the process."""

import pytest

from integrations.http import IntegrationError
from integrations.providers import redcap
from integrations.tests.fake import response
from integrations.tests.provider_contract import KEY, ProviderContract

pytestmark = pytest.mark.django_db

INSTANCE = "https://redcap.test.edu/redcap"
API = f"{INSTANCE}/api/"


def info(**over):
    return {
        "project_id": "42",
        "project_title": "Sleep Study",
        "creation_time": "2024-01-02 03:04:05",
        "in_production": 1,
        "purpose": "2",
        "is_longitudinal": 0,
        "surveys_enabled": 1,
        "project_notes": "internal notes",
        **over,
    }


class TestRedcap(ProviderContract):
    provider = redcap.PROVIDER
    item_id = "42"
    title = "Sleep Study"
    instance_url = INSTANCE
    target = "dataset"
    replies = {
        "identity": [("POST", API, 200, info())],
        "item": [("POST", API, 200, info())],
        "item_changed": [("POST", API, 200, info(project_title="Sleep Study 2", in_production=0))],
        "item_gone": [("POST", API, 403, {"error": "You do not have permissions to use the API"})],
        "search": [("POST", API, 200, info())],
    }

    def lifecycle(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "search")
        w.call(
            "GET",
            f"projects/{w.project.pk}/integrations/redcap/search/",
            q="x",
            target="dataset",
        )
        self.create_link(w)

    def test_only_project_info_is_ever_requested(self, w):
        """No request carries any other content action, and the token is only in the body."""
        self.lifecycle(w)
        assert w.transport.calls
        for method, url, kw in w.transport.calls:
            assert (method, url) == ("POST", API)
            assert kw["data"] == {
                "content": "project",
                "format": "json",
                "returnFormat": "json",
                "token": KEY,
            }
            assert KEY not in url and KEY not in repr(kw.get("headers", {}))
            assert "params" not in kw

    def test_data_dictionary_is_not_requested(self):
        """D110: `content=metadata` is refused by policy, not just unused."""
        assert redcap.PROJECT_INFO["content"] == "project"
        assert self.provider.metadata_only is True

    def test_other_projects_token_is_not_the_linked_project(self, w):
        self.lifecycle(w)
        w.transport.on("POST", API, response(200, info(project_id="43")))
        assert redcap.fetch_item(self.account(w), "42") is None

    def test_search_returns_the_one_project(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "search")
        found = redcap.search_items(self.account(w), "anything", "dataset")
        assert [r["id"] for r in found] == ["42"]
        assert found[0]["url"] == f"{INSTANCE}/index.php?pid=42"

    def test_checksum_ignores_unstable_fields_and_follows_stable_ones(self, w):
        self._w = w
        self.connect(w)
        acct = self.account(w)
        w.transport.on("POST", API, response(200, info()))
        base = redcap.fetch_item(acct, "42")["checksum"]
        w.transport.on("POST", API, response(200, info(project_notes="edited", creation_time="x")))
        assert redcap.fetch_item(acct, "42")["checksum"] == base
        w.transport.on("POST", API, response(200, info(surveys_enabled=0)))
        assert redcap.fetch_item(acct, "42")["checksum"] != base
        assert base.startswith("sha256:") and redcap.fetch_item(acct, "42")["modified_at"] is None

    @pytest.mark.parametrize("pid", ["abc", "4 2", "42/../x", "", "12345678901", "-1"])
    def test_id_pattern(self, pid):
        assert not self.provider.valid_external_id(pid)
        assert self.provider.valid_external_id("42")

    @pytest.mark.parametrize(
        "body", [[], {"error": "bad"}, {"project_id": "x", "project_title": "t"}, {"a": 1}]
    )
    def test_unreadable_answers_become_integration_errors(self, w, body):
        self._w = w
        self.connect(w)
        w.transport.on("POST", API, response(200, body))
        with pytest.raises(IntegrationError) as exc:
            redcap.fetch_item(self.account(w), "42")
        assert KEY not in f"{exc.value!s} {exc.value!r}"

    def test_server_error_message_hides_the_body_and_key(self, w):
        self._w = w
        self.connect(w)
        w.transport.on("POST", API, response(500, {"error": f"boom {KEY}"}))
        with pytest.raises(IntegrationError) as exc:
            redcap.fetch_item(self.account(w), "42")
        assert KEY not in str(exc.value) and "boom" not in str(exc.value)

    @pytest.mark.parametrize(
        ("url", "code"),
        [
            ("http://redcap.test.edu/redcap", "invalid_instance_url"),
            ("https://10.0.0.5/redcap", "invalid_instance_url"),
            ("https://redcap.test.edu:8443/redcap", "invalid_instance_url"),
            ("https://u:p@redcap.test.edu/redcap", "invalid_instance_url"),
            ("https://redcap.test.edu/redcap?x=1", "invalid_instance_url"),
        ],
    )
    def test_instance_url_is_checked(self, w, url, code):
        resp = w.call("POST", "integrations/redcap/connect/", {"api_key": KEY, "instance_url": url})
        assert resp.status_code == 400 and resp.json()["code"] == code
        assert not w.transport.calls

    def test_instance_url_is_required(self, w):
        resp = w.call("POST", "integrations/redcap/connect/", {"api_key": KEY})
        assert resp.status_code == 400
        assert not w.transport.calls
