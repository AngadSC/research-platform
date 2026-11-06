"""Helpers shared by the reference and repository providers (Zotero, Zenodo, Figshare, OSF,
D115 to D119). Nothing here talks to the network except `read`, which goes through
`integrations.http.send`."""

import hashlib
import re
from datetime import UTC

from django.utils.dateparse import parse_datetime

from integrations import http

_DOI = re.compile(r"^10\.\d{4,9}/\S+$")  # the D95 rule
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_MD5 = re.compile(r"^[0-9a-fA-F]{32}$")


def clean_doi(value) -> str:
    """A bare DOI (`10.1234/abc`) from a bare, `doi:` or doi.org form, else ''."""
    if not isinstance(value, str):
        return ""
    doi = _DOI_PREFIX.sub("", value.strip())
    return doi if _DOI.match(doi) and len(doi) <= 200 else ""


def clean_text(value, limit=300) -> str:
    """One line of plain text: whitespace (and so control characters) collapsed."""
    return " ".join(str(value or "").split())[:limit]


def web_url(value) -> str:
    """`value` if it is a plain http(s) address of sane length, else ''."""
    return value if isinstance(value, str) and re.match(r"^https?://\S{1,480}$", value) else ""


def aware(value):
    """An ISO time as an aware datetime (naive means UTC, as OSF sends it); None if unparsable."""
    when = parse_datetime(value) if isinstance(value, str) else None
    return when.replace(tzinfo=UTC) if when and when.tzinfo is None else when


def required_time(value):
    """Like `aware`, but an unparsable time raises ValueError (callers turn that into an
    IntegrationError): a provider answering with junk is an unreadable answer."""
    when = aware(value)
    if when is None:
        raise ValueError
    return when


def files_checksum(pairs, prefix) -> str:
    """One checksum for a record's files from (name, md5) pairs. One file: `md5:<hex>`. Several:
    `<prefix>:<sha256 of the sorted name:md5 lines>`, a manifest digest named for what it is, so
    it is never mistaken for the hash of one file. Any file without an md5: ''."""
    pairs = sorted(pairs)
    if not pairs or not all(isinstance(m, str) and _MD5.match(m) for _, m in pairs):
        return ""
    if len(pairs) == 1:
        return f"md5:{pairs[0][1].lower()}"
    lines = "\n".join(f"{n}:{m.lower()}" for n, m in pairs)
    return f"{prefix}:{hashlib.sha256(lines.encode()).hexdigest()}"


def read(provider, account, url, label, gone=(404,)):
    """GET `url` and parse the JSON body. None when the status is in `gone`; otherwise anything
    but 200 or an unreadable body raises IntegrationError with a fixed message."""
    resp = http.send("GET", url, provider=provider, account=account)
    if resp.status_code in gone:
        return None
    if resp.status_code != 200:
        raise http.IntegrationError(f"{label} did not answer")
    try:
        return resp.json()
    except ValueError:
        raise http.IntegrationError(f"{label} returned an unreadable answer") from None
