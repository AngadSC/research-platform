"""protocols.io (ARCHITECTURE section 9, D113). A personal access token (bearer). Metadata only:
title, id, version, DOI, dates. Never a protocol's steps, materials, comments or files."""

from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider

API = "https://www.protocols.io/api/v4/protocols"
# The only fields ever asked for.
FIELDS = "id,title,uri,version_id,doi,created_on,published_on,last_modified"
_BAD = (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError)


def _identity(data):
    user = data["user"]
    return str(user.get("id") or user["username"]), str(user.get("username", ""))


def _when(value) -> datetime | None:
    """protocols.io dates are Unix seconds (0 or null = unset)."""
    return datetime.fromtimestamp(int(value), UTC) if value else None


def _meta(item: dict) -> dict:
    uri = str(item["uri"])
    return {
        "title": str(item["title"]),
        # built from the slug, not taken from the reply: the host is ours
        "url": f"https://www.protocols.io/view/{quote(uri, safe='')}",
        "mime_type": "",
        "modified_at": _when(item.get("last_modified")) or _when(item.get("published_on")),
        "version": str(item.get("version_id", "")),
        "checksum": "",
        "doi": str(item.get("doi") or ""),
    }


def fetch_item(account, external_id):
    resp = http.send(
        "GET",
        f"{API}/{quote(external_id, safe='')}?{urlencode({'fields': FIELDS})}",
        provider=PROVIDER,
        account=account,
    )
    if resp.status_code in (403, 404):  # 403: made private, or no longer shared with them
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("protocols.io did not return the protocol")
    try:
        data = resp.json()
        item = data.get("payload") or data.get("protocol")
        if not isinstance(item, dict):
            raise ValueError
        return _meta(item)
    except _BAD:
        raise http.IntegrationError("protocols.io returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """The person's own protocols, plus public ones when there is a query."""
    key = (query or "").strip()[:100]
    out, seen = [], set()
    for flt in ["user_private", "user_public"] + (["public"] if key else []):
        params = {"filter": flt, "key": key, "page_size": 20, "fields": FIELDS}
        resp = http.send("GET", f"{API}?{urlencode(params)}", provider=PROVIDER, account=account)
        if resp.status_code != 200:
            raise http.IntegrationError("protocols.io did not answer the search")
        try:
            for item in resp.json()["items"]:
                meta = _meta(item)
                if item["uri"] in seen:
                    continue
                seen.add(item["uri"])
                out.append(
                    {
                        "id": str(item["uri"]),
                        "title": meta["title"],
                        "subtitle": meta["doi"] or ("Public" if flt == "public" else "Yours"),
                        "modified": meta["modified_at"],
                        "url": meta["url"],
                    }
                )
        except _BAD:
            raise http.IntegrationError("protocols.io returned an unreadable answer") from None
    return out


PROVIDER = Provider(
    name="protocols_io",
    label="protocols.io",
    auth_type=AuthType.API_KEY,
    category=Category.PROTOCOLS,
    icon="protocols-io",
    link_targets=frozenset({"analysis", "document", "project"}),
    link_methods=("search", "paste_url"),
    connect_fields=(
        ConnectField(
            "api_key",
            "Access token",
            "protocols.io > Profile > Developer > Access token (a personal client access "
            "token). We only read protocol titles, versions and dates.",
        ),
    ),
    api_hosts=frozenset({"www.protocols.io"}),
    identity_url="https://www.protocols.io/api/v3/session/profile",
    parse_identity=_identity,
    fetch_item=fetch_item,
    search_items=search_items,
    link_hosts=frozenset({"www.protocols.io"}),
    # D113: the external id is the protocol's uri (its slug), which is what a pasted address
    # contains and what the API accepts in place of the numeric id.
    url_pattern=r"https://www\.protocols\.io/view/(?P<id>[a-z0-9][a-z0-9-]{0,199})",
    external_id_pattern=r"^[a-z0-9][a-z0-9-]{0,199}$",
)
