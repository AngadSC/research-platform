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
