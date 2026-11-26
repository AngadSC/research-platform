"""Vendor exports through Benchling's allotropy, turned into our summary (child process only).

allotropy converts a vendor file into Allotrope Simple Model (ASM), a deeply nested dict whose
shape varies by technique. We don't model it: we find every "measurement document" and every data
cube in it and flatten them into plates, tables and traces.
"""

import io
import re

# our software key -> allotropy Vendor name
VENDORS = {
    "agilent_gen5": "AGILENT_GEN5",
    "moldev_softmax_pro": "MOLDEV_SOFTMAX_PRO",
    "thermo_skanit": "THERMO_SKANIT",
    "tecan_magellan": "TECAN_MAGELLAN",
    "bmg_mars": "BMG_MARS",
    "revvity_envision": "PERKIN_ELMER_ENVISION",
    "nanodrop_one": "THERMO_FISHER_NANODROP_ONE",
    "nanodrop_eight": "THERMO_FISHER_NANODROP_EIGHT",
    "nanodrop_8000": "THERMO_FISHER_NANODROP_8000",
    "qubit": "THERMO_FISHER_QUBIT4",
    "bio_rad_cfx": "CFXMAESTRO",
    "quantstudio": "APPBIO_QUANTSTUDIO",
    "quantstudio_design_analysis": "APPBIO_QUANTSTUDIO_DESIGNANDANALYSIS",
    "cytiva_unicorn": "CYTIVA_UNICORN",
    "thermo_chromeleon": "BENCHLING_CHROMELEON",
    "agilent_openlab": "AGILENT_OPENLAB_CDS",
    "agilent_tapestation": "AGILENT_TAPESTATION_ANALYSIS",
    "flowjo": "FLOWJO",
    "bd_facsdiva": "BD_BIOSCIENCES_FACSDIVA",
    "biacore_insight": "CYTIVA_BIACORE_INSIGHT",
    "biacore_t200_control": "CYTIVA_BIACORE_T200_CONTROL",
    "biacore_t200_evaluation": "CYTIVA_BIACORE_T200_EVALUATION",
}

MAX_ROWS = 1000
MAX_COLUMNS = 14
MAX_PLATES = 12
MAX_TRACES = 12
MAX_POINTS = 1500
PLATE_FORMATS = [(2, 3), (3, 4), (4, 6), (6, 8), (8, 12), (16, 24), (32, 48)]
# Quantities that describe the run rather than the result.
NOT_RESULTS = re.compile(r"temperature|volume|count|setting|number|time|length|gain", re.I)
WELL = re.compile(r"^([A-Z]{1,2})0*(\d{1,2})$")
PLACEHOLDER = {"", "n/a", "na", "none", "null"}


class Unreadable(Exception):
    user_message = ""


def extensions(key: str) -> list[str]:
    from allotropy.parser_factory import Vendor  # imported late: it takes a second and 200 MB

    return list(Vendor[VENDORS[key]].supported_extensions)


def _is_quantity(x) -> bool:
    return isinstance(x, dict) and "value" in x and set(x) <= {"value", "unit"}


def _text(x) -> str | None:
    return None if x is None or str(x).strip().lower() in PLACEHOLDER else str(x).strip()


def _walk(node):
    """Every (key, value) pair in a nested dict/list, depth first."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _first(node, name: str):
    return next((v for k, v in _walk(node) if k == name), None)


def _label(key: str) -> str:
    key = re.sub(r"\s*\(.*?\)\s*$", "", key).strip()
    if key == "cycle threshold result":
        return "Cq"
    return key[:1].upper() + key[1:]


def _well(location) -> tuple[str, int, int] | None:
    m = WELL.match(str(location or "").strip().upper())
    if not m:
        return None
    row = 0
    for ch in m.group(1):
        row = row * 26 + ord(ch) - 64
    return f"{m.group(1)}{int(m.group(2))}", row, int(m.group(2))


def _as_list(x) -> list:
    return x if isinstance(x, list) else [x] if x else []


def _settings(meas: dict) -> dict:
    docs = _as_list(
        (meas.get("device control aggregate document") or {}).get("device control document")
    )
    return docs[0] if docs else {}


def _wavelength(settings: dict) -> str | None:
    for k, v in settings.items():
        if "wavelength" in k and _is_quantity(v) and k.startswith(("detector", "excitation")):
            return f"{v['value']:g}"
    return None


def _quantities(meas: dict) -> list[tuple[str, object, str]]:
    """(label, value, unit) for each result in one measurement document."""
    wavelength = _wavelength(_settings(meas))
    sources = [meas]
    sources += _as_list(
        (meas.get("processed data aggregate document") or {}).get("processed data document")
    )
    sources.append((meas.get("sample document") or {}).get("custom information document") or {})
    out = []
    for n, source in enumerate(sources):
        for k, v in source.items():
            if _is_quantity(v) and not NOT_RESULTS.search(k) and v["value"] is not None:
                label = _label(k) + (f" {wavelength} nm" if wavelength and n == 0 else "")
                out.append((label, v["value"], v.get("unit", "")))
    return out


def _thin(xs: list, ys: list) -> tuple[list, list]:
    step = len(xs) // MAX_POINTS + 1
    return xs[::step], ys[::step]


def _axis(d: dict) -> str:
    unit = d.get("unit", "")
    unit = "" if unit in ("(unitless)", "#") else unit
    concept = _label(d.get("concept", ""))
    return f"{concept} ({unit})" if unit else concept


def _trace(cube: dict, index: int) -> dict | None:
    struct, data = cube["cube-structure"], cube["data"]
    dims, measures = struct.get("dimensions") or [], struct.get("measures") or []
    if not (dims and measures and data.get("dimensions") and data.get("measures")):
        return None
    pairs = [
        (x, y)
        for x, y in zip(data["dimensions"][0], data["measures"][0], strict=False)
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and abs(x) < 1e15
        and abs(y) < 1e15
    ]
    if not pairs:
        return None
    x, y = _thin([p[0] for p in pairs], [p[1] for p in pairs])
    return {
        "name": _text(cube.get("label")) or _axis(measures[0]) or f"Trace {index}",
        "x_label": _axis(dims[0]),
        "y_label": _axis(measures[0]),
        "x": x,
        "y": y,
    }


def _to_od(label: str, unit: str, technique: str) -> str:
    """allotropy calls plate-reader absorbance mAU; the numbers in these files are OD."""
    if unit == "(unitless)":
        return ""
    if (
        unit == "mAU"
        and technique in ("plate reader", "spectrophotometry")
        and label.lower().startswith("absorbance")
    ):
        return "OD"
    return unit


def convert(data: bytes, filename: str, key: str) -> dict:
    from allotropy.parser_factory import Vendor
    from allotropy.to_allotrope import allotrope_from_io

    asm = allotrope_from_io(io.BytesIO(data), filename, Vendor[VENDORS[key]])
    technique = next((k for k in asm if k.endswith("aggregate document")), "")
    top = asm.get(technique, {})
    technique = technique.replace(" aggregate document", "")

    is_plate = _first(top, "container type") == "well plate" or bool(
        _first(top, "plate well count")
    )
    rows: list[dict] = []
    open_rows: dict[tuple, dict] = {}  # (sample, well, plate) -> the row still taking columns
    traces: list[dict] = []
    reads: list[dict] = []  # plate reads: {"plate", "label", "unit", "wells", "rows", "cols"}
    detection: list[str] = []
    wavelengths: list[str] = []
    measurements = [m for k, v in _walk(top) if k == "measurement document" for m in _as_list(v)]
    for meas in measurements:
        sample = meas.get("sample document") or {}
        well = _well(sample.get("well location identifier") or sample.get("location identifier"))
        plate = _text(sample.get("well plate identifier")) or ""
        name = _text(sample.get("sample identifier")) or ""
        settings = _settings(meas)
        if _text(settings.get("detection type")) and settings["detection type"] not in detection:
            detection.append(settings["detection type"])
        if _wavelength(settings) and _wavelength(settings) not in wavelengths:
            wavelengths.append(_wavelength(settings))
        for _, cube in _walk(meas):
            if isinstance(cube, dict) and "cube-structure" in cube and "data" in cube:
                if t := _trace(cube, len(traces) + 1):
                    t["name"] = " ".join(p for p in (well[0] if well else name, t["name"]) if p)
                    traces.append(t)
        quantities = _quantities(meas)
        if not quantities:
            continue
        base = {"Sample": name, "Well": well[0] if well else "", "Plate": plate}
        key = tuple(base.values())
        if key not in open_rows:
            open_rows[key] = dict(base)
            rows.append(open_rows[key])
        for label, value, unit in quantities:
            unit = _to_od(label, unit, technique)
            column = f"{label} ({unit})" if unit and unit != "(unitless)" else label
            if column in open_rows[key]:  # the same well read again (kinetic): start the next row
                open_rows[key] = dict(base)
                rows.append(open_rows[key])
            open_rows[key][column] = value
        if is_plate and well:
            label, value, unit = quantities[0]
            read = next(
                (
                    r
                    for r in reads
                    if (r["plate"], r["label"]) == (plate, label) and well[0] not in r["wells"]
                ),
                None,
            )
            if read is None:
                read = {
                    "plate": plate,
                    "label": label,
                    "unit": _to_od(label, unit, technique),
                    "wells": {},
                    "rows": 0,
                    "cols": 0,
                }
                reads.append(read)
            read["wells"][well[0]] = value
            read["rows"], read["cols"] = max(read["rows"], well[1]), max(read["cols"], well[2])

    warnings: list[str] = []
    plates = []
    seen: dict[tuple, int] = {}
    for read in reads[:MAX_PLATES]:
        n = seen[(read["plate"], read["label"])] = seen.get((read["plate"], read["label"]), 0) + 1
        r, c = next(
            ((r, c) for r, c in PLATE_FORMATS if r >= read["rows"] and c >= read["cols"]),
            (0, 0),
        )
        if not r:  # bigger than a 1536-well plate: the readings table below still has every well
            warnings.append(
                "A plate in this file has more wells than we can draw, so it is shown as a table."
            )
            continue
        title = " ".join(
            p for p in (read["plate"], read["label"], f"(read {n})" if n > 1 else "") if p
        )
        plates.append(
            {"name": title, "rows": r, "cols": c, "unit": read["unit"], "wells": read["wells"]}
        )
    if len(reads) > MAX_PLATES:
        warnings.append(f"Showing the first {MAX_PLATES} of {len(reads)} plate reads.")

    tables = []
    if rows:
        used = [
            c
            for c in dict.fromkeys(c for r in rows for c in r)
            if any(r.get(c) not in ("", None) for r in rows)
        ]
        if len(used) > MAX_COLUMNS:
            warnings.append(f"Showing the first {MAX_COLUMNS} of {len(used)} columns.")
        columns = used[:MAX_COLUMNS]
        tables.append(
            {
                "name": "Readings",
                "columns": columns,
                "rows": [[r.get(c, "") for c in columns] for r in rows[:MAX_ROWS]],
                "truncated": len(rows) > MAX_ROWS,
            }
        )

    if len(traces) > MAX_TRACES:
        warnings.append(f"Showing the first {MAX_TRACES} of {len(traces)} traces.")
        traces = traces[:MAX_TRACES]
    counts: dict[str, int] = {}
    for t in traces:
        counts[t["name"]] = counts.get(t["name"], 0) + 1
        if counts[t["name"]] > 1:
            t["name"] += f" ({counts[t['name']]})"
    if not (plates or tables or traces):
        raise Unreadable("No readings were found in this file.")

    system = _first(top, "device system document") or {}
    software = _first(top, "data system document") or {}
    when = _text(_first(top, "measurement time")) or _text(_first(top, "injection time"))
    if when and when[:4] in ("1970", "1900"):
        when = None
    model = " ".join(
        p
        for p in (
            _text(system.get("product manufacturer")),
            _text(system.get("model number")) or _text(system.get("asset management identifier")),
        )
        if p
    )
    fields = [
        {"label": label, "value": value}
        for label, value in (
            ("Instrument", model),
            (
                "Software",
                " ".join(
                    p
                    for p in (
                        _text(software.get("software name")),
                        _text(software.get("software version")),
                    )
                    if p
                ),
            ),
            ("Read mode", ", ".join(detection)),
            ("Wavelengths", f"{', '.join(wavelengths)} nm" if wavelengths else ""),
            ("Operator", _text(_first(top, "analyst")) or ""),
            ("Readings", str(len(rows)) if rows else ""),
        )
        if value
    ]
    out = {
        "kind": "plate" if plates else "table" if tables else "trace",
        "title": filename.rsplit(".", 1)[0][:80] or "Instrument file",
        "measured_at": when,
        "instrument_serial": _text(system.get("equipment serial number")),
        "fields": fields,
        "warnings": warnings,
    }
    for name, value in (("plates", plates), ("tables", tables), ("traces", traces)):
        if value:
            out[name] = value
    return out
