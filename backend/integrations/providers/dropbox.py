"""Dropbox (ARCHITECTURE section 9, D100, D103). Scopes `files.metadata.read` and
`account_info.read` only, offline access (refresh token). Metadata only: the RPC host
`api.dropboxapi.com` is the only host, and the content host is never named, so no file bytes can
be requested."""

import json
from urllib.parse import quote

from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import required_time

API = "https://api.dropboxapi.com"
_JSON = {"Content-Type": "application/json"}


def _identity(data: dict) -> tuple[str, str]:
    return str(data["account_id"]), str(data.get("email", ""))


def _web_url(path) -> str:
    """Dropbox has no per-id web link in metadata: the file's place in the person's own tree."""
    path = path if isinstance(path, str) and path.startswith("/") else ""
    folder, _, name = path.rpartition("/")
    base = f"https://www.dropbox.com/home{quote(folder, safe='/')}"
    return f"{base}?preview={quote(name, safe='')}" if name else base


def _meta(data: dict) -> dict:
    return {
        "title": data["name"],
        "url": _web_url(data.get("path_display")),
        "mime_type": "",
        "modified_at": (
            required_time(data["server_modified"]) if data.get("server_modified") else None
        ),
        "version": str(data.get("rev", "")),
        "checksum": (
            f"dropbox-content-hash:{data['content_hash'].lower()}"
            if data.get("content_hash")
            else ""
        ),
    }


def _not_found(resp) -> bool:
    try:
        error = resp.json()["error"]
        return error[".tag"] == "path" and error["path"][".tag"] in ("not_found", "malformed_path")
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def fetch_item(account, external_id):
    """`files/get_metadata` by `id:`. None = gone: path not found (409), 403 or deleted."""
    resp = http.send(
        "POST",
        f"{API}/2/files/get_metadata",
        provider=PROVIDER,
        account=account,
        headers=_JSON,
        data=json.dumps({"path": external_id}),
    )
    if resp.status_code == 403 or (resp.status_code == 409 and _not_found(resp)):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("Dropbox did not return the item")
    try:
        data = resp.json()
        return None if data.get(".tag") == "deleted" else _meta(data)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Dropbox returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """`files/search_v2` over names. Empty query: nothing (Dropbox needs a query)."""
    query = (query or "").strip()[:200]
    if not query:
        return []
    body = {"query": query, "options": {"max_results": 20, "filename_only": True}}
    resp = http.send(
        "POST",
        f"{API}/2/files/search_v2",
        provider=PROVIDER,
        account=account,
        headers=_JSON,
        data=json.dumps(body),
    )
    if resp.status_code != 200:
        raise http.IntegrationError("Dropbox did not answer the search")
    try:
        out = []
        for match in resp.json()["matches"]:
            data = match["metadata"]["metadata"]
            meta = _meta(data)
            out.append(
                {
                    "id": data["id"],
                    "title": meta["title"],
                    "subtitle": data.get("path_display", ""),
                    "modified": meta["modified_at"],
                    "url": meta["url"],
                }
            )
        return out
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Dropbox returned an unreadable answer") from None


@sensitive_variables("token", "tokens", "access")
def revoke(token) -> bool:
    """`auth/token/revoke` disables the bearer token used to call it (and its refresh token). The
    stored token is normally the refresh token, so trade it for an access token first; if that
    fails the stored token is itself an access token."""
    client_id, client_secret = PROVIDER.client()
    access = token
    exchange = http.send(
        "POST",
        PROVIDER.token_url,
        provider=PROVIDER,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    if exchange.status_code == 200:
        try:
            access = exchange.json()["access_token"]
        except (ValueError, KeyError, TypeError):
            return False
    resp = http.send(
        "POST",
        PROVIDER.revoke_url,
        provider=PROVIDER,
        headers={"Authorization": f"Bearer {access}"},
    )
    return resp.status_code == 200


def apply_to_target(kind, meta):
    """D76: an empty dataset checksum takes Dropbox's `content_hash`."""
    return {"checksum": meta.get("checksum", "")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="dropbox",
    label="Dropbox",
    auth_type=AuthType.OAUTH2,
    category=Category.STORAGE,
    icon="dropbox",
    link_targets=frozenset(TARGETS),
    link_methods=("search",),  # shared links need sharing.read: not requested (D103)
    scopes=("account_info.read", "files.metadata.read"),
    authorize_url="https://www.dropbox.com/oauth2/authorize",
    token_url=f"{API}/oauth2/token",
    revoke_url=f"{API}/2/auth/token/revoke",
    identity_url=f"{API}/2/users/get_current_account",
    identity_method="POST",
    api_hosts=frozenset({"api.dropboxapi.com"}),
    link_hosts=frozenset({"www.dropbox.com"}),
    authorize_params={"token_access_type": "offline"},
    parse_identity=_identity,
    fetch_item=fetch_item,
    search_items=search_items,
    revoke=revoke,
    external_id_pattern=r"^id:[A-Za-z0-9_-]{1,64}$",
    apply_to_target=apply_to_target,
)
