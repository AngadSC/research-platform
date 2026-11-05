"""Qualtrics provider (D112): the contract plus host, metadata-only and parsing rules. All HTTP
is the fake transport; nothing leaves the process."""

import re

import pytest

from integrations.http import IntegrationError
from integrations.providers import qualtrics
from integrations.tests.fake import response
from integrations.tests.provider_contract import KEY, ProviderContract

pytestmark = pytest.mark.django_db

HOST = "https://uni.yul1.qualtrics.com"
SV = "SV_0abcDEF1234xyz"
WHOAMI = f"{HOST}/API/v3/whoami"
META = f"{HOST}/API/v3/survey-definitions/{SV}/metadata"
LIST = f"{HOST}/API/v3/surveys?offset=0"
ALLOWED_PATH = re.compile(
    r"/API/v3/(whoami|surveys\?offset=\d+|survey-definitions/SV_[A-Za-z0-9]+/metadata)"
)


def meta(**over):
    return {
        "result": {
            "SurveyID": SV,
            "SurveyName": "Sleep diary",
            "SurveyStatus": "Active",
            "CreationDate": "2024-01-02T03:04:05Z",
            "LastModified": "2024-02-03T04:05:06Z",
            **over,
        },
        "meta": {"httpStatus": "200 - OK"},
    }


def listing(*surveys, next_page=None):
    return {
        "result": {
            "elements": list(surveys),
            **({"nextPage": next_page} if next_page else {}),
        },
        "meta": {"httpStatus": "200 - OK"},
    }


def survey(sid=SV, name="Sleep diary", active=True, modified="2024-02-03T04:05:06Z"):
    return {
        "id": sid,
        "name": name,
        "ownerId": "UR_1",
        "lastModified": modified,
        "isActive": active,
    }


class TestQualtrics(ProviderContract):
    provider = qualtrics.PROVIDER
    item_id = SV
    title = "Sleep diary"
    instance_url = HOST
    target = "dataset"
    search_query = "sleep"
    replies = {
        "identity": [
            ("GET", WHOAMI, 200, {"result": {"userId": "UR_9", "userName": "pi@uni.edu"}})
        ],
        "item": [("GET", META, 200, meta())],
        "item_changed": [("GET", META, 200, meta(LastModified="2024-03-04T00:00:00Z"))],
        "item_gone": [("GET", META, 404, {"meta": {"httpStatus": "404 - Not Found"}})],
        "search": [("GET", LIST, 200, listing(survey(), survey("SV_zzzzzzzzzz1", "Other")))],
    }

    def test_token_goes_in_the_header_only(self, w):
        self._w = w
        self.connect(w)
        method, url, kw = w.transport.calls[0]
        assert kw["headers"]["X-API-TOKEN"] == KEY and KEY not in url

    def test_search_filters_by_name_and_sorts_newest_first(self, w):
        self._w = w
        self.connect(w)
        old = survey("SV_old00000001", "Sleep old", modified="2020-01-01T00:00:00Z")
        w.transport.on("GET", LIST, response(200, listing(old, survey(), survey("SV_x", "Mood"))))
        found = qualtrics.search_items(self.account(w), "SLEEP", "dataset")
        assert [r["id"] for r in found] == [SV, "SV_old00000001"]
        assert found[0]["url"] == f"{HOST}/survey-builder/{SV}/edit"

    def test_search_pages_by_offset_never_follows_next_page_url(self, w):
        self._w = w
        self.connect(w)
        evil = "https://evil.example/API/v3/surveys?offset=1"
        w.transport.on("GET", LIST, response(200, listing(survey(), next_page=evil)))
        w.transport.on(
            "GET",
            f"{HOST}/API/v3/surveys?offset=1",
            response(200, listing(survey("SV_page2000001", "Sleep two"))),
        )
        found = qualtrics.search_items(self.account(w), "sleep", "dataset")
        assert len(found) == 2
        assert all("evil" not in u for _, u, _ in w.transport.calls)

    def test_only_survey_metadata_is_ever_requested(self, w):
        self._w = w
        self.connect(w)
        self.reply(w, "search")
        self.create_link(w)
        qualtrics.search_items(self.account(w), "", "dataset")
        assert w.transport.calls
        for method, url, kw in w.transport.calls:
            assert method == "GET" and url.startswith(HOST)
            assert ALLOWED_PATH.fullmatch(url[len(HOST) :]), url
            assert not kw.get("data") and not kw.get("json")
            assert not re.search(r"respons|export|distribution|mailinglist", url, re.I)

    @pytest.mark.parametrize(
        "host",
        [
            "https://qualtrics.com",
            "https://evilqualtrics.com",
            "https://uni.qualtrics.com.evil.net",
            "https://qualtrics.com.evil.net",
            "https://uni.qualtrics.co",
            "https://example.org",
        ],
    )
    def test_instance_host_must_be_under_qualtrics_com(self, w, host):
        resp = w.call(
            "POST", "integrations/qualtrics/connect/", {"api_key": KEY, "instance_url": host}
        )
        assert resp.status_code == 400 and resp.json()["code"] == "instance_not_allowed"
        assert not w.transport.calls

    @pytest.mark.parametrize("host", ["https://uni.yul1.qualtrics.com", "https://a.qualtrics.com"])
    def test_instance_host_pattern_accepts_brand_and_datacenter(self, host):
        from integrations.http import instance_host_allowed

        assert instance_host_allowed(host.removeprefix("https://"), self.provider)

    @pytest.mark.parametrize("sid", ["SV_", "sv_abcdefgh12", "SV_a/../b", "SV_abc def12345", ""])
    def test_id_pattern(self, sid):
        assert not self.provider.valid_external_id(sid)
        assert self.provider.valid_external_id(SV)

    def test_id_is_quoted_in_the_url(self, w):
        self._w = w
        self.connect(w)
        w.transport.on(
            "GET", f"{HOST}/API/v3/survey-definitions/SV_a%2Fb%3Fx/metadata", response(404, {})
        )
        assert qualtrics.fetch_item(self.account(w), "SV_a/b?x") is None

    @pytest.mark.parametrize("body", [{}, {"result": {}}, {"result": {"SurveyName": "x"}}, []])
    def test_unreadable_metadata_becomes_integration_error(self, w, body):
        self._w = w
        self.connect(w)
        w.transport.on("GET", META, response(200, body))
        with pytest.raises(IntegrationError) as exc:
            qualtrics.fetch_item(self.account(w), SV)
        assert KEY not in f"{exc.value!s} {exc.value!r}"

    @pytest.mark.parametrize("body", [{}, {"result": {}}, {"result": {"elements": [{"id": "x"}]}}])
    def test_unreadable_list_becomes_integration_error(self, w, body):
        self._w = w
        self.connect(w)
        w.transport.on("GET", LIST, response(200, body))
        with pytest.raises(IntegrationError):
            qualtrics.search_items(self.account(w), "", "dataset")

    def test_forbidden_survey_is_unavailable_and_server_error_hides_body(self, w):
        self._w = w
        self.connect(w)
        w.transport.on("GET", META, response(403, {}))
        assert qualtrics.fetch_item(self.account(w), SV) is None
        w.transport.on("GET", META, response(500, {"error": f"x {KEY}"}))
        with pytest.raises(IntegrationError) as exc:
            qualtrics.fetch_item(self.account(w), SV)
        assert KEY not in str(exc.value)
