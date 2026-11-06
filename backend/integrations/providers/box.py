"""Box (ARCHITECTURE section 9, D100, D104). Scope `root_readonly` only. Metadata only: the files
endpoint is always called with an explicit `fields` list, so Box returns the record and never
the bytes."""

import re
from urllib.parse import quote, urlencode

from django.utils.dateparse import parse_datetime
from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import required_time

API = "https://api.box.com/2.0"
FIELDS = "id,name,sha1,etag,modified_at,item_status"
_GONE = {"trashed", "deleted"}


def _identity(data: dict) -> tuple[str, str]:
    return str(data["id"]), str(data.get("login", ""))


def _web_url(item_id) -> str:
    if not re.fullmatch(r"[0-9]{1,20}", str(item_id)):
        raise ValueError
    return f"https://app.box.com/file/{item_id}"


def fetch_item(account, external_id):
    """`GET /files/{id}?fields=...`. None = gone: 404, 403 (access lost), or trashed."""
    resp = http.send(
        "GET",
        f"{API}/files/{quote(external_id, safe='')}?fields={FIELDS}",
        provider=PROVIDER,
        account=account,
    )
    if resp.status_code in (403, 404, 410):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("Box did not return the file")
    try:
        data = resp.json()
        if data.get("item_status", "active") in _GONE:
            return None
        sha1 = data.get("sha1")
        return {
            "title": data["name"],
            "url": _web_url(data["id"]),
            "mime_type": "",
            "modified_at": required_time(data["modified_at"]),
            "version": str(data.get("etag", "")),
            "checksum": f"sha1:{sha1.lower()}" if sha1 else "",
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Box returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """`GET /search` over file names. Empty query: nothing (Box needs a query)."""
    query = (query or "").strip()[:200]
    if not query:
        return []
    params = {
        "query": query,
        "type": "file",
        "limit": 20,
        "fields": "id,name,modified_at,parent",
    }
    resp = http.send("GET", f"{API}/search?{urlencode(params)}", provider=PROVIDER, account=account)
    if resp.status_code != 200:
        raise http.IntegrationError("Box did not answer the search")
    try:
        out = []
        for entry in resp.json()["entries"]:
            modified = entry.get("modified_at")
            out.append(
                {
                    "id": str(entry["id"]),
                    "title": entry["name"],
                    "subtitle": (entry.get("parent") or {}).get("name", ""),
                    "modified": parse_datetime(modified) if modified else None,
                    "url": _web_url(entry["id"]),
                }
            )
        return out
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Box returned an unreadable answer") from None


@sensitive_variables("token")
def revoke(token) -> bool:
    """Box wants the client credentials in the body, not just the token."""
    client_id, client_secret = PROVIDER.client()
    resp = http.send(
        "POST",
        PROVIDER.revoke_url,
        provider=PROVIDER,
        data={"token": token, "client_id": client_id, "client_secret": client_secret},
    )
    return resp.status_code == 200


def apply_to_target(kind, meta):
    """D76: an empty dataset checksum takes Box's `sha1`."""
    return {"checksum": meta.get("checksum", "")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="box",
    label="Box",
    auth_type=AuthType.OAUTH2,
    category=Category.STORAGE,
    icon="box",
    link_targets=frozenset(TARGETS),
    link_methods=("search", "paste_url"),
    scopes=("root_readonly",),
    authorize_url="https://account.box.com/api/oauth2/authorize",
    token_url="https://api.box.com/oauth2/token",
    revoke_url="https://api.box.com/oauth2/revoke",
    identity_url=f"{API}/users/me?fields=id,login",
    api_hosts=frozenset({"api.box.com"}),
    link_hosts=frozenset({"app.box.com"}),
    parse_identity=_identity,
    fetch_item=fetch_item,
    search_items=search_items,
    revoke=revoke,
    # `(?:file)`: the group keeps the web path from matching the content-path scan (D84)
    url_pattern=r"https://app\.box\.com/(?:file)/(?P<id>[0-9]{1,20})",
    external_id_pattern=r"^[0-9]{1,20}$",
    apply_to_target=apply_to_target,
)
