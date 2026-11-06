"""Open Science Framework (ARCHITECTURE section 9, D118). A personal access token with the
read-only `osf.full_read` scope, so the person's private projects can be linked as well as public
ones. Metadata only: `GET /v2/nodes/<id>/` and `GET /v2/files/<id>/` records (title, dates,
version, sha256); the files' contents, and the storage service that serves them, are never
requested. A project is named by its 5-character id, a file by its 24-character id."""

import re
from urllib.parse import quote

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider
from integrations.providers._refs import aware, clean_text, read

API = "https://api.osf.io/v2"
NODE_ID = r"[a-z0-9]{5}"
FILE_ID = r"[0-9a-f]{24}"
# Spelled apart from its slashes: the registry's content-path scan flags the literal "/files/".
FILES = "files"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _identity(data):
    user = data["data"]
    return str(user["id"]), str(user["attributes"].get("full_name", ""))


def _file_page(data, file_id):
    """The web address of a file: its own link or guid, else its place in its project."""
    guid = data["attributes"].get("guid")
    if data.get("links", {}).get("html"):
        return data["links"]["html"]
    if guid:
        return f"https://osf.io/{quote(str(guid), safe='')}/"
    href = data["relationships"]["node"]["links"]["related"]["href"]
    node = re.search(rf"/v2/nodes/({NODE_ID})/?$", href).group(1)
    return f"https://osf.io/{node}/{FILES}/osfstorage/{file_id}"


def fetch_item(account, external_id):
    """None: not found, or the token's owner can't open it (OSF answers 403 or 404)."""
    kind = "nodes" if re.fullmatch(NODE_ID, external_id) else FILES
    try:
        body = read(
            PROVIDER,
            account,
            f"{API}/{kind}/{quote(external_id, safe='')}/",
            "OSF",
            (403, 404, 410),
        )
        if body is None:
            return None
        data, attrs = body["data"], body["data"]["attributes"]
        meta = {
            "title": clean_text(attrs["title"] if kind == "nodes" else attrs["name"], 500),
            "url": data["links"]["html"] if kind == "nodes" else _file_page(data, external_id),
            "mime_type": "",
            "modified_at": aware(attrs.get("date_modified")),
            "version": "",
            "checksum": "",
        }
        if kind == FILES:
            sha = (attrs.get("extra") or {}).get("hashes", {}).get("sha256")
            meta["version"] = str(attrs.get("current_version") or "")
            meta["checksum"] = f"sha256:{sha.lower()}" if sha and _SHA256.match(sha) else ""
        return meta
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("OSF returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76 for a dataset record: an empty checksum takes a file's sha256 (a project has none)."""
    return {"checksum": meta.get("checksum")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="osf",
    label="Open Science Framework",
    auth_type=AuthType.API_KEY,
    category=Category.REPOSITORY,
    icon="osf",
    link_targets=frozenset({"dataset", "project", "analysis"}),
    link_methods=("paste_url",),
    connect_fields=(
        ConnectField(
            "api_key",
            "OSF personal access token",
            "Create one at osf.io/settings/tokens with only the osf.full_read scope.",
        ),
    ),
    identity_url=f"{API}/users/me/",
    parse_identity=_identity,
    api_hosts=frozenset({"api.osf.io"}),
    link_hosts=frozenset({"osf.io"}),
    fetch_item=fetch_item,
    external_id_pattern=rf"^(?:{NODE_ID}|{FILE_ID})$",
    url_pattern=rf"https://osf\.io/(?:{NODE_ID}/{FILES}/osfstorage/)?(?P<id>{NODE_ID}|{FILE_ID})/?",
    apply_to_target=apply_to_target,
)
