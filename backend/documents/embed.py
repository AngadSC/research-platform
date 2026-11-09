"""Links that can be shown in a frame on the document page. A pasted URL goes through
`normalise`, which checks the host against the allowlist and returns the URL to frame and the URL
to open in a new tab. Anything else is a 400: the browser only ever frames what this returns.

Google links become `/preview`. `/edit`, `/preview` and `?embedded=true` all answer with no
X-Frame-Options or frame-ancestors for a public document (checked with curl, 2026-11); `/preview`
is what Drive's own "Embed item" produces, so it is the one form Google means to be framed. It is
read-only; editing happens through the Open link."""

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from rest_framework.exceptions import ValidationError

MAX_URL = 2000
_GOOGLE_PATH = re.compile(
    r"/(document|spreadsheets|presentation)(?:/u/\d+)?/d/([A-Za-z0-9_-]{20,})(?:/.*)?"
)


def _fail(message: str):
    return ValidationError({"embed_url": message})


def _google(path: str) -> tuple[str, str]:
    match = _GOOGLE_PATH.fullmatch(path)
    if not match:
        raise _fail("Paste the share link of a Google Doc, Sheet or Slides file.")
    base = f"https://docs.google.com/{match[1]}/d/{match[2]}"
    return f"{base}/preview", f"{base}/edit"


def _office_viewer(parts, query: dict) -> tuple[str, str]:
    src = query.get("src", "")
    if parts.path.lower() not in ("/op/embed.aspx", "/op/view.aspx") or not src.startswith(
        "https://"
    ):
        raise _fail("Paste an Office Online viewer link with an https file address.")
    return (
        f"https://view.officeapps.live.com/op/embed.aspx?src={quote(src, safe='')}",
        f"https://view.officeapps.live.com/op/view.aspx?src={quote(src, safe='')}",
    )


def _onedrive(parts, query: dict, raw: str) -> tuple[str, str]:
    resid = query.get("resid") or query.get("id")
    if not resid:
        raise _fail("Paste the OneDrive share link for a file (it must include the file's id).")
    params = {"resid": resid, "em": "2"}
    if query.get("authkey"):
        params["authkey"] = query["authkey"]
    return f"https://onedrive.live.com/embed?{urlencode(params)}", raw


def _sharepoint(parts, pairs: list, raw: str) -> tuple[str, str]:
    if parts.path in ("", "/"):
        raise _fail("Paste the SharePoint share link for a file.")
    query = urlencode([*(p for p in pairs if p[0] != "action"), ("action", "embedview")])
    return f"https://{parts.hostname}{quote(parts.path, safe='/:%')}?{query}", raw


def normalise(raw: str) -> tuple[str, str]:
    """(url to frame, url to open). Raises a 400 naming `embed_url` for anything not allowed."""
    raw = (raw or "").strip()
    frame, opener = _route(raw) if len(raw) <= MAX_URL else ("", "")
    if not frame or len(frame) > MAX_URL or len(opener) > MAX_URL:
        raise _fail("That link is too long.")
    return frame, opener


def _route(raw: str) -> tuple[str, str]:
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise _fail("That is not a valid link.") from exc
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        raise _fail("Only plain https links can be embedded.")
    pairs = parse_qsl(parts.query)
    query = dict(pairs)
    if host == "docs.google.com":
        return _google(parts.path)
    if host == "view.officeapps.live.com":
        return _office_viewer(parts, query)
    if host == "onedrive.live.com":
        return _onedrive(parts, query, raw)
    if host.endswith(".sharepoint.com"):
        return _sharepoint(parts, pairs, raw)
    if host == "1drv.ms":
        # ponytail: not resolved server-side (an outbound fetch for a paste). Add when asked.
        raise _fail(
            "Shortened 1drv.ms links can't be embedded. Open the link, then paste the full address "
            "from your browser."
        )
    raise _fail("Only Google Docs and Microsoft Office links can be embedded.")
