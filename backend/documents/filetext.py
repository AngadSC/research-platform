"""Plain text of a project file, for the AI tool read_file (VISION A4).

Word (.docx) and Excel (.xlsx) files are zip archives of XML, read here with the standard library
only: the archive's declared sizes are checked before anything is unpacked (zipfile never returns
more than a member declares), and the XML is streamed with iterparse, so a large sheet never sits
in memory. Expat does not fetch external entities and limits entity expansion. PDFs are not read
here: papers.pdftext reads them in a sandboxed child process.
"""

import csv
import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile

from papers.pdftext import _clean as clean

MAX_UNPACKED = 50 * 1024 * 1024  # bytes of XML in one Word or Excel file
MAX_COLS = 16384  # Excel's own limit (column XFD)
MAX_TEXT = 2_000_000  # characters of text kept from one file
CUT = "\n(The rest of this file is too long to read here.)"
KINDS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "text",
    ".txt": "text",
    ".md": "text",
    ".json": "text",
}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class FileTextError(Exception):
    """A message the model can pass on."""


def kind(filename: str) -> str | None:
    """ "pdf", "docx", "xlsx", "text", or None for a type that cannot be read as text."""
    return KINDS.get(os.path.splitext(filename.lower())[1])


def text_of(data: bytes, file_kind: str) -> str:
    """The whole text of a "text", "docx" or "xlsx" file. Raises FileTextError."""
    if file_kind == "text":
        return _cap(clean(data.decode("utf-8-sig", errors="replace")))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
                raise FileTextError("This file is too large to read as text.")
            return clean(_docx(z) if file_kind == "docx" else _xlsx(z))
    except (zipfile.BadZipFile, KeyError, ValueError, ET.ParseError, EOFError):
        raise FileTextError("The text of this file could not be read; it may be damaged.") from None


def _cap(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + CUT


def _iter(z, name, tag):
    """Each `tag` element of one XML member, freed once used. Every other element is freed as
    soon as it ends, so a file of millions of empty elements never builds a big tree."""
    stack, inside = [], 0
    with z.open(name) as fh:
        for event, el in ET.iterparse(fh, events=("start", "end")):
            if event == "start":
                stack.append(el)
                inside += el.tag == tag
                continue
            stack.pop()
            if el.tag == tag:
                yield el
                inside -= 1
                el.clear()
            if inside:
                continue  # part of a matched element; freed with it
            el.clear()
            if stack:
                stack[-1].remove(el)


def _docx(z) -> str:
    out, size = [], 0
    for p in _iter(z, "word/document.xml", W + "p"):
        line = "".join(
            (el.text or "") if el.tag == W + "t" else "\t"
            for el in p.iter()
            if el.tag in (W + "t", W + "tab")
        )
        out.append(line)
        size += len(line) + 1
        if size > MAX_TEXT:
            return "\n".join(out)[:MAX_TEXT] + CUT
    return "\n".join(out)


def _col(ref: str) -> int | None:
    """0-based column of a cell reference like "AB12"."""
    m = re.match(r"[A-Z]+", ref or "")
    if not m:
        return None
    n = 0
    for c in m.group():
        n = n * 26 + ord(c) - 64
    return n - 1 if n <= MAX_COLS else None


def _cell(c, shared) -> str:
    t = c.get("t")
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(S + "t"))
    v = c.find(S + "v")
    v = (v.text or "") if v is not None else ""
    if t == "s":
        return shared[int(v)] if v.isdigit() and int(v) < len(shared) else ""
    if t == "b":
        return "TRUE" if v == "1" else "FALSE"
    return v  # numbers (dates are Excel serial numbers), formula results, errors


def _xlsx(z) -> str:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = [
            "".join(t.text or "" for t in si.iter(S + "t"))
            for si in _iter(z, "xl/sharedStrings.xml", S + "si")
        ]
    rels = {
        r.get("Id"): r.get("Target", "")
        for r in _iter(
            z,
            "xl/_rels/workbook.xml.rels",
            "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        )
    }
    sheets = [(s.get("name"), s.get(R + "id")) for s in _iter(z, "xl/workbook.xml", S + "sheet")]
    out = io.StringIO()
    rows = csv.writer(out, lineterminator="\n")
    for name, rid in sheets:
        target = rels.get(rid, "")
        out.write(f"# Sheet: {name}\n")
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        for row in _iter(z, path, S + "row"):
            cells = {}
            for c in row.iter(S + "c"):
                col = _col(c.get("r"))
                cells[col if col is not None else len(cells)] = _cell(c, shared)
                if len(cells) > MAX_COLS:
                    raise ValueError("too many columns")
            if cells:
                rows.writerow([cells.get(i, "") for i in range(max(cells) + 1)])
            if out.tell() > MAX_TEXT:
                return out.getvalue()[:MAX_TEXT] + CUT
        out.write("\n")
    return out.getvalue()
