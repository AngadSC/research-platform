"""Institution type-ahead from ROR, the free Research Organization Registry (D237), through the
SSRF-safe client (D82). Public metadata, no key; only the typed text leaves the server. ROR has
no postal code or ethics pages, so what it does not hold stays for the person to type."""

import hashlib
import re

from django.core.cache import cache

from integrations import http
from integrations.providers import AuthType, Provider
from integrations.providers._refs import clean_text, web_url

API = "https://api.ror.org/v2/organizations"
# Not in the integrations registry: nothing connects to it and no link ever points at it.
ROR = Provider(
    name="ror",
    label="ROR",
    auth_type=AuthType.PUBLIC,
    api_hosts=frozenset({"api.ror.org"}),
)
USER_AGENT = "research-workspace/1.0"
MIN_Q, MAX_Q = 2, 100
PAGE_SIZE = 20  # ROR's fixed page
LIMIT = 8
CACHE_SECONDS = 24 * 60 * 60


def _query(words) -> str:
    """Every word must be in a name and the last is still being typed. `words` are `\\w+` only
    and lowercased (so none reads as an operator): nothing typed can change the query."""
    terms = " AND ".join([*words[:-1], f"{words[-1]}*"])
    return (
        f"names.value:({terms}) AND status:active "
        "AND types:(education OR healthcare OR facility OR government)"
    )


def _display(item) -> str:
    names = item.get("names") or []
    return next((n["value"] for n in names if "ror_display" in n.get("types", [])), "")


def _row(item) -> dict:
    place = (item.get("locations") or [{}])[0].get("geonames_details") or {}
    parts = [place.get("name"), place.get("country_subdivision_name"), place.get("country_name")]
    site = next((x["value"] for x in item.get("links") or [] if x.get("type") == "website"), "")
    return {
        "id": str(item["id"]),
        "name": clean_text(_display(item), 200),
        "address": clean_text(", ".join(dict.fromkeys(p for p in parts if p)), 300),
        "website": web_url(site),
    }


def _rank(item, text):
    """Names that start with what was typed come first, then shorter names, because the
    university itself is usually shorter than its hospital or institutes. Ties: ROR's order."""
    aliases = (str(n.get("value", "")).lower() for n in item.get("names") or [])
    name = _display(item).lower()
    return (not name.startswith(text), not any(a.startswith(text) for a in aliases), len(name))


@http.interactive
def _fetch(text: str, words: list[str]) -> list[dict]:
    # ponytail: ROR has no phrase-prefix search, so "university of a" matches any record holding
    # those words. A short last word gets three pages to find names that really start that way;
    # the list narrows with each letter typed.
    pages = 3 if len(words[-1]) <= 2 else 1
    found = {}
    try:
        for page in range(1, pages + 1):
            resp = http.send(
                "GET",
                API,
                provider=ROR,
                params={"query.advanced": _query(words), "page": page},
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            if not resp.ok:
                raise ValueError
            items = resp.json()["items"]
            found.update((i["id"], i) for i in items if _display(i))
            if len(items) < PAGE_SIZE:
                break
        return [_row(i) for i in sorted(found.values(), key=lambda i: _rank(i, text))[:LIMIT]]
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise http.IntegrationError("ROR returned an unreadable answer") from None


def search(q) -> list[dict]:
    """Up to `LIMIT` organisations for the typed text, cached a day. Too short or too long gives
    [] without a call. Raises IntegrationError if ROR can't be reached, which is never cached."""
    text = " ".join(str(q or "").lower().split())
    words = re.findall(r"\w+", text)
    if not (MIN_Q <= len(text) <= MAX_Q) or not words:
        return []
    key = "ror:" + hashlib.sha256(text.encode()).hexdigest()
    found = cache.get(key)
    if found is None:
        found = _fetch(text, words)
        cache.set(key, found, CACHE_SECONDS)
    return found
