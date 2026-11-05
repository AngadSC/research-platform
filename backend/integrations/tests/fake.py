"""Fake providers, one per auth type, and an in-process HTTP transport for integration tests.

- FAKE: oauth2, search, paste URL, every target.
- FAKE_KEY: api_key, self-hosted (an instance URL), a key and a secret, a non-bearer header,
  search, and an `apply_to_target` hook that fills an analysis' repo and commit (D86).
- FAKE_LINK: link_only (a pasted URL plus the person's title; never checked).
- FAKE_PUBLIC: public (metadata read without credentials), search, fills a dataset checksum.
"""

import json
from urllib.parse import quote, urlencode

import requests
from django.utils.dateparse import parse_datetime

from integrations import http
from integrations.http import IntegrationError
from integrations.registry import TARGETS, AuthType, Category, ConnectField, Provider


def _item(provider, url):
    """GET one item; the shapes all fake providers share."""

    def fetch(account, external_id):
        resp = http.send(
            "GET", url(account, quote(external_id, safe="")), provider=provider(), account=account
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise IntegrationError("the provider did not return the item")
        data = resp.json()
        return {
            "title": data["name"],
            "url": data["url"],
            "mime_type": data.get("mimeType", ""),
            "modified_at": parse_datetime(data["modifiedTime"]),
            "version": str(data.get("version", "")),
            "checksum": data.get("checksum", ""),
        }

    return fetch


def _search(provider, url):
    def search(account, query, target):
        resp = http.send(
            "GET",
            f"{url(account)}?{urlencode({'q': query})}",
            provider=provider(),
            account=account,
        )
        if resp.status_code != 200:
            raise IntegrationError("the provider did not answer the search")
        return [
            {
                "id": d["id"],
                "title": d["name"],
                "subtitle": d.get("path", ""),
                "modified": parse_datetime(d["modifiedTime"]) if d.get("modifiedTime") else None,
                "url": d.get("url", ""),
            }
            for d in resp.json()["items"]
        ]

    return search


FAKE = Provider(
    name="fake",
    label="Fake Drive",
    auth_type=AuthType.OAUTH2,
    category=Category.STORAGE,
    icon="fake",
    link_targets=frozenset(TARGETS),
    link_methods=("search", "paste_url"),
    scopes=("files.read", "files.meta"),
    authorize_url="https://auth.fake.test/authorize",
    token_url="https://api.fake.test/token",
    revoke_url="https://api.fake.test/revoke",
    identity_url="https://api.fake.test/me?fields=id,email",
    api_hosts=frozenset({"api.fake.test"}),
    authorize_params={"access_type": "offline", "include_granted_scopes": "true"},
    parse_identity=lambda data: (data["id"], data.get("email", "")),
    fetch_item=_item(lambda: FAKE, lambda a, i: f"https://api.fake.test/files/{i}"),
    search_items=_search(lambda: FAKE, lambda a: "https://api.fake.test/search"),
    link_hosts=frozenset({"fake.test"}),
    url_pattern=r"https://fake\.test/(?P<id>[A-Za-z0-9_.-]+)",
)


def _key_header(kwargs, key, secret):
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "X-Fake-Key": f"{key}:{secret}"}}


def _analysis_code(kind, meta):
    if kind != "analysis":
        return {}
    return {"code_repo_url": meta["url"], "code_commit": meta["version"]}


FAKE_KEY = Provider(
    name="fake_key",
    label="Fake Lab Server",
    auth_type=AuthType.API_KEY,
    category=Category.CODE,
    icon="fake-key",
    link_targets=frozenset({"project", "analysis", "dataset"}),
    link_methods=("search", "paste_url"),
    connect_fields=(
        ConnectField("instance_url", "Server address", "For example https://git.uni.edu"),
        ConnectField("api_key", "Access token", "Settings > Tokens, read-only scope."),
        ConnectField("secret", "Token secret", required=False),
    ),
    needs_instance_url=True,
    identity_url="/api/me",
    parse_identity=lambda data: (data["id"], data.get("username", "")),
    sign=_key_header,
    fetch_item=_item(lambda: FAKE_KEY, lambda a, i: f"{a.instance_url}/api/items/{i}"),
    search_items=_search(lambda: FAKE_KEY, lambda a: f"{a.instance_url}/api/search"),
    url_pattern=r"https://[a-z0-9.-]+/items/(?P<id>[0-9]+)",
    external_id_pattern=r"^[0-9]{1,12}$",
    apply_to_target=_analysis_code,
)

FAKE_LINK = Provider(
    name="fake_link",
    label="Fake Writer",
    auth_type=AuthType.LINK_ONLY,
    category=Category.WRITING,
    icon="fake-link",
    link_targets=frozenset({"project", "manuscript", "document"}),
    link_methods=("paste_url",),
    link_hosts=frozenset({"links.fake.test"}),
    url_pattern=r"https://links\.fake\.test/p/(?P<id>[a-f0-9]{8})",
    external_id_pattern=r"^[a-f0-9]{8}$",
)

FAKE_PUBLIC = Provider(
    name="fake_public",
    label="Fake Repository",
    auth_type=AuthType.PUBLIC,
    category=Category.REPOSITORY,
    icon="fake-public",
    link_targets=frozenset({"project", "dataset", "result"}),
    link_methods=("search", "paste_url"),
    api_hosts=frozenset({"public.fake.test"}),
    fetch_item=_item(lambda: FAKE_PUBLIC, lambda a, i: f"https://public.fake.test/records/{i}"),
    search_items=_search(lambda: FAKE_PUBLIC, lambda a: "https://public.fake.test/search"),
    link_hosts=frozenset({"records.fake.test"}),
    url_pattern=r"https://records\.fake\.test/r/(?P<id>[0-9]+)",
    external_id_pattern=r"^[0-9]{1,12}$",
    apply_to_target=lambda kind, meta: {"checksum": meta["checksum"]} if kind == "dataset" else {},
)


def response(status=200, body=None, headers=None, url=""):
    resp = requests.Response()
    resp.status_code = status
    resp._content = b"" if body is None else json.dumps(body).encode()
    resp.headers.update(headers or {})
    resp.url = url
    return resp


class FakeTransport:
    """Stands in for `integrations.http._session`. `on(method, url, *replies)` queues replies;
    the last one repeats. A reply is a Response, an exception to raise, or a callable taking
    the request kwargs and returning a Response. Every call is kept in `calls`."""

    def __init__(self):
        self.routes, self.calls = {}, []

    def on(self, method, url, *replies):
        self.routes[(method, url)] = list(replies)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        queue = self.routes.get((method, url))
        if not queue:
            raise AssertionError(f"unexpected request {method} {url}")
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply(kwargs) if callable(reply) else reply

    def sent(self, method, url):
        return [kw for m, u, kw in self.calls if (m, u) == (method, url)]
