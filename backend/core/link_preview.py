"""Link previews in chat (D322): a pasted web address shows its page's title and description.

The server reads the page, not the reader's browser, so no outside site learns who is reading the
chat and no outside image or script loads in the app. Every fetch goes through
`integrations.http.send` with a provider made for that one host: https on port 443, a DNS name
resolving to public addresses only (pinned per request, so DNS rebinding can't reach the
network inside), redirects only on the same host, a few seconds and 512 KB at most. Only the
title, description and site name are kept, as plain text; nothing from the page is ever shown as
markup. Results are cached for a day, failures for an hour, by the address's hash.
"""

import dataclasses
import hashlib
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.core.cache import cache

from integrations import http
from integrations.providers import AuthType, Provider

_BASE = Provider(
    name="link_preview", label="Link preview", auth_type=AuthType.PUBLIC, secret_url=True
)
MAX_URL = 2000
MAX_BYTES = 512 * 1024
TIMEOUT = 6
CACHE_OK, CACHE_FAILED = 24 * 3600, 3600
_SPACE = re.compile(r"\s+")


class _Meta(HTMLParser):
    """Reads <title> and the og:/twitter:/description <meta> tags of the page's head."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self._in_title, self.done = {}, "", False, False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in {
                "og:title",
                "og:description",
                "og:site_name",
                "twitter:title",
                "twitter:description",
                "description",
            }:
                self.meta.setdefault(key, a.get("content", ""))
        elif tag == "body":
            self.done = True  # everything we read is in the head

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and len(self.title) < 1000:
            self.title += data


def _clean(value, limit) -> str:
    text = _SPACE.sub(" ", unescape(str(value or ""))).strip()
    text = "".join(c for c in text if c.isprintable())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def check_url(url) -> str:
    """The host of a previewable address, or ValueError: https, port 443, no userinfo, a DNS
    name (never an IP literal), within the deployment's host allowlist when it has one."""
    url = str(url or "").strip()
    if len(url) > MAX_URL:
        raise ValueError("too long")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or parts.port not in (None, 443)
        or parts.username is not None
        or "@" in parts.netloc
        or not http.dns_name_ok(host)
        or not http.instance_host_allowed(host, _BASE)
    ):
        raise ValueError("not previewable")
    try:  # every request checks this again, pinned (`PinnedAdapter`); this answers early
        http.public_address(host)
    except http.IntegrationError:
        raise ValueError("not a public address") from None
    return host


def _fetch(url, host) -> dict:
    provider = dataclasses.replace(_BASE, api_hosts=frozenset({host}))
    with http.budget(TIMEOUT, per_request=TIMEOUT, max_bytes=MAX_BYTES):
        resp = http.send(
            "GET",
            url,
            provider=provider,
            headers={"Accept": "text/html", "User-Agent": "labbenchos link preview"},
        )
    kind = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if resp.status_code != 200 or kind not in ("text/html", "application/xhtml+xml"):
        return {}
    parser = _Meta()
    try:
        parser.feed(resp.content.decode(resp.encoding or "utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 - a page we can't parse simply has no preview
        return {}
    m = parser.meta
    return {
        "title": _clean(m.get("og:title") or m.get("twitter:title") or parser.title, 200),
        "description": _clean(
            m.get("og:description") or m.get("twitter:description") or m.get("description"), 300
        ),
        "site_name": _clean(m.get("og:site_name"), 100),
    }


def preview(url) -> dict:
    """{url, host, title, description, site_name}; the last three are "" when the page gave
    none or could not be read. ValueError when the address is not one we will fetch."""
    host = check_url(url)
    key = "link-preview:" + hashlib.sha256(url.encode()).hexdigest()
    found = cache.get(key)
    if found is None:
        try:
            found = _fetch(url, host)
        except http.IntegrationError:
            found = {}
        cache.set(key, found, CACHE_OK if found.get("title") else CACHE_FAILED)
    empty = {"title": "", "description": "", "site_name": ""}
    return {"url": url, "host": host, **empty, **found}
