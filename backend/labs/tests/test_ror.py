"""Institution type-ahead (D237). Who reaches it is in the permission matrix; this covers the
query, the mapping, the cache and what happens when ROR is down. No network: `http.send` is fake."""

from unittest.mock import Mock

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from integrations.http import IntegrationError
from labs import ror

pytestmark = pytest.mark.django_db

ALBERTA = {
    "id": "https://ror.org/0160cpw27",
    "names": [{"value": "University of Alberta", "types": ["ror_display", "label"]}],
    "locations": [
        {
            "geonames_details": {
                "name": "Edmonton",
                "country_subdivision_name": "Alberta",
                "country_name": "Canada",
            }
        }
    ],
    "links": [{"type": "website", "value": "https://www.ualberta.ca/"}],
}
OTHER = {
    "id": "https://ror.org/other",
    "names": [{"value": "Concordia University of Edmonton", "types": ["ror_display"]}],
}


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()


@pytest.fixture
def send(monkeypatch):
    fake = Mock(return_value=Mock(ok=True, json=lambda: {"items": [OTHER, ALBERTA]}))
    monkeypatch.setattr(ror.http, "send", fake)
    return fake


def test_maps_ror_and_ranks_names_that_start_with_the_text_first(send):
    assert ror.search("University of Alb") == [
        {
            "id": ALBERTA["id"],
            "name": "University of Alberta",
            "address": "Edmonton, Alberta, Canada",
            "website": "https://www.ualberta.ca/",
        },
        # ROR has no location or website here: left blank, not guessed
        {
            "id": OTHER["id"],
            "name": "Concordia University of Edmonton",
            "address": "",
            "website": "",
        },
    ]
    assert send.call_args.args == ("GET", ror.API)
    assert send.call_args.kwargs["provider"].api_hosts == frozenset({"api.ror.org"})
    assert send.call_args.kwargs["params"]["query.advanced"].startswith(
        "names.value:(university AND of AND alb*) AND status:active"
    )


def test_the_university_comes_before_its_longer_named_centres(send):
    hospital = {
        **ALBERTA,
        "id": "h",
        "names": [{"value": "University of Alberta Hospital", "types": ["ror_display"]}],
    }
    send.return_value = Mock(ok=True, json=lambda: {"items": [hospital, ALBERTA]})
    assert [r["name"] for r in ror.search("university of")][0] == "University of Alberta"


def test_typed_syntax_cannot_reach_the_query(send):
    ror.search('uni OR "x" types:company) AND (\\*')
    query = send.call_args.kwargs["params"]["query.advanced"]
    assert '"' not in query and "\\" not in query
    assert query.startswith("names.value:(uni AND or AND x AND types AND company AND and*)")


def test_a_short_last_word_reads_more_pages_and_stops_at_a_short_page(send):
    ror.search("university of a")
    assert send.call_count == 1  # the fake's page has fewer than 20 items

    send.reset_mock()
    full = {"items": [{**OTHER, "id": str(n)} for n in range(ror.PAGE_SIZE)]}
    send.return_value = Mock(ok=True, json=lambda: full)
    ror.search("university of b")
    assert [c.kwargs["params"]["page"] for c in send.call_args_list] == [1, 2, 3]


@pytest.mark.parametrize("q", ["", "a", " . ", "x" * 101])
def test_too_short_or_too_long_makes_no_call(send, q):
    assert ror.search(q) == []
    send.assert_not_called()


def test_results_are_cached_and_the_text_is_normalised(send):
    ror.search("McGill")
    ror.search("  mcgill ")
    assert send.call_count == 1


@pytest.mark.parametrize(
    "answer", [Mock(ok=False), Mock(ok=True, json=lambda: {"bad": 1}), IntegrationError("down")]
)
def test_a_failure_is_not_cached_and_the_endpoint_returns_nothing(send, make_user, answer):
    send.side_effect = [answer]
    client = APIClient()
    client.force_login(make_user())

    resp = client.get("/api/institutions/search/", {"q": "mcgill"})

    assert resp.status_code == 200 and resp.json() == {"results": []}
    send.side_effect = None
    assert ror.search("mcgill")  # the failure was not remembered


def test_creating_a_lab_saves_the_picked_address_and_checks_the_website(make_user):
    client = APIClient()
    client.force_login(make_user())
    body = {"name": "Picked", "institution_name": "University of Alberta"}

    made = client.post(
        "/api/labs/",
        {**body, "address": "Edmonton, Alberta, Canada", "website": "https://www.ualberta.ca/"},
        format="json",
    )
    assert made.status_code == 201, made.content
    assert made.json()["address"] == "Edmonton, Alberta, Canada"
    assert made.json()["website"] == "https://www.ualberta.ca/"

    bad = client.post("/api/labs/", {**body, "website": "ftp://x.example"}, format="json")
    assert bad.status_code == 400 and "website" in bad.json()
