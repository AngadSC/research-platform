"""Suggestions for an ethics or funding record, read from the form a person is attaching.

This only suggests: the answer goes to the form on screen, the person checks and saves it, and
the file itself is not kept by this step. Nothing here calls an outside service or an AI model.
The text comes from `papers.pdftext` (a PDF is hostile input, so it is read in a sandboxed child).
What a form says is data: it is length-limited and never followed as an instruction.

Forms differ, so the reader is deliberately plain. It looks for a label ("Approval number",
"Expiry date") and takes what follows it, on the same line or the next one. A field it is not
sure of is left out, so a blank is honest and a wrong guess is rare.
"""

import calendar
import datetime
import re
from decimal import Decimal, InvalidOperation

from papers import pdftext

MAX_PAGES = 12  # the details of a form are on its first pages
KINDS = ("ethics", "funding")

_SEP = r"\s*(?:[:\-–—]|\bis\b)?\s*"


_ALTS: list[str] = []


def _label(*names: str) -> re.Pattern:
    alt = "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in names)
    _ALTS.append(alt)
    return re.compile(rf"^\W*(?:{alt}){_SEP}(.*)$", re.I)


LABELS = {
    "approval_number": _label(
        "approval number",
        "approval no",
        "certificate number",
        "certificate no",
        "protocol number",
        "protocol no",
        "study number",
        "ethics number",
        "reb number",
        "irb number",
        "file number",
        "application number",
        "study id",
        "protocol id",
    ),
    "title": _label(
        "title of study",
        "title of the study",
        "study title",
        "project title",
        "title of project",
        "title of the project",
        "protocol title",
        "title of research",
        "research title",
    ),
    "board": _label(
        "ethics board",
        "review board",
        "reviewing board",
        "reviewing committee",
        "ethics committee",
        "issued by",
        "approving body",
        "approved by",
    ),
    "approval_date": _label(
        "approval date",
        "date of approval",
        "date approved",
        "approved on",
        "date of initial approval",
        "initial approval date",
        "date issued",
        "issue date",
    ),
    "expiry_date": _label(
        "expiry date",
        "expiration date",
        "date of expiry",
        "approval expires",
        "approval expiry",
        "expires on",
        "expires",
        "valid until",
        "valid through",
        "approval valid until",
        "renewal due",
        "renewal date",
    ),
    "funder": _label(
        "funding agency",
        "granting agency",
        "funder",
        "sponsor",
        "awarded by",
        "funding body",
        "funding organization",
        "funding organisation",
        "agency",
        "grantor",
    ),
    "program": _label(
        "funding opportunity",
        "funding program",
        "funding programme",
        "grant program",
        "competition",
        "grant title",
        "award title",
        "award type",
        "program",
        "programme",
    ),
    "award_number": _label(
        "award number",
        "award no",
        "grant number",
        "grant no",
        "grant id",
        "award id",
        "application id",
        "application number",
        "file number",
        "reference number",
        "agreement number",
    ),
    "amount": _label(
        "amount awarded",
        "award amount",
        "total award",
        "total funding",
        "total amount",
        "amount approved",
        "amount",
    ),
    "start_date": _label(
        "start date",
        "project start",
        "term start",
        "effective date",
        "funding start",
    ),
    "end_date": _label(
        "end date",
        "project end",
        "term end",
        "funding end",
        "completion date",
    ),
}
FIELDS = {
    "ethics": ("approval_number", "board", "title", "approval_date", "expiry_date"),
    "funding": (
        "funder",
        "program",
        "award_number",
        "amount",
        "currency",
        "start_date",
        "end_date",
    ),
}
LIMITS = {
    "approval_number": 100,
    "board": 200,
    "title": 300,
    "funder": 200,
    "program": 300,
    "award_number": 100,
}

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MONTHS["sept"] = 9
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_YEAR_OK = range(1990, 2100)


def parse_date(text: str) -> datetime.date | None:
    """A date written in a form, or None. A day/month order that cannot be told (03/04/2025) is
    refused rather than guessed."""
    t = text.strip()
    candidates = []
    if m := re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", t):
        candidates.append((int(m[1]), int(m[2]), int(m[3])))
    elif m := re.search(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", t, re.I):
        candidates.append((int(m[3]), _MONTHS[m[1].lower()], int(m[2])))
    elif m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})\b", t, re.I):
        candidates.append((int(m[3]), _MONTHS[m[2].lower()], int(m[1])))
    elif m := re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", t):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        if a > 12 >= b:
            candidates.append((y, b, a))
        elif b > 12 >= a:
            candidates.append((y, a, b))
        elif a == b:
            candidates.append((y, a, b))
    for y, mo, d in candidates:
        try:
            date = datetime.date(y, mo, d)
        except ValueError:
            continue
        if y in _YEAR_OK:
            return date
    return None


def parse_amount(text: str) -> tuple[str | None, str | None]:
    """(amount, currency) from "$45,000.00 CAD". Either may be None."""
    currency = None
    if m := re.search(r"\b(CAD|USD|EUR|GBP|AUD|NZD|CHF)\b", text, re.I):
        currency = m[1].upper()
    elif "€" in text:
        currency = "EUR"
    elif "£" in text:
        currency = "GBP"
    m = re.search(r"(\d{1,3}(?:[,\s]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", text)
    if not m:
        return None, currency
    try:
        value = Decimal(re.sub(r"[,\s]", "", m[1]))
    except InvalidOperation:
        return None, currency
    if value <= 0 or value >= Decimal(10) ** 12:
        return None, currency
    return f"{value:.2f}", currency


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines()]


def _value(lines: list[str], i: int, rest: str) -> str:
    """What follows a label: the rest of its line, else the next line that has text."""
    rest = rest.strip()
    if rest:
        return rest
    for nxt in lines[i + 1 : i + 3]:
        if nxt:
            return nxt
    return ""


def read_text(text: str, kind: str) -> dict:
    """{"fields": {name: value}} for `kind`, from the plain text of a form. Values are strings,
    dates as YYYY-MM-DD."""
    lines = _lines(text)
    found: dict[str, str] = {}
    for name in FIELDS[kind]:
        pattern = LABELS.get(name)
        if pattern is None:
            continue
        for i, line in enumerate(lines):
            if len(line) > 400 or not (m := pattern.match(line)):
                continue
            value = _value(lines, i, m[1])
            if not value or LABELS_ANY.match(value):  # the next label, so this one was empty
                continue
            if name in ("approval_date", "expiry_date", "start_date", "end_date"):
                date = parse_date(value)
                if date:
                    found[name] = date.isoformat()
                    break
            elif name == "amount":
                amount, currency = parse_amount(value)
                if amount:
                    found["amount"] = amount
                    if currency:
                        found["currency"] = currency
                    break
            else:
                found[name] = value[: LIMITS[name]].strip(" .;,")
                break
    if kind == "ethics" and "approval_number" not in found:
        # An approval number printed on its own, e.g. "Pro00151738" or "REB19-0345".
        if m := re.search(r"\b(Pro\d{6,}|REB\s?\d{2}-\d{3,5}|H\d{2}-\d{4,6})\b", text):
            found["approval_number"] = m[1]
    if kind == "ethics" and "board" not in found:
        if m := re.search(
            r"((?:[A-Z][A-Za-z&'’-]*[ \t]+){0,5}"
            r"(?:Research Ethics Board|Institutional Review Board|"
            r"Research Ethics Committee|Ethics Review Board))",
            text,
        ):
            found["board"] = " ".join(m[1].split())[: LIMITS["board"]]
    if kind == "funding" and "currency" not in found and "amount" in found:
        found["currency"] = "CAD"  # the site's default, shown to the person to change
    return {"fields": {k: v for k, v in found.items() if v}}


# A line that is itself one of the labels: the value we were after was empty.
LABELS_ANY = re.compile("^(?:" + "|".join(_ALTS) + r")\b", re.I)


def read_form(data: bytes, filename: str, kind: str) -> dict:
    """Reads a PDF or a plain text file. Raises `pdftext.PdfTextError` or ValueError with a
    message the person can act on."""
    if kind not in KINDS:
        raise ValueError("Unknown kind of form.")
    name = (filename or "").lower()
    if name.endswith(".txt"):
        text = data[:200_000].decode("utf-8", errors="replace")
    elif name.endswith(".pdf") or data.startswith(b"%PDF"):
        text, page = "", 1
        while page and page <= MAX_PAGES:
            out = pdftext.read_pages(data, page, min(page + 5, MAX_PAGES))
            text += "\n".join(p["text"] for p in out["pages"]) + "\n"
            page = out["next_page"]
    else:
        raise ValueError("Only a PDF or a plain text file can be read for details.")
    return read_text(text, kind)
