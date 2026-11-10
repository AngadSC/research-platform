"""Zotero (ARCHITECTURE section 9, D115). A read-only API key, sent in the `Zotero-API-Key`
header. Metadata only: item records (title, DOI, url, dates, version); never attachments' files
or any `file` endpoint. Items are named `<u|g><library id>:<item key>`."""

import re
from urllib.parse import quote, urlencode

from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider
from integrations.providers._refs import aware, clean_doi, clean_text, read, web_url

API = "https://api.zotero.org"
ITEM_KEY = "[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}"  # Zotero's item key alphabet
_ID = re.compile(rf"^([ug])([0-9]{{1,12}}):({ITEM_KEY})$")
_NOT_REFERENCES = {"note", "annotation"}
MAX_GROUPS = 5  # groups searched besides the personal library
SEARCH_LIMIT = 20


def _read_only_access(access) -> None:
    """The key must read something and write nothing (least scope, D115)."""
    libs = [access["user"], *access.get("groups", {}).values()]
    if any(lib.get("write") for lib in libs) or not any(lib.get("library") for lib in libs):
        raise ValueError("key must be read-only with library access")


def identify(account):
    """`GET /keys/current`: (user id, user name). Zotero answers 403 for an unknown key."""
    resp = http.send("GET", f"{API}/keys/current", provider=PROVIDER, account=account)
    if resp.status_code in (403, 404):
        raise http.AccountUnavailable("Zotero rejected the key")
    if resp.status_code != 200:
        raise http.IntegrationError("Zotero did not answer")
    data = resp.json()
    _read_only_access(data["access"])
    return str(int(data["userID"])), str(data.get("username", ""))


@sensitive_variables("key")
def sign(kwargs, key, secret):
    headers = {**kwargs.get("headers", {}), "Zotero-API-Key": key, "Zotero-API-Version": "3"}
    return {**kwargs, "headers": headers}


def _library(kind, number) -> str:
    return f"{API}/{'users' if kind == 'u' else 'groups'}/{quote(number, safe='')}"


def _summary(item, library_id=None):
    """The item's metadata from an API item record; None for notes and annotations."""
    data = item["data"]
    if data.get("itemType") in _NOT_REFERENCES:
        return None
    link = item.get("links", {}).get("alternate", {}).get("href", "")
    if not link:  # the web library address, always on www.zotero.org
        lib = item["library"]
        link = f"https://www.zotero.org/{lib['type']}s/{lib['id']}/items/{item['key']}"
    return {
        "title": clean_text(data.get("title") or data.get("filename") or "Untitled item", 500),
        "url": link,
        "mime_type": "",
        "modified_at": aware(data.get("dateModified")),
        "version": str(item["version"]),
        "checksum": "",
        "doi": clean_doi(data.get("DOI")),
        "item_url": web_url(data.get("url")),
    }


def fetch_item(account, external_id):
    """One item's record. None: it is gone, a note, or not in a library this key can read."""
    match = _ID.match(external_id)
    if not match:
        raise http.IntegrationError("Zotero item id is not valid")
    kind, number, key = match.groups()
    if kind == "u" and number != account.external_account_id:
        return None  # only the key's own library; never someone else's public one
    url = f"{_library(kind, number)}/items/{quote(key, safe='')}"
    try:
        item = read(PROVIDER, account, url, "Zotero", gone=(403, 404))
        return item and _summary(item)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Zotero returned an unreadable answer") from None


def _find(account, kind, number, query):
    params = {"limit": SEARCH_LIMIT, "sort": "dateModified", "direction": "desc"}
    if query:
        params |= {"q": query, "qmode": "titleCreatorYear"}
    url = f"{_library(kind, number)}/items/top?{urlencode(params)}"
    items = read(PROVIDER, account, url, "Zotero", gone=(403, 404)) or []
    out = []
    for item in items:
        found = _summary(item)
        if found:
            meta = item.get("meta", {})
            out.append(
                {
                    "id": f"{kind}{number}:{item['key']}",
                    "title": found["title"],
                    "subtitle": " - ".join(
                        clean_text(x, 120)
                        for x in (meta.get("creatorSummary"), meta.get("parsedDate"))
                        if x
                    ),
                    "modified": found["modified_at"],
                    "url": found["url"],
                }
            )
    return out


def search_items(account, query, target_kind):
    """Items of the personal library, then of up to MAX_GROUPS readable groups, newest first."""
    try:
        me = account.external_account_id
        results = _find(account, "u", me, query)
        groups = (
            read(
                PROVIDER,
                account,
                f"{API}/users/{quote(me, safe='')}/groups?limit={MAX_GROUPS}",
                "Zotero",
                gone=(403, 404),
            )
            or []
        )
        for group in groups[:MAX_GROUPS]:
            if len(results) >= SEARCH_LIMIT:
                break
            results += _find(account, "g", str(int(group["id"])), query)
        return results[:SEARCH_LIMIT]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Zotero returned an unreadable answer") from None


def _author(creator) -> str:
    """ "Family, Given"; a trailing comma for a one-part name (see Paper.authors)."""
    if creator.get("lastName"):
        return clean_text(f"{creator['lastName']}, {creator.get('firstName', '')}", 200)
    return f"{clean_text(creator.get('name'), 199)},"


def paper_fields(account, external_id) -> dict | None:
    """One library item as paper-library fields (D242). None: it is gone or not a reference."""
    match = _ID.match(external_id)
    if not match or (match[1] == "u" and match[2] != account.external_account_id):
        return None
    url = f"{_library(match[1], match[2])}/items/{quote(match[3], safe='')}"
    try:
        item = read(PROVIDER, account, url, "Zotero", gone=(403, 404))
        if not item or _summary(item) is None:
            return None
        data = item["data"]
        date = item.get("meta", {}).get("parsedDate") or data.get("date") or ""
        year = re.search(r"\d{4}", date)
        venue = next(
            (
                data[k]
                for k in ("publicationTitle", "proceedingsTitle", "conferenceName", "bookTitle")
                if data.get(k)
            ),
            "",
        )
        return {
            "title": clean_text(data.get("title"), 500),
            "authors": [
                _author(c)
                for c in (data.get("creators") or [])[:200]
                if c.get("creatorType") == "author"
            ],
            "year": int(year[0]) if year else None,
            "venue": clean_text(venue, 300),
            "doi": clean_doi(data.get("DOI")),
            "url": web_url(data.get("url")),
            "abstract": str(data.get("abstractNote") or "")[:20_000],
        }
    except (KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Zotero returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D115: a decision gets the item appended to its `references` (see
    `services._append_reference`); nothing else is touched."""
    if kind != "decision":
        return {}
    return {
        "references": {
            "title": meta["title"][:300],
            "url": meta.get("item_url", ""),
            "doi": meta.get("doi", ""),
        }
    }


PROVIDER = Provider(
    name="zotero",
    label="Zotero",
    auth_type=AuthType.API_KEY,
    category=Category.REFERENCES,
    icon="zotero",
    link_targets=frozenset({"decision", "document", "manuscript", "project"}),
    link_methods=("search",),
    connect_fields=(
        ConnectField(
            "api_key",
            "Zotero API key",
            "Create one at zotero.org/settings/keys with read-only access to your library "
            "and the groups you want to link from. Keys that can write are refused.",
        ),
    ),
    identify=identify,
    sign=sign,
    api_hosts=frozenset({"api.zotero.org"}),
    link_hosts=frozenset({"www.zotero.org"}),
    fetch_item=fetch_item,
    search_items=search_items,
    external_id_pattern=_ID.pattern,
    apply_to_target=apply_to_target,
)
