"""A fake OAuth2 provider and an in-process HTTP transport for integration tests."""

import json
from urllib.parse import quote

import requests
from django.utils.dateparse import parse_datetime

from integrations import http
from integrations.http import IntegrationError
from integrations.registry import AuthType, Provider


def fetch_item(account, external_id):
    resp = http.send(
        "GET",
        f"https://api.fake.test/files/{quote(external_id, safe='')}",
        provider=FAKE,
        account=account,
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
        "checksum": "",
    }


FAKE = Provider(
    name="fake",
    label="Fake Drive",
    auth_type=AuthType.OAUTH2,
    scopes=("files.read", "files.meta"),
    icon="fake",
    authorize_url="https://auth.fake.test/authorize",
    token_url="https://api.fake.test/token",
    revoke_url="https://api.fake.test/revoke",
    identity_url="https://api.fake.test/me?fields=id,email",
    api_hosts=frozenset({"api.fake.test"}),
    authorize_params={"access_type": "offline", "include_granted_scopes": "true"},
    parse_identity=lambda data: (data["id"], data.get("email", "")),
    fetch_item=fetch_item,
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
