"""Edit in Word, Excel or PowerPoint: a copy of an upload put into this app's own folder in the
person's OneDrive (`/me/drive/special/approot`, scope `Files.ReadWrite.AppFolder`, which reaches
that folder and nothing else), where its web link opens in Office for the web.

Kept out of integrations/providers/onedrive.py on purpose: provider modules stay metadata-only
(D84, their strings are scanned for content paths such as `/content`). This is the one place that
sends file contents to Microsoft, and only with the person's own connection."""

import re
from urllib.parse import quote

from integrations import http
from integrations.providers import onedrive

APPS = {".docx": "Word", ".xlsx": "Excel", ".pptx": "PowerPoint"}
# ponytail: one PUT, kept small so it finishes inside INTEGRATION_HTTP_DEADLINE. Graph now takes up
# to 250 MB this way; raise it together with the deadline, or use an upload session.
MAX_BYTES = 4 * 1024 * 1024
_NOT_IN_NAMES = re.compile(r'[\x00-\x1f"*:<>?/\\|#%]')  # OneDrive refuses these (and / splits)


class NotAllowed(http.IntegrationError):
    """Microsoft refused the write: the app folder permission is missing or was withdrawn."""


def safe_name(stem: str, ext: str) -> str:
    stem = _NOT_IN_NAMES.sub("_", stem).strip(" .")[:200]
    return f"{stem or 'file'}{ext}"


def upload_copy(account, *, name, data) -> dict:
    """Simple upload into the app folder; a file of the same name is kept and this one renamed.
    Returns {"id": "<drive>.<item>", "name", "url"} from Microsoft's answer."""
    resp = http.send(
        "PUT",
        f"{onedrive.GRAPH}/me/drive/special/approot:/{quote(name, safe='')}:/content"
        "?@microsoft.graph.conflictBehavior=rename",
        provider=onedrive.PROVIDER,
        account=account,
        data=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    if resp.status_code == 403:
        raise NotAllowed("OneDrive did not allow the copy")
    if resp.status_code not in (200, 201):
        raise http.IntegrationError("OneDrive did not make the copy")
    try:
        item = resp.json()
        url = onedrive._web_url(item["webUrl"])
        if not url:
            raise ValueError
        drive = (item.get("parentReference") or {}).get("driveId", "")
        return {"id": f"{drive}.{item['id']}", "name": str(item["name"]), "url": url}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise http.IntegrationError("OneDrive returned an unreadable answer") from None
