"""Google Drive (ARCHITECTURE section 9, D64, D70, D76 to D78). Scope `drive.file` only: per-file
access to what the person picks in the Google Picker. Metadata only: never `alt=media`, an export
or a download."""

from urllib.parse import quote

from django.utils.dateparse import parse_datetime

from integrations import http
from integrations.providers import TARGETS, AuthType, Category, Provider

FIELDS = "id,name,mimeType,modifiedTime,md5Checksum,version,webViewLink,trashed"
_RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded"}


def _identity(data: dict) -> tuple[str, str]:
    # Drive `about` works with drive.file alone, so no openid/email scope is needed (D64).
    user = data["user"]
    return str(user["permissionId"]), str(user.get("emailAddress", ""))


def fetch_item(account, external_id):
    """Drive v3 `files.get`, metadata fields only. None = "no longer available": 404, 403
    (access lost) or trashed."""
    resp = http.send(
        "GET",
        f"https://www.googleapis.com/drive/v3/files/{quote(external_id, safe='')}?fields={FIELDS}",
        provider=PROVIDER,
        account=account,
    )
    if resp.status_code == 403:
        try:
            reasons = {e.get("reason") for e in resp.json()["error"]["errors"]}
        except (ValueError, KeyError, TypeError, AttributeError):
            reasons = set()
        if reasons & _RATE_REASONS:  # throttled, not lost
            raise http.IntegrationError("Google Drive is rate limiting requests")
    if resp.status_code in (403, 404):
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("Google Drive did not return the file")
    try:
        data = resp.json()
        if data.get("trashed"):
            return None
        md5 = data.get("md5Checksum")
        return {
            "title": data["name"],
            "url": data["webViewLink"],
            "mime_type": data.get("mimeType", ""),
            "modified_at": parse_datetime(data["modifiedTime"]),
            "version": str(data.get("version", "")),
            "checksum": f"md5:{md5.lower()}" if md5 else "",
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("Google Drive returned an unreadable answer") from None


def apply_to_target(kind, meta):
    """D76: a dataset record's empty checksum takes the md5, else `drive-version:<n>` (Google
    Docs and Sheets have no md5)."""
    if kind != "dataset":
        return {}
    version = (meta.get("version") or "").strip()
    return {
        "checksum": meta.get("checksum")
        or (f"drive-version:{version}" if version.isdigit() else "")
    }


PROVIDER = Provider(
    name="google_drive",
    label="Google Drive",
    auth_type=AuthType.OAUTH2,
    category=Category.STORAGE,
    icon="google-drive",
    link_targets=frozenset(TARGETS),
    link_methods=("picker",),  # drive.file sees only picked files: no search, no pasted URLs
    scopes=("https://www.googleapis.com/auth/drive.file",),
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    token_url="https://oauth2.googleapis.com/token",
    revoke_url="https://oauth2.googleapis.com/revoke",
    identity_url="https://www.googleapis.com/drive/v3/about?fields=user(permissionId,emailAddress)",
    api_hosts=frozenset({"www.googleapis.com", "oauth2.googleapis.com"}),
    # offline + consent: always get a refresh token. No include_granted_scopes: it makes Google
    # add every scope this client was ever given, which the connect then refuses (D221).
    authorize_params={"access_type": "offline", "prompt": "consent"},
    parse_identity=_identity,
    fetch_item=fetch_item,
    external_id_pattern=r"^[A-Za-z0-9_-]+$",
    link_hosts=frozenset({"docs.google.com", "drive.google.com"}),
    apply_to_target=apply_to_target,
)
