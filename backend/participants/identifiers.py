"""The participant registry takes coded IDs and non-identifying attributes only.

Nothing here can prove a value is not a name, so the checks are deliberately blunt: a code must
contain a digit (a plain word is refused), and free text may not hold an email address, a phone
number or a full date (a likely birthdate). A refusal never repeats the value it refused.
"""

import re

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
PHONE_RE = re.compile(r"(?<![\d])\+?\d[\d\s().-]{6,}\d(?![\d])")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RES = (
    re.compile(r"(?<!\d)\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)"),
    re.compile(r"(?<!\d)\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}(?!\d)"),
    re.compile(rf"(?<!\d)\d{{1,2}}\s+{_MONTH},?\s+\d{{4}}", re.I),
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}", re.I),
)


def _digits(text: str) -> int:
    return sum(c.isdigit() for c in text)


def identifier_problem(text: str) -> str | None:
    """What kind of direct identifier `text` looks like, or None. Never returns the value."""
    if EMAIL_RE.search(text):
        return "an email address"
    for m in PHONE_RE.finditer(text):
        if _digits(m.group()) >= 7:
            return "a phone number"
    if any(r.search(text) for r in DATE_RES):
        return "a full date (it could be a birthdate)"
    return None


def free_text_problem(text: str) -> str | None:
    return identifier_problem(text or "")


def code_problem(code: str) -> str | None:
    """Why `code` cannot be a participant code, or None when it can."""
    if not CODE_RE.match(code):
        return "Use letters, digits, dots, dashes or underscores only, with no spaces (up to 40)."
    if not any(c.isdigit() for c in code):
        return "A code needs a number in it, like P-017. A plain word could be a name."
    kind = identifier_problem(code)
    if kind:
        return f"This looks like {kind}. Use a coded ID such as P-017."
    return None
