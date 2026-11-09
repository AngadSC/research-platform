"""Plain text from an uploaded PDF, a page range at a time, on demand.

A PDF is hostile input and pypdf is a pure-Python parser of it, so pypdf never runs in the web
process. `read_pages` feeds the bytes to this same file run as a short-lived child (`-I`, empty
environment so no secrets, stdout as a pipe) that sets its own address-space, CPU and file-write
limits before it imports pypdf, and is killed after `TIMEOUT` seconds. A hang, a decompression bomb
or a crash costs that one child. Only the standard library at module level, for that reason.
"""

import io
import json
import subprocess
import sys
import threading
import unicodedata

MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 2000
MAX_RANGE = 20  # pages in one call
# Non-ASCII text is escaped to six JSON characters each, and a tool result may be 100,000 characters
MAX_CHARS = 15_000
TIMEOUT = 20  # seconds, wall clock and CPU
MEMORY = 1024**3
_SLOTS = threading.BoundedSemaphore(4)  # concurrent children per web process

_MESSAGES = {
    "encrypted": "This PDF is password-protected, so its text cannot be read. Upload an "
    "unprotected copy.",
    "too_many_pages": f"This PDF has more than {MAX_PAGES} pages, too many to read.",
    "unreadable": "The text of this PDF could not be read; the file may be damaged.",
}


class PdfTextError(Exception):
    """A message the person (or model) can act on."""


def _clean(text: str) -> str:
    """Drop what a reader can't see: control, format (zero-width, bidi, tag) and unassigned
    characters. Invisible text is the usual way to hide instructions for a model in a PDF."""
    return "".join(
        c for c in text if c in "\n\t" or unicodedata.category(c) not in ("Cc", "Cf", "Co", "Cn")
    ).strip()


def read_pages(data: bytes, first: int, last: int) -> dict:
    """Pages `first` to `last` (1-based, inclusive, capped at MAX_RANGE and MAX_CHARS). Returns
    {"total_pages", "pages": [{"page", "text"}], "next_page": int | None, "cut": bool}; `cut` means
    the last page returned was too long to return whole. Raises PdfTextError."""
    if len(data) > MAX_BYTES:
        raise PdfTextError("This PDF is too large to read (50 MB maximum).")
    if not _SLOTS.acquire(timeout=5):
        raise PdfTextError("Too many PDFs are being read right now. Try again in a moment.")
    try:
        done = subprocess.run(  # noqa: S603 (our own interpreter and file; the PDF is stdin)
            [
                sys.executable,
                "-I",
                "-B",
                __file__,
                str(first),
                str(min(last, first + MAX_RANGE - 1)),
            ],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # pypdf warns per bad object; nothing here needs keeping
            timeout=TIMEOUT,
            env={},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise PdfTextError("Reading this PDF took too long, so it was stopped.") from None
    finally:
        _SLOTS.release()
    try:
        out = json.loads(done.stdout)
    except ValueError:  # killed by a limit, or crashed
        raise PdfTextError(_MESSAGES["unreadable"]) from None
    if "error" in out:
        if out["error"] == "out_of_range":
            raise PdfTextError(f"This PDF has {out['total_pages']} page(s).")
        raise PdfTextError(_MESSAGES[out["error"]])
    pages = [{"page": p["page"], "text": _clean(p["text"])} for p in out["pages"]]
    if not any(p["text"] for p in pages):
        raise PdfTextError(
            f"No text could be extracted from page(s) {pages[0]['page']}-{pages[-1]['page']}. The "
            "PDF may be scanned images, and OCR is not available: read it in the viewer instead."
        )
    following = pages[-1]["page"] + 1
    return {
        "total_pages": out["total_pages"],
        "pages": pages,
        "next_page": following if following <= out["total_pages"] else None,
        "cut": out["cut"],
    }


def _extract(data: bytes, first: int, last: int) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):  # a blank password opens many PDFs
        return {"error": "encrypted"}
    total = len(reader.pages)
    if total > MAX_PAGES:
        return {"error": "too_many_pages"}
    if first > total:
        return {"error": "out_of_range", "total_pages": total}
    pages, used, cut = [], 0, False
    for n in range(first, min(last, total) + 1):
        text = reader.pages[n - 1].extract_text() or ""
        room = MAX_CHARS - used
        if len(text) > room and pages:  # the next call starts on this page, whole
            break
        pages.append({"page": n, "text": text[:room]})
        used += len(text[:room])
        cut = len(text) > room
    return {"total_pages": total, "pages": pages, "cut": cut}


def _child() -> None:
    import resource

    for limit, value in (
        (resource.RLIMIT_AS, MEMORY),
        (resource.RLIMIT_CPU, TIMEOUT),
        (resource.RLIMIT_FSIZE, 0),
    ):
        resource.setrlimit(limit, (value, value))
    try:
        out = _extract(sys.stdin.buffer.read(), int(sys.argv[1]), int(sys.argv[2]))
    except Exception:  # noqa: BLE001 (any parser failure on a hostile file is the same answer)
        out = {"error": "unreadable"}
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":
    _child()
