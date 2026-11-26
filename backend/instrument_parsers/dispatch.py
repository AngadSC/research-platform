"""Choose a parser, run it, and make the result safe to store (child process only)."""

import json
import math
import os

from . import asm, formats

MAX_SUMMARY = 500 * 1024

# Our own readers; every other key in SOFTWARE_CHOICES is an allotropy vendor (see asm.VENDORS).
OWN = {
    "generic_csv": formats.generic_table,
    "image_tiff": formats.tiff_image,
    "fcs": formats.fcs_events,
    "abi_sanger": formats.abif_trace,
}
MAGIC = ("abi_sanger", "fcs", "image_tiff")  # formats we recognise by their first bytes
UNSUPPORTED = (
    "We can't preview this kind of file yet. You can still keep it with your records and "
    "download it."
)


def _sniff(data: bytes, ext: str) -> list[str]:
    """Candidate software keys for an unlabelled file, most specific first."""
    head = data[:512]
    if head[:4] == b"ABIF" or head[128:132] == b"ABIF":
        return ["abi_sanger"]
    if head[:3] == b"FCS":
        return ["fcs"]
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return ["image_tiff"]
    # Vendor exports first (they would also pass as a plain table), then the plain table.
    candidates = [k for k in asm.VENDORS if ext in asm.extensions(k)]
    if ext in ("csv", "tsv", "txt", "xlsx"):
        candidates.append("generic_csv")
    return candidates


def _clean(x):
    """Plain JSON types only: NaN and infinity become null, numpy numbers become Python ones."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _fit(summary: dict) -> dict:
    """Shrink tables and traces until the summary fits the size limit."""
    for _ in range(8):
        if len(json.dumps(summary, allow_nan=False)) <= MAX_SUMMARY:
            return summary
        for table in summary.get("tables", []):
            cut = max(len(table["rows"]) // 2, 1)
            table["truncated"] = table["truncated"] or cut < len(table["rows"])
            table["rows"] = table["rows"][:cut]
        for trace in summary.get("traces", []):
            trace["x"], trace["y"] = trace["x"][::2], trace["y"][::2]
        summary["plates"] = summary.get("plates", [])[:6]
    return {
        "status": "failed",
        "software": summary.get("software", ""),
        "error": "This file is too large to preview.",
    }


def run(data: bytes, filename: str, software: str) -> dict:
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    candidates = [software] if software else _sniff(data, ext)
    last_error = ""
    for key in candidates:
        try:
            summary = (OWN[key] if key in OWN else lambda d, f, k=key: asm.convert(d, f, k))(
                data, filename
            )
        except Exception as exc:  # noqa: BLE001 (a wrong guess or a bad file; try the next)
            last_error = getattr(exc, "user_message", "") or ""
            continue
        summary = _clean({"status": "ok", "software": key, **summary})
        return _fit(summary)
    if software or (len(candidates) == 1 and candidates[0] in MAGIC):
        return {
            "status": "failed",
            "software": software or candidates[0],
            "error": last_error
            or (
                "This file doesn't look like an export from the software you chose, or it comes "
                "from a version we can't read."
                if software
                else "This file could not be read; it may be damaged."
            ),
        }
    return {"status": "unsupported", "software": "", "error": UNSUPPORTED}
