"""Borealis (D183): the Canadian Dataverse repository at borealisdata.ca (University of Alberta
and other Canadian universities). Public, read without credentials; metadata only. One call per
item to the Dataverse native API for the latest *published* version with `excludeFiles=true`, so
the answer carries no file list, no file ids and no draft. File access and download endpoints are
never requested. A dataset is named by its DOI (prefix 10.5683, checked against DataCite)."""

from urllib.parse import quote

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import aware, clean_text, read

HOST = "https://borealisdata.ca"
_SEG = r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}"  # starts alphanumeric: no "." or ".." segment
_DOI = rf"10\.5683/{_SEG}(?:/{_SEG}){{0,3}}"


def _title(version):
    for field in version["metadataBlocks"]["citation"]["fields"]:
        if field["typeName"] == "title":
            return clean_text(field["value"], 500)
    raise KeyError("title")


def fetch_item(account, external_id):
    """The latest published version's metadata. None: unknown, unpublished (only a draft),
    restricted or deaccessioned; the API answers 404 or 403 for those."""
    pid = quote(f"doi:{external_id}", safe="")
    try:
        data = read(
            PROVIDER,
            None,
            f"{HOST}/api/datasets/:persistentId/versions/:latest-published"
            f"?persistentId={pid}&excludeFiles=true",
            "Borealis",
            (403, 404),
        )
        if data is None:
            return None
        version = data["data"]
        if version["versionState"] != "RELEASED":
            return None
        major, minor = int(version["versionNumber"]), int(version["versionMinorNumber"])
        return {
            "title": _title(version),
            "url": f"{HOST}/dataset.xhtml?persistentId={pid}",
            "mime_type": "",
            "modified_at": aware(version.get("lastUpdateTime") or version.get("releaseTime")),
            "version": f"{major}.{minor}",
            "checksum": "",
            "doi": external_id,
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Borealis returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76: an empty dataset version label takes the Dataverse version (major.minor). Dataverse
    holds file hashes only in the file list, which is never requested, so no checksum."""
    return {"version_label": meta.get("version")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="borealis",
    label="Borealis",
    auth_type=AuthType.PUBLIC,
    category=Category.REPOSITORY,
    icon="borealis",
    link_targets=frozenset(TARGETS) & {"dataset", "result", "manuscript", "project"},
    link_methods=("paste_url",),
    api_hosts=frozenset({"borealisdata.ca"}),
    link_hosts=frozenset({"borealisdata.ca", "doi.org", "dx.doi.org"}),
    fetch_item=fetch_item,
    external_id_pattern=rf"^{_DOI}$",
    url_pattern=(
        rf"https://(?:borealisdata\.ca/(?:dataset\.xhtml|citation)\?persistentId=(?i:doi(?::|%3A))"
        rf"|(?:dx\.)?doi\.org/)(?P<id>{_DOI})(?:&version=[0-9.]{{1,12}})?"
    ),
    apply_to_target=apply_to_target,
)
