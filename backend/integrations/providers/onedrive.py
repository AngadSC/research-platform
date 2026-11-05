"""Microsoft OneDrive and SharePoint through Microsoft Graph (ARCHITECTURE section 9, D100 to
D102). Delegated scopes `Files.Read.All` and `offline_access` only. Metadata only: `$select`
names the fields, and no content, preview or thumbnail endpoint is ever called. Microsoft has no
per-token revoke endpoint, so disconnecting wipes the local tokens only."""

import os
import re
from urllib.parse import quote, urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.utils.dateparse import parse_datetime

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import required_time


def tenant(value) -> str:
    """The Microsoft tenant: `common` (default), `organizations`, `consumers`, a tenant id or a
    domain. Anything else is a configuration error (it goes into the authorize and token URLs)."""
    value = (value or "").strip() or "common"
    if not re.fullmatch(
        r"common|organizations|consumers|[0-9a-fA-F-]{36}|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", value
    ):
        raise ImproperlyConfigured("INTEGRATION_ONEDRIVE_TENANT is not a tenant id or domain.")
    return value


TENANT = tenant(os.environ.get("INTEGRATION_ONEDRIVE_TENANT"))

GRAPH = "https://graph.microsoft.com/v1.0"
FIELDS = "id,name,lastModifiedDateTime,eTag,cTag,webUrl,file,folder,deleted,parentReference"
_SHARE_SUFFIXES = (".sharepoint.com", ".sharepoint.us", ".sharepoint.cn")
_SHARE_HOSTS = {"onedrive.live.com", "1drv.ms"}
_ID = r"[A-Za-z0-9!_-]{1,128}"


def _identity(data: dict) -> tuple[str, str]:
    # The drive answers with Files.Read alone, so no User.Read scope is needed (D100).
    owner = (data.get("owner") or {}).get("user") or {}
    return str(data["id"]), str(owner.get("email", ""))


def split_id(external_id: str) -> tuple[str, str]:
    drive, item = external_id.split(".")
    return drive, item


def _checksum(file_facet: dict) -> str:
    hashes = file_facet.get("hashes") or {}
    if hashes.get("sha256Hash"):
        return f"sha256:{hashes['sha256Hash'].lower()}"
    if hashes.get("sha1Hash"):
        return f"sha1:{hashes['sha1Hash'].lower()}"
    if hashes.get("quickXorHash"):  # base64, not hex: change detection only (see apply_to_target)
        return f"quickxor:{hashes['quickXorHash']}"
    return ""


def _web_url(url) -> str:
    """The item's web link when it is https on a Microsoft file host, else ""."""
    parts = urlsplit(url or "")
    host = parts.hostname or ""
    ok = host in _SHARE_HOSTS or host.endswith(_SHARE_SUFFIXES)
    return url if parts.scheme == "https" and ok and not parts.port else ""


def _ref(item: dict) -> tuple[str, str]:
    """(drive id, item id); a shared-with-me entry points at the owner's drive."""
    item = item.get("remoteItem") or item
    return str(item["parentReference"]["driveId"]), str(item["id"])


def fetch_item(account, external_id):
    """`GET /drives/{drive}/items/{item}` with `$select`. None = gone: 404, 403 (access lost)
    or a deleted item."""
    drive, item = split_id(external_id)
    resp = http.send(
        "GET",
        f"{GRAPH}/drives/{quote(drive, safe='')}/items/{quote(item, safe='')}?$select={FIELDS}",
        provider=PROVIDER,
        account=account,
    )
    if resp.status_code in (403, 404, 410):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("OneDrive did not return the item")
    try:
        data = resp.json()
        if data.get("deleted"):
            return None
        file_facet = data.get("file", {})
        url = _web_url(data["webUrl"])
        if not url:
            raise ValueError
        return {
            "title": data["name"],
            "url": url,
            "mime_type": file_facet.get("mimeType", ""),
            "modified_at": required_time(data["lastModifiedDateTime"]),
            "version": str(data.get("eTag", "")),
            "checksum": _checksum(file_facet),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("OneDrive returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """Drive search (own files plus items shared with the person). Empty query: nothing."""
    query = (query or "").strip()[:200]
    if not query:
        return []
    # OData: a quote inside a string literal is doubled, then the whole is percent-encoded.
    url = f"{GRAPH}/me/drive/search(q='{quote(query.replace(chr(39), chr(39) * 2), safe='')}')"
    resp = http.send("GET", f"{url}?$select={FIELDS}&$top=20", provider=PROVIDER, account=account)
    if resp.status_code != 200:
        raise http.IntegrationError("OneDrive did not answer the search")
    try:
        out = []
        for entry in resp.json()["value"]:
            drive, item = _ref(entry)
            if entry.get("deleted"):
                continue
            modified = entry.get("lastModifiedDateTime")
            out.append(
                {
                    "id": f"{drive}.{item}",
                    "title": entry["name"],
                    "subtitle": (entry.get("parentReference") or {}).get("name", ""),
                    "modified": parse_datetime(modified) if modified else None,
                    "url": _web_url(entry.get("webUrl")),
                }
            )
        return out
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("OneDrive returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76: an empty dataset checksum takes the sha256 (or sha1) hash. quickXor is not a hex
    digest of a standard algorithm, so it never goes on the record."""
    checksum = meta.get("checksum") or ""
    ok = kind == "dataset" and checksum.startswith(("sha256:", "sha1:"))
    return {"checksum": checksum} if ok else {}


PROVIDER = Provider(
    name="onedrive",
    label="OneDrive and SharePoint",
    auth_type=AuthType.OAUTH2,
    category=Category.STORAGE,
    icon="onedrive",
    link_targets=frozenset(TARGETS),
    link_methods=("search",),  # a pasted share link needs the shares API: not offered (D101)
    scopes=("Files.Read.All", "offline_access"),
    authorize_url=f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize",
    token_url=f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
    revoke_url="",  # none exists for Microsoft tokens (D102)
    identity_url=f"{GRAPH}/me/drive?$select=id,owner",
    api_hosts=frozenset({"login.microsoftonline.com", "graph.microsoft.com"}),
    authorize_params={"response_mode": "query"},
    parse_identity=_identity,
    fetch_item=fetch_item,
    search_items=search_items,
    # business drive ids are `b!<base64url>`, personal ones hex; item ids are alphanumeric
    # (personal: `<drive>!<n>`). The two parts are joined with a dot, which neither contains.
    external_id_pattern=rf"^{_ID}\.{_ID}$",
    apply_to_target=apply_to_target,
)
