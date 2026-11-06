"""Qualtrics (ARCHITECTURE section 9, D112). The person gives an API token and their datacenter
or brand address (`*.qualtrics.com`). Metadata only: the survey list and one survey's metadata.
Never responses, exports, distributions or the survey's questions."""

from datetime import datetime
from urllib.parse import quote, urlencode

from django.utils.dateparse import parse_datetime

from integrations import http
from integrations.providers import AuthType, Category, ConnectField, Provider

MAX_PAGES = 5  # the list is paged; stop here rather than walk a huge account


def _sign(kwargs, key, secret):
    return {**kwargs, "headers": {**kwargs.get("headers", {}), "X-API-TOKEN": key}}


def _get(account, path):
    url = account.instance_url.rstrip("/") + path
    return http.send("GET", url, provider=PROVIDER, account=account)


def _identity(data):
    result = data["result"]
    return str(result["userId"]), str(result.get("email") or result.get("userName") or "")


def _web_url(account, survey_id):
    return f"{account.instance_url.rstrip('/')}/survey-builder/{quote(survey_id, safe='')}/edit"


def _date(value) -> datetime | None:
    return parse_datetime(value) if isinstance(value, str) and value else None


def fetch_item(account, external_id):
    """Survey metadata only (`.../metadata`): None = 404 or no access."""
    resp = _get(account, f"/API/v3/survey-definitions/{quote(external_id, safe='')}/metadata")
    if resp.status_code in (403, 404):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("Qualtrics did not return the survey")
    try:
        result = resp.json()["result"]
        modified = str(result["LastModified"])
        return {
            "title": str(result["SurveyName"]),
            "url": _web_url(account, external_id),
            "mime_type": "",
            "modified_at": _date(modified),
            "version": modified,
            "checksum": "",
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Qualtrics returned an unreadable answer") from None


def search_items(account, query, target_kind):
    """The person's surveys whose name contains the query, newest change first."""
    needle = (query or "").strip().lower()
    found, offset = [], 0
    for _ in range(MAX_PAGES):
        resp = _get(account, f"/API/v3/surveys?{urlencode({'offset': offset})}")
        if resp.status_code != 200:
            raise http.IntegrationError("Qualtrics did not answer the search")
        try:
            result = resp.json()["result"]
            for s in result["elements"]:
                name = str(s["name"])
                if needle in name.lower():
                    found.append(
                        {
                            "id": str(s["id"]),
                            "title": name,
                            "subtitle": "Active" if s.get("isActive") else "Inactive",
                            "modified": _date(s.get("lastModified")),
                            "url": _web_url(account, str(s["id"])),
                        }
                    )
            offset += len(result["elements"])
            if not result.get("nextPage") or not result["elements"]:
                break
        except (ValueError, KeyError, TypeError, AttributeError):
            raise http.IntegrationError("Qualtrics returned an unreadable answer") from None
    found.sort(key=lambda r: r["modified"].timestamp() if r["modified"] else 0, reverse=True)
    return found


PROVIDER = Provider(
    name="qualtrics",
    label="Qualtrics",
    auth_type=AuthType.API_KEY,
    category=Category.DATA_CAPTURE,
    icon="qualtrics",
    link_targets=frozenset({"dataset", "project"}),
    link_methods=("search",),
    connect_fields=(
        ConnectField(
            "instance_url",
            "Qualtrics address",
            "Your datacenter or brand address, for example https://yourbrand.yul1.qualtrics.com "
            "(Account Settings > Qualtrics IDs shows the datacenter).",
        ),
        ConnectField(
            "api_key",
            "API token",
            "Account Settings > Qualtrics IDs > API > Generate Token. We only read survey "
            "names and dates only.",
        ),
    ),
    needs_instance_url=True,
    # D112: only a host under qualtrics.com (at least one label before it), on top of the
    # deployment allowlist.
    instance_host_pattern=r"(?:[a-z0-9-]+\.)+qualtrics\.com",
    identity_url="/API/v3/whoami",
    parse_identity=_identity,
    sign=_sign,
    fetch_item=fetch_item,
    search_items=search_items,
    external_id_pattern=r"^SV_[A-Za-z0-9]{8,20}$",
)
