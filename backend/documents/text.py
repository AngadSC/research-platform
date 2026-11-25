"""Plain-text extraction for search (D93)."""


def extract_text(content) -> str:
    """Plain text of BlockNote JSON: every string under a `text` key, in document order
    (covers paragraphs, links, list items, children and table cells)."""
    out: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                out.append(node["text"])
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(content)
    return " ".join(t.strip() for t in out if t.strip())


PREVIEW_CHARS = 280
PREVIEW_ROWS, PREVIEW_COLS = 6, 4


def preview_of(kind: str, content) -> dict:
    """What a document looks like at thumbnail size, for the grid view: the first lines of a
    text document, the top-left corner of a spreadsheet's first sheet, a presentation's first
    slide. Plain data only; the page draws it."""
    blocks = content if isinstance(content, list) else []
    if kind == "sheet":
        sheet = next((b for b in blocks if isinstance(b, dict) and b.get("type") == "sheet"), {})
        sheets = sheet.get("sheets") or [{}]
        cells = sheets[0].get("cells") or {} if isinstance(sheets[0], dict) else {}
        rows = [
            [
                str((cells.get(f"{chr(65 + c)}{r + 1}") or {}).get("text", ""))[:24]
                for c in range(PREVIEW_COLS)
            ]
            for r in range(PREVIEW_ROWS)
        ]
        return {"kind": "sheet", "rows": rows}
    if kind == "slides":
        slide = next((b for b in blocks if isinstance(b, dict) and b.get("type") == "slide"), {})
        title = (slide.get("title") or {}).get("text", "")
        body = (slide.get("body") or {}).get("text", "")
        return {"kind": "slides", "title": str(title)[:80], "text": str(body)[:160]}
    return {"kind": "doc", "text": extract_text(blocks)[:PREVIEW_CHARS]}
