"""Figshare (ARCHITECTURE section 9, D117): public articles, read without credentials. Metadata
only: `GET /v2/articles/<id>` (title, DOI, version, dates, public page, each file's name and md5);
the files themselves are never requested. Pasted figshare.com article pages and
`10.6084/m9.figshare.<id>` DOIs are accepted."""

from urllib.parse import quote

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider
from integrations.providers._refs import aware, clean_doi, clean_text, files_checksum, read

API = "https://api.figshare.com/v2/articles"


def fetch_item(account, external_id):
    """None: not found or not public (the unauthenticated API answers 404 for those)."""
    try:
        data = read(PROVIDER, None, f"{API}/{quote(external_id, safe='')}", "Figshare", (403, 404))
        if data is None:
            return None
        files = [(f["name"], str(f.get("computed_md5", ""))) for f in data.get("files") or []]
        return {
            "title": clean_text(data["title"], 500),
            "url": data["url_public_html"],
            "mime_type": "",
            "modified_at": aware(data.get("modified_date")),
            "version": clean_text(data.get("version"), 100),
            "checksum": files_checksum(files, "figshare-manifest"),
            "doi": clean_doi(data.get("doi")),
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Figshare returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76 for a dataset record: an empty checksum takes the article's (see Zenodo, D116)."""
    return {"checksum": meta.get("checksum")} if kind == "dataset" else {}


PROVIDER = Provider(
    name="figshare",
    label="Figshare",
    auth_type=AuthType.PUBLIC,
    category=Category.REPOSITORY,
    icon="figshare",
    link_targets=frozenset(TARGETS) & {"dataset", "result", "manuscript"},
    link_methods=("paste_url",),
    api_hosts=frozenset({"api.figshare.com"}),
    link_hosts=frozenset({"figshare.com", "doi.org", "dx.doi.org"}),
    fetch_item=fetch_item,
    external_id_pattern=r"^[0-9]{1,12}$",
    # /articles/<type>/<title slug>/<id>[/<version>]: the slug has a non-digit, so the id is
    # never taken for it. Or a figshare DOI, with an optional .v<n> version suffix.
    url_pattern=(
        r"https://(?:figshare\.com/articles/[a-z_]+/(?=[^/?#]*[^/?#0-9])[^/?#]+/"
        r"|(?:dx\.)?doi\.org/(?i:10\.6084/m9\.figshare\.))"
        r"(?P<id>[0-9]{1,12})(?:(?:/|\.v)[0-9]{1,4})?/?"
    ),
    apply_to_target=apply_to_target,
)
