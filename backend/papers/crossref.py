"""Fill a paper's fields from its DOI, through the SSRF-safe client (D82). Public metadata, no
credentials; the User-Agent names only the software."""

import html
import re
from urllib.parse import quote

from integrations import http
from integrations.providers import AuthType, Provider
from integrations.providers._refs import clean_doi, clean_text, web_url

API = "https://api.crossref.org/works/"
# Not in the integrations registry: nothing connects to it and no link ever points at it.
CROSSREF = Provider(
    name="crossref",
    label="Crossref",
    auth_type=AuthType.PUBLIC,
    api_hosts=frozenset({"api.crossref.org"}),
)
USER_AGENT = "research-workspace/1.0"
MAX_AUTHORS = 200


def _author(a) -> str:
    """A trailing comma when there is no given name (see Paper.authors)."""
    return clean_text(f"{a.get('family') or a.get('name')}, {a.get('given', '')}", 200)


def _abstract(value) -> str:
    """Crossref abstracts are JATS XML: this keeps only their text."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(text.split())[:20_000]


@http.interactive
def lookup(doi: str) -> dict | None:
    """Metadata for a DOI, or None if the DOI is malformed or Crossref does not know it. Raises
    IntegrationError if Crossref can't be reached or answers junk."""
    doi = clean_doi(doi)
    if not doi:
        return None
    resp = http.send(
        "GET",
        API + quote(doi, safe=""),
        provider=CROSSREF,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    if resp.status_code == 404:
        return None
    try:
        if not resp.ok:
            raise ValueError
        msg = resp.json()["message"]
        issued = (msg.get("issued") or {}).get("date-parts") or [[None]]
        year = issued[0][0]
        return {
            "title": clean_text((msg.get("title") or [""])[0], 500),
            "authors": [_author(a) for a in (msg.get("author") or [])[:MAX_AUTHORS]],
            "year": year if isinstance(year, int) else None,
            "venue": clean_text((msg.get("container-title") or [""])[0], 300),
            "doi": clean_doi(msg.get("DOI")) or doi,
            "url": web_url(msg.get("URL")),
            "abstract": _abstract(msg.get("abstract")),
        }
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise http.IntegrationError("Crossref returned an unreadable answer") from None
