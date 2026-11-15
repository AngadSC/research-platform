"""Chat reactions (D321) and link previews (D322). Outside pages come from the patched HTTP layer;
nothing leaves the process."""

import pytest
import requests
from django.core.cache import cache
from django.urls import reverse
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core import link_preview, reactions
from integrations.tests.fake import response
from labs.models import LabChatMessage

pytestmark = pytest.mark.django_db

THUMBS, HEART = "\U0001f44d", "❤️"


def api(user):
    client = APIClient()
    client.force_login(user)
    return client


@pytest.mark.parametrize("value", [THUMBS, HEART, "\U0001f44d\U0001f3fd", "\U0001f9d1‍\U0001f52c"])
def test_emoji_are_accepted(value):
    assert reactions.clean_emoji(value) == value


@pytest.mark.parametrize("value", ["\U0001f44d\u202e", "", "a", "<b>", "\U0001f44d ", "é", "\U0001f44d" * 20, None])
def test_anything_else_is_refused(value):
    with pytest.raises(ValidationError):
        reactions.clean_emoji(value)


def test_reacting_toggles_and_counts_each_person_once(lab_users):
    lab, u = lab_users
    message = LabChatMessage.objects.create(lab=lab, author=u["member"], body="hi")
    url = reverse("labs:labchat-reactions", args=[lab.pk, message.pk])

    body = api(u["viewer"]).post(url, {"emoji": THUMBS}, format="json").json()
    assert body["reactions"] == [{"emoji": THUMBS, "count": 1, "mine": True}]
    body = api(u["pi"]).post(url, {"emoji": THUMBS}, format="json").json()
    assert body["reactions"] == [{"emoji": THUMBS, "count": 2, "mine": True}]

    # Others see the count, not themselves in it.
    (row,) = api(u["member"]).get(reverse("labs:labchat-list", args=[lab.pk])).json()
    assert row["reactions"] == [{"emoji": THUMBS, "count": 2, "mine": False}]

    body = api(u["viewer"]).post(url, {"emoji": THUMBS}, format="json").json()
    assert body["reactions"] == [{"emoji": THUMBS, "count": 1, "mine": False}]
    api(u["pi"]).post(url, {"emoji": THUMBS}, format="json")
    message.refresh_from_db()
    assert message.reactions == {}


def test_a_reaction_must_be_an_emoji(lab_users):
    lab, u = lab_users
    message = LabChatMessage.objects.create(lab=lab, author=u["member"], body="hi")
    url = reverse("labs:labchat-reactions", args=[lab.pk, message.pk])
    assert api(u["member"]).post(url, {"emoji": "<script>"}, format="json").status_code == 400


def test_reactions_stop_at_a_limit(lab_users):
    lab, u = lab_users
    many = {chr(0x1F600 + i): [str(u["pi"].pk)] for i in range(reactions.MAX_KINDS)}
    message = LabChatMessage.objects.create(lab=lab, author=u["member"], body="hi", reactions=many)
    url = reverse("labs:labchat-reactions", args=[lab.pk, message.pk])
    assert api(u["member"]).post(url, {"emoji": THUMBS}, format="json").status_code == 400
    # Joining one that is already there still works.
    assert api(u["member"]).post(url, {"emoji": "\U0001f600"}, format="json").status_code == 200


# ---------------------------------------------------------------- link previews (D322)

PAGE = """<html><head><title>Fallback</title>
<meta property="og:title" content="Gene &amp; cell atlas">
<meta name="description" content="  A   reference
  atlas  ">
<meta property="og:site_name" content="Example">
</head><body><meta property="og:title" content="not this"></body></html>"""


def _html(body, kind="text/html; charset=utf-8"):
    resp = response(200, None, {"Content-Type": kind})
    resp._content = body.encode()
    resp.encoding = "utf-8"
    return resp


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()


def test_preview_reads_the_title_and_description(transport, lab_users):
    lab, u = lab_users
    url = "https://atlas.example.test/cells?id=4"
    transport.on("GET", url, _html(PAGE))
    resp = api(u["viewer"]).get(reverse("labs:link-preview", args=[lab.pk]), {"url": url})
    assert resp.status_code == 200
    assert resp.json() == {
        "url": url,
        "host": "atlas.example.test",
        "title": "Gene & cell atlas",
        "description": "A reference atlas",
        "site_name": "Example",
    }
    # Cached: a second look reads nothing.
    api(u["viewer"]).get(reverse("labs:link-preview", args=[lab.pk]), {"url": url})
    assert len(transport.sent("GET", url)) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://atlas.example.test/",
        "https://127.0.0.1/",
        "https://[::1]/",
        "https://user@atlas.example.test/",
        "https://atlas.example.test:8443/",
        "https://localhost/",
        "javascript:alert(1)",
    ],
)
def test_preview_refuses_addresses_it_must_not_read(transport, lab_users, url):
    lab, u = lab_users
    resp = api(u["member"]).get(reverse("labs:link-preview", args=[lab.pk]), {"url": url})
    assert resp.status_code == 400
    assert transport.calls == []


def test_preview_refuses_hosts_that_resolve_to_private_addresses(transport, lab_users, monkeypatch):
    from integrations import http

    lab, u = lab_users
    monkeypatch.setattr(http, "_resolve", lambda host: ["10.0.0.5"])
    url = "https://intranet.example.test/"
    resp = api(u["member"]).get(reverse("labs:link-preview", args=[lab.pk]), {"url": url})
    assert resp.status_code == 400
    assert transport.calls == []


def test_preview_of_something_other_than_a_page_is_empty(transport, lab_users):
    lab, u = lab_users
    url = "https://files.example.test/data.csv"
    transport.on("GET", url, _html("a,b", kind="text/csv"))
    body = link_preview.preview(url)
    assert body["title"] == "" and body["host"] == "files.example.test"


def test_preview_survives_a_network_error(transport, lab_users):
    url = "https://down.example.test/"
    transport.on("GET", url, requests.ConnectionError("boom"))
    assert link_preview.preview(url)["title"] == ""
