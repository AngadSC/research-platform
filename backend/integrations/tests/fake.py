"""A fake OAuth2 provider and an in-process HTTP transport for integration tests."""

import json

import requests

from integrations.registry import AuthType, Provider

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
