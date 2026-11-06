"""FRDR (D184): the Federated Research Data Repository. FRDR's own search API (Globus Search)
needs a Globus login, so the reliable public route is the DataCite REST API: every FRDR dataset
has a DOI under 10.20383, and DataCite answers `GET /dois/<doi>` without credentials. Metadata
only: title, DOI, version if any, record update time and the dataset page. A dataset is named by
its DOI; a pasted FRDR page address (which carries a UUID, not the DOI) is resolved with one
DataCite search on the page address. Nothing is requested from frdr-dfdr.ca itself."""

from urllib.parse import quote

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import aware, clean_doi, clean_text, read

API = "https://api.datacite.org/dois"
PAGE = "https://www.frdr-dfdr.ca/repo/dataset"
_DOI = r"10\.20383/[A-Za-z0-9][A-Za-z0-9._-]{0,59}"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _find_by_page(uuid):
    """The DataCite record whose landing page is this FRDR dataset page, or None."""
    query = f'url:"{PAGE}/{uuid}" OR url:"https://frdr-dfdr.ca/repo/dataset/{uuid}"'
    data = read(PROVIDER, None, f"{API}?query={quote(query, safe='')}&page%5Bsize%5D=1", "DataCite")
    rows = data["data"]
    return rows[0] if rows else None


def fetch_item(account, external_id):
    """None when DataCite has no such findable DOI, or the DOI is not an FRDR one."""
    try:
        if external_id.startswith("10."):
            data = read(PROVIDER, None, f"{API}/{quote(external_id, safe='')}", "DataCite")
            row = data["data"] if data is not None else None
        else:
            row = _find_by_page(external_id)
        if row is None:
            return None
        attrs = row["attributes"]
        doi = clean_doi(attrs["doi"])
        if not doi.startswith("10.20383/"):
            return None
        return {
            "title": clean_text(attrs["titles"][0]["title"], 500),
            "url": attrs.get("url") or f"https://doi.org/{doi}",
            "mime_type": "",
            "modified_at": aware(attrs.get("updated")),
            "version": clean_text(attrs.get("version"), 100),
            "checksum": "",
            "doi": doi,
        }
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise http.IntegrationError("DataCite returned an unreadable answer") from None


PROVIDER = Provider(
    name="frdr",
    label="FRDR",
    auth_type=AuthType.PUBLIC,
    category=Category.REPOSITORY,
    icon="frdr",
    link_targets=frozenset(TARGETS) & {"dataset", "result", "manuscript", "project"},
    link_methods=("paste_url",),
    api_hosts=frozenset({"api.datacite.org"}),
    link_hosts=frozenset({"www.frdr-dfdr.ca", "frdr-dfdr.ca", "doi.org", "dx.doi.org"}),
    fetch_item=fetch_item,
    external_id_pattern=rf"^(?:{_DOI}|{_UUID})$",
    url_pattern=(
        rf"https://(?:(?:www\.)?frdr-dfdr\.ca/repo/dataset/|(?:dx\.)?doi\.org/)"
        rf"(?P<id>{_DOI}|{_UUID})/?"
    ),
)
