"""Reading a Google Drive file's contents for the AI tool read_file (VISION B4, D269).

Kept out of integrations/providers/google_drive.py on purpose: provider modules stay
metadata-only (D84, checked by integrations/tests/provider_contract.py). This module is the one
place that downloads or exports Drive content, and only with the asking person's own account.
With drive.file Google opens just the files that person picked or that the app created; anything
else is a 403 or 404, which reads as None here.
"""

from urllib.parse import quote

from integrations import http
from integrations.providers import google_drive

EXPORTS = {  # Google's own formats: Docs and Slides as text, Sheets as CSV (first sheet only)
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _get_capped(account, url, max_bytes):
    """GET with the body capped at `max_bytes`. None for a 403 or 404 that is not throttling."""
    with http.budget(max_bytes=max_bytes):
        resp = http.send("GET", url, provider=google_drive.PROVIDER, account=account)
    if resp.status_code in (403, 404):
        try:
            reasons = {e.get("reason") for e in resp.json()["error"]["errors"]}
        except (ValueError, KeyError, TypeError, AttributeError):
            reasons = set()
        if reasons & google_drive._RATE_REASONS:
            raise http.IntegrationError("Google Drive is rate limiting requests")
        if "exportSizeLimitExceeded" in reasons:
            raise http.ResponseTooLarge("Google Drive: the file is too large to export")
        return None
    if resp.status_code != 200:
        raise http.IntegrationError("Google Drive did not return the file")
    return resp


def read_content(account, external_id, max_bytes):
    """(bytes, their MIME type) of one Drive file, or None when this person can't open it (403,
    404, trashed). Docs, Sheets and Slides are exported (EXPORTS). Any other file is downloaded
    only if Drive's own size for it is within `max_bytes`, and every body is cut off past
    `max_bytes` while it is read. Raises http.ResponseTooLarge or http.IntegrationError."""
    base = f"https://www.googleapis.com/drive/v3/files/{quote(external_id, safe='')}"
    resp = _get_capped(account, f"{base}?fields=mimeType,size,trashed", max_bytes)
    if resp is None:
        return None
    try:
        meta = resp.json()
        mime, size = str(meta.get("mimeType", "")), int(meta.get("size", 0))
        trashed = meta.get("trashed")
    except (ValueError, TypeError, AttributeError):
        raise http.IntegrationError("Google Drive returned an unreadable answer") from None
    if trashed:
        return None
    if mime in EXPORTS:
        mime = EXPORTS[mime]
        url = f"{base}/export?mimeType={quote(mime, safe='')}"
    elif size > max_bytes:
        raise http.ResponseTooLarge("Google Drive: the file is too large")
    else:
        url = f"{base}?alt=media"
    resp = _get_capped(account, url, max_bytes)
    return None if resp is None else (resp.content, mime)
