"""Readers for formats allotropy doesn't cover (child process only): tables, TIFF images, FCS flow
files and ABI sequencing traces. Each takes (data, filename) and returns the summary without
"status" and "software". Everything read from the file is bounds-checked and capped."""

import base64
import csv
import io
import re
import struct
import zipfile

MAX_ROWS = 1000
MAX_COLUMNS = 40
MAX_SHEETS = 5
MAX_POINTS = 1500
MAX_PIXELS = 100_000_000
MAX_XLSX_UNPACKED = 200 * 1024 * 1024
PNG_SIZES = (1024, 800, 640, 512, 384)
PNG_BUDGET = 350_000  # base64 characters, so the whole summary stays well under 500 KB


class Unreadable(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.user_message = message


def _number(cell):
    if isinstance(cell, str):
        text = cell.strip()
        try:
            return (
                float(text)
                if re.fullmatch(r"[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", text)
                else text
            )
        except ValueError:
            return text
    return cell


def _table(name: str, grid: list[list]) -> dict:
    grid = [r for r in grid if any(c not in ("", None) for c in r)]
    if not grid:
        raise Unreadable("This file has no table in it.")
    width = min(max(len(r) for r in grid), MAX_COLUMNS)
    head = [
        str(c) if c not in (None, "") else f"Column {i + 1}" for i, c in enumerate(grid[0][:width])
    ]
    head += [f"Column {i + 1}" for i in range(len(head), width)]
    body = [
        [_number(c) if c is not None else "" for c in (r + [""] * width)[:width]]
        for r in grid[1 : MAX_ROWS + 1]
    ]
    return {"name": name, "columns": head, "rows": body, "truncated": len(grid) - 1 > MAX_ROWS}


def generic_table(data: bytes, filename: str) -> dict:
    """CSV, TSV, tab-separated text or XLSX as plain tables."""
    stem = filename.rsplit(".", 1)[0][:80] or "Table"
    warnings = []
    if data[:2] == b"PK":
        from openpyxl import load_workbook

        with zipfile.ZipFile(io.BytesIO(data)) as z:  # a zip bomb is the usual hostile xlsx
            if sum(i.file_size for i in z.infolist()) > MAX_XLSX_UNPACKED:
                raise Unreadable("This spreadsheet is too large to preview.")
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        tables = []
        for sheet in book.worksheets[:MAX_SHEETS]:
            rows = []
            for row in sheet.iter_rows(values_only=True, max_row=MAX_ROWS + 50):
                rows.append(list(row))
            if any(any(c not in ("", None) for c in r) for r in rows):
                tables.append(_table(sheet.title, rows))
        if len(book.worksheets) > MAX_SHEETS:
            warnings.append(f"Showing the first {MAX_SHEETS} of {len(book.worksheets)} sheets.")
        if not tables:
            raise Unreadable("This spreadsheet is empty.")
    else:
        if b"\x00" in data[:4096]:
            raise Unreadable("This looks like a binary file, not a table.")
        text = data.decode("utf-8-sig") if _is_utf8(data) else data.decode("latin-1")
        sample = "\n".join(text.splitlines()[:20])
        delimiter = max(",\t;|", key=sample.count)
        if sample.count(delimiter) == 0:
            raise Unreadable("This text file doesn't look like a table.")
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        tables = [
            _table("Table", [row for _, row in zip(range(MAX_ROWS + 50), reader, strict=False)])
        ]
    return {"kind": "table", "title": stem, "fields": [], "tables": tables, "warnings": warnings}


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8-sig")
        return True
    except UnicodeDecodeError:
        return False


# ---- TIFF -------------------------------------------------------------------------------------


def tiff_image(data: bytes, filename: str) -> dict:
    """First image of a TIFF or OME-TIFF as an auto-contrast 8-bit PNG thumbnail."""
    import numpy as np
    import tifffile
    from PIL import Image

    with tifffile.TiffFile(io.BytesIO(data)) as tif:
        page = tif.pages[0]
        if page.imagelength * page.imagewidth > MAX_PIXELS:
            raise Unreadable("This image is too large to preview.")
        arr = np.squeeze(page.asarray())
        pages, ome = len(tif.pages), tif.is_ome
        photometric = page.photometric.name
        description = (page.tags["Software"].value if "Software" in page.tags else "") or ""
        stamp = page.tags["DateTime"].value if "DateTime" in page.tags else None
    if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
        arr = np.moveaxis(arr, 0, -1)  # planar RGB
    if arr.ndim == 3 and arr.shape[-1] not in (3, 4):
        arr = arr[0]
    if arr.ndim not in (2, 3) or arr.size == 0:
        raise Unreadable("This TIFF doesn't hold an ordinary image.")
    height, width = arr.shape[:2]
    bits = arr.dtype.itemsize * 8
    step = max(height, width) // 2048 + 1
    small = arr[::step, ::step, :3] if arr.ndim == 3 else arr[::step, ::step]
    values = small.astype(np.float32)
    if arr.dtype == np.uint8 and arr.ndim == 3:
        lo, hi = 0.0, 255.0
    else:
        lo, hi = (
            (float(v) for v in np.percentile(values[np.isfinite(values)], (0.5, 99.9)))
            if np.isfinite(values).any()
            else (0.0, 1.0)
        )
        if hi <= lo:
            lo, hi = float(np.nanmin(values)), float(np.nanmax(values))
        if hi <= lo:
            hi = lo + 1.0
    scaled = np.clip((np.nan_to_num(values) - lo) / (hi - lo), 0, 1)
    if photometric == "MINISWHITE":
        scaled = 1 - scaled
    image = Image.fromarray((scaled * 255).astype(np.uint8))
    encoded = ""
    for size in PNG_SIZES:
        thumb = image.copy()
        thumb.thumbnail((size, size))
        buffer = io.BytesIO()
        thumb.save(buffer, "PNG", optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode()
        if len(encoded) <= PNG_BUDGET:
            break
    fields = [
        {"label": "Size", "value": f"{width} x {height} pixels"},
        {"label": "Bit depth", "value": f"{bits}-bit" + (" colour" if arr.ndim == 3 else " grey")},
        {"label": "Format", "value": "OME-TIFF" if ome else "TIFF"},
    ]
    if pages > 1:
        fields.append({"label": "Images in file", "value": str(pages)})
    if description:
        fields.append({"label": "Made by", "value": str(description)[:120]})
    return {
        "kind": "image",
        "title": filename.rsplit(".", 1)[0][:80] or "Image",
        "measured_at": _tiff_date(stamp),
        "fields": fields,
        "image": {"png_base64": encoded, "width": width, "height": height, "bit_depth": bits},
        "warnings": (
            [f"This file has {pages} images. The first one is shown."] if pages > 1 else []
        )
        + ["The preview is stretched to show faint bands. The original file is unchanged."],
    }


def _tiff_date(stamp) -> str | None:
    m = re.fullmatch(r"(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)", str(stamp or "").strip())
    return f"{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}:{m[6]}" if m else None


# ---- FCS --------------------------------------------------------------------------------------


def _fcs_text(data: bytes) -> tuple[dict, int, int]:
    if data[:3] != b"FCS" or data[3:6] not in (b"2.0", b"3.0", b"3.1"):
        raise Unreadable("This isn't an FCS 2.0, 3.0 or 3.1 file.")
    start, end, dstart, dend = (int(data[i : i + 8].strip() or 0) for i in (10, 18, 26, 34))
    segment = data[start : end + 1]
    if len(segment) < 2:
        raise Unreadable("This FCS file has no header information.")
    delim = segment[:1]
    parts = (
        segment[1:].replace(delim * 2, b"\x00").split(delim)
    )  # a doubled delimiter is an escaped one
    keys = {}
    for k, v in zip(parts[0::2], parts[1::2], strict=False):
        keys[k.decode("latin-1").strip().upper()] = (
            v.replace(b"\x00", delim).decode("latin-1").strip()
        )
    dstart = dstart or int(keys.get("$BEGINDATA", 0))
    dend = dend or int(keys.get("$ENDDATA", 0))
    return keys, dstart, dend


def fcs_events(data: bytes, filename: str) -> dict:
    """Header, parameters, event count and one histogram of a flow cytometry FCS file."""
    import numpy as np

    keys, dstart, dend = _fcs_text(data)
    try:
        total, count = int(keys["$TOT"]), int(keys["$PAR"])
    except (KeyError, ValueError):
        raise Unreadable("This FCS file is missing its event or parameter count.") from None
    if not 0 < count <= 256 or total < 0:
        raise Unreadable("This FCS file has an unexpected number of parameters.")
    kind = keys.get("$DATATYPE", "F").upper()
    little = keys.get("$BYTEORD", "1,2,3,4").startswith("1")
    bits = {i: int(keys.get(f"$P{i}B", 0) or 0) for i in range(1, count + 1)}
    width = {"F": 32, "D": 64}.get(kind) or bits[1]
    if (
        kind == "A"
        or keys.get("$MODE", "L") != "L"
        or width not in (8, 16, 32, 64)
        or any(b != width for b in bits.values() if kind == "I")
    ):
        raise Unreadable(
            "This kind of FCS data (list mode with fixed-size numbers only) isn't supported yet."
        )
    dtype = np.dtype({"F": "f", "D": "f"}.get(kind, "u") + str(width // 8)).newbyteorder(
        "<" if little else ">"
    )
    need = total * count * dtype.itemsize
    chunk = data[dstart : dstart + need]
    if len(chunk) < need:
        raise Unreadable("This FCS file is cut short: some events are missing.")
    events = np.frombuffer(chunk, dtype=dtype).reshape(total, count).astype(np.float64)
    if kind == "I":
        for i in range(1, count + 1):
            rng = int(float(keys.get(f"$P{i}R", 0) or 0))
            if rng > 1 and rng & (rng - 1) == 0:
                events[:, i - 1] = np.bitwise_and(events[:, i - 1].astype(np.uint64), rng - 1)

    names = [keys.get(f"$P{i}N", f"P{i}") for i in range(1, count + 1)]
    labels = [keys.get(f"$P{i}S", "") for i in range(1, count + 1)]
    # histogram of the first fluorescence channel, else the first channel
    pick = next((i for i, n in enumerate(names) if not re.match(r"(?i)(time|fsc|ssc|event)", n)), 0)
    trace = None
    if total:
        column = events[:, pick]
        lo, hi = float(column.min()), float(column.max())
        counts, edges = np.histogram(column, bins=128, range=(lo, hi if hi > lo else lo + 1))
        trace = {
            "name": f"{names[pick]} {labels[pick]}".strip(),
            "x_label": names[pick],
            "y_label": "Events",
            "x": [float(v) for v in (edges[:-1] + edges[1:]) / 2],
            "y": [int(v) for v in counts],
        }
    rows = []
    for i in range(count):
        col = events[:, i] if total else np.zeros(1)
        rows.append(
            [names[i], labels[i], float(np.median(col)), float(col.min()), float(col.max())]
        )
    fields = [
        {"label": "Events", "value": f"{total:,}"},
        {"label": "Parameters", "value": str(count)},
    ]
    for label, key in (
        ("Cytometer", "$CYT"),
        ("Cytometer serial", "$CYTSN"),
        ("File", "$FIL"),
        ("Sample source", "$SRC"),
        ("Date", "$DATE"),
        ("Start time", "$BTIM"),
    ):
        if keys.get(key):
            fields.append({"label": label, "value": keys[key]})
    date = keys.get("$DATE", "")
    when = None
    if m := re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", date):
        month = "JanFebMarAprMayJunJulAugSepOctNovDec".find(m[2].title())
        if month >= 0:
            when = f"{m[3]}-{month // 3 + 1:02d}-{int(m[1]):02d}"
    out = {
        "kind": "flow",
        "title": (keys.get("$FIL") or filename.rsplit(".", 1)[0])[:80],
        "measured_at": when,
        "instrument_serial": keys.get("$CYTSN") or None,
        "fields": fields,
        "tables": [
            {
                "name": "Parameters",
                "columns": ["Channel", "Label", "Median", "Lowest", "Highest"],
                "rows": rows,
                "truncated": False,
            }
        ],
        "warnings": [
            "Event values are shown as stored in the file, before any compensation or scaling."
        ],
    }
    if trace:
        out["traces"] = [trace]
    return out


# ---- ABIF (.ab1 Sanger sequencing, .fsa fragment analysis) -------------------------------------

ABIF_NUMBERS = {
    1: ("B", 1),
    4: ("h", 2),
    5: ("i", 4),
    7: ("f", 4),
    8: ("d", 8),
}  # element type -> (struct code, bytes)


def _abif_entries(data: bytes) -> tuple[dict, bytes]:
    if data[:4] != b"ABIF":
        if data[128:132] != b"ABIF":
            raise Unreadable("This isn't an ABI trace file.")
        data = data[128:]
    count, _, offset = struct.unpack(">iii", data[18:30])
    if not 0 < count <= 5000 or offset <= 0 or offset + count * 28 > len(data):
        raise Unreadable("This ABI trace file's index is damaged.")
    entries = {}
    for n in range(count):
        name, number, etype, esize, num, size, pos = struct.unpack(
            ">4siHhiii", data[offset + n * 28 : offset + n * 28 + 24]
        )
        raw = (
            data[offset + n * 28 + 20 : offset + n * 28 + 24]
            if size <= 4
            else data[pos : pos + size]
        )
        entries[(name.decode("latin-1"), number)] = (etype, num, raw[:size])
    return entries, data


def _abif_value(entries: dict, name: str, number: int = 1):
    got = entries.get((name, number))
    if not got:
        return None
    etype, num, raw = got
    if etype == 18 and raw:
        return raw[1 : 1 + raw[0]].decode("latin-1")
    if etype in (2, 19):
        return raw.decode("latin-1", "replace").strip("\x00")
    if etype not in ABIF_NUMBERS:
        return None
    code, size = ABIF_NUMBERS[etype]
    return list(struct.unpack(f">{len(raw) // size}{code}", raw[: len(raw) // size * size]))


def abif_trace(data: bytes, filename: str) -> dict:
    """Bases, quality summary and the four channel traces of an ABI .ab1 / .fsa file."""
    entries, data = _abif_entries(data)
    bases = _abif_value(entries, "PBAS", 2) or _abif_value(entries, "PBAS", 1) or ""
    quality = _abif_value(entries, "PCON", 2) or _abif_value(entries, "PCON", 1) or []
    order = _abif_value(entries, "FWO_", 1) or "GATC"
    channels = [(i, _abif_value(entries, "DATA", i)) for i in (9, 10, 11, 12)]
    channels = [(i, v) for i, v in channels if v]
    names = list(order) if len(order) == len(channels) else [f"Channel {i}" for i, _ in channels]
    if not channels:  # fragment analysis files keep raw data in DATA 1-5
        channels = [(i, _abif_value(entries, "DATA", i)) for i in range(1, 6)]
        channels = [(i, v) for i, v in channels if v]
        names = [f"Dye {i}" for i, _ in channels]
    if not channels and not bases:
        raise Unreadable("No sequence or trace data was found in this file.")

    traces = []
    for name, (_, values) in zip(names, channels, strict=False):
        step = len(values) // MAX_POINTS + 1  # peak of each bin, so thin peaks survive
        y = [max(values[i : i + step]) for i in range(0, len(values), step)]
        traces.append(
            {
                "name": name,
                "x_label": "Scan",
                "y_label": "Signal",
                "x": list(range(0, len(values), step))[: len(y)],
                "y": y,
            }
        )

    fields = []
    sample = _abif_value(entries, "SMPL", 1)
    for label, value in (
        ("Sample", sample),
        ("Instrument", _abif_value(entries, "MODL", 1) or _abif_value(entries, "MCHN", 1)),
        ("Run", _abif_value(entries, "RUNN", 1)),
    ):
        if value:
            fields.append({"label": label, "value": str(value)})
    if bases:
        q20 = sum(1 for q in quality if q >= 20)
        fields.append({"label": "Bases called", "value": f"{len(bases):,}"})
        if quality:
            fields.append(
                {"label": "Average quality", "value": f"Q{sum(quality) / len(quality):.0f}"}
            )
            fields.append({"label": "Bases at Q20 or better", "value": f"{q20 / len(quality):.0%}"})
        fields.append(
            {"label": "Sequence", "value": bases[:120] + ("..." if len(bases) > 120 else "")}
        )
    return {
        "kind": "sequence_trace",
        "title": (sample or filename.rsplit(".", 1)[0])[:80],
        "fields": fields,
        "traces": traces,
        "warnings": [] if bases else ["This file has trace data but no base calls."],
    }
