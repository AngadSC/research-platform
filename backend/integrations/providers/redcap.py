"""REDCap (ARCHITECTURE section 9, D110, D111). Self-hosted: the person gives their instance
address and a project API token. Metadata only: the single API action used is `content=project`
(project information). Never records, files, reports, logs or the data dictionary."""

import hashlib
import json
from urllib.parse import quote

from django.views.decorators.debug import sensitive_variables

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider

# The only form body this module ever sends, apart from the token that `sign` adds.
PROJECT_INFO = {"content": "project", "format": "json", "returnFormat": "json"}
# D111: what "changed since linked" hashes. Settings a lab would notice changing; no counts, no
# participant data, no times that move without a change.
STABLE_FIELDS = (
    "project_title",
    "purpose",
    "is_longitudinal",
    "surveys_enabled",
    "in_production",
    "has_repeating_instruments_or_events",
    "record_autonumbering_enabled",
    "randomization_enabled",
    "project_irb_number",
    "project_grant_number",
)


@sensitive_variables("key", "secret", "kwargs")
def sign(kwargs, key, secret):
    """REDCap takes the token in the form body, not a header."""
    return {**kwargs, "data": {**(kwargs.get("data") or {}), "token": key}}


def _project_info(account) -> dict | None:
    """The project the token belongs to. None when REDCap refuses the token (403)."""
    resp = http.send(
        "POST",
        account.instance_url.rstrip("/") + "/api/",
        provider=PROVIDER,
        account=account,
        data=dict(PROJECT_INFO),
    )
    if resp.status_code == 403:
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("REDCap did not return the project")
    try:
        data = resp.json()
        if not isinstance(data, dict):  # REDCap answers {"error": ...} or a list on failure
            raise ValueError
        data["project_id"] = str(int(data["project_id"]))
        data["project_title"] = str(data["project_title"])
        return data
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("REDCap returned an unreadable answer") from None


def identify(account):
    info = _project_info(account)
    if info is None:
        raise http.AccountUnavailable("REDCap refused the token")
    return info["project_id"], info["project_title"][:100]


def _meta(account, info):
    stable = {k: info.get(k) for k in STABLE_FIELDS}
    digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
    pid = quote(info["project_id"], safe="")
    return {
        "title": info["project_title"],
        "url": f"{account.instance_url.rstrip('/')}/index.php?pid={pid}",
        "mime_type": "",
        "modified_at": None,  # REDCap project info carries no modified time
        "version": "",
        "checksum": f"sha256:{digest}",
    }


def fetch_item(account, external_id):
    """None when the token is refused or belongs to a different project than the link."""
    info = _project_info(account)
    if info is None or info["project_id"] != external_id:
        return None
    return _meta(account, info)


def search_items(account, query, target_kind):
    """A token opens one project, so that project is the only result."""
    info = _project_info(account)
    if info is None:
        return []
    meta = _meta(account, info)
    return [
        {
            "id": info["project_id"],
            "title": meta["title"],
            "subtitle": f"Project {info['project_id']}",
            "modified": None,
            "url": meta["url"],
        }
    ]


PROVIDER = Provider(
    name="redcap",
    label="REDCap",
    auth_type=AuthType.API_KEY,
    category=Category.DATA_CAPTURE,
    icon="redcap",
    link_targets=frozenset({"dataset", "project"}),
    link_methods=("search",),
    connect_fields=(
        ConnectField(
            "instance_url",
            "REDCap address",
            "The address of your REDCap, for example https://redcap.example.edu/redcap "
            "(the API is at that address plus /api/).",
        ),
        ConnectField(
            "api_key",
            "Project API token",
            "In the project: Applications > API. The token belongs to one project. We only "
            "read the project's title and settings, never records or files.",
        ),
    ),
    needs_instance_url=True,
    identify=identify,
    sign=sign,
    fetch_item=fetch_item,
    search_items=search_items,
    external_id_pattern=r"^[0-9]{1,10}$",
)
