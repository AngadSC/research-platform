"""Zenodo (ARCHITECTURE section 9, D116): public records, read without credentials. Metadata
only: the record's JSON (title, DOI, version, dates, link and each file's name and md5); the
files themselves are never requested. A record is named by its numeric id; pasted
`10.5281/zenodo.<n>` DOIs resolve to that id."""

from urllib.parse import quote

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import aware, clean_doi, clean_text, files_checksum, read

API = "https://zenodo.org/api/records"


def fetch_item(account, external_id):
    """`GET /api/records/<id>`. None: not found, restricted (403) or deleted (410)."""
    try:
        data = read(
            PROVIDER, None, f"{API}/{quote(external_id, safe='')}", "Zenodo", (403, 404, 410)
        )
        if data is None:
            return None
        meta = data["metadata"]
        files = [(f["key"], str(f.get("checksum", "")).removeprefix("md5:")) for f in data["files"]]
        return {
            "title": clean_text(meta["title"], 500),
            "url": data["links"]["html"],
            "mime_type": "",
            "modified_at": aware(data.get("updated") or data.get("modified")),
            "version": clean_text(meta.get("version"), 100),
            "checksum": files_checksum(files, "zenodo-manifest"),
            "doi": clean_doi(data.get("doi") or meta.get("doi")),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Zenodo returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76 for a dataset record: an empty checksum takes the record's (one file: its md5;
    several: a manifest digest). `version_label` is the person's own and is never touched."""
    return {"checksum": meta.get("checksum")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="zenodo",
    label="Zenodo",
    auth_type=AuthType.PUBLIC,
    category=Category.REPOSITORY,
    icon="zenodo",
    link_targets=frozenset(TARGETS) & {"dataset", "result", "manuscript"},
    link_methods=("paste_url",),
    api_hosts=frozenset({"zenodo.org"}),
    link_hosts=frozenset({"zenodo.org", "doi.org", "dx.doi.org"}),
    fetch_item=fetch_item,
    external_id_pattern=r"^[0-9]{1,12}$",
    url_pattern=(
        r"https://(?:zenodo\.org/records?/|(?:dx\.)?doi\.org/(?i:10\.5281/zenodo\.))"
        r"(?P<id>[0-9]{1,12})/?"
    ),
    apply_to_target=apply_to_target,
)
