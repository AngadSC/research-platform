import base64
import io
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
from openpyxl import Workbook

import instrument_parsers
from instrument_parsers import SOFTWARE_CHOICES, asm, dispatch, formats, parse_file

from .builders import make_abif, make_fcs, make_tiff

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
DEMOS = HERE.parent / "demo_files"


def parse_fixture(name: str, software: str = "", folder: Path = FIXTURES) -> dict:
    return parse_file((folder / name).read_bytes(), name, software)


# ---- the contract ------------------------------------------------------------------------------


def test_every_choice_has_a_parser():
    keys = [k for k, _ in SOFTWARE_CHOICES]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(asm.VENDORS) | set(dispatch.OWN)
    assert all(label for _, label in SOFTWARE_CHOICES)


def test_vendors_exist_in_allotropy():
    from allotropy.parser_factory import Vendor

    for vendor in asm.VENDORS.values():
        assert Vendor[vendor]


@pytest.mark.parametrize(
    "path",
    sorted(p for p in [*FIXTURES.iterdir(), *DEMOS.iterdir()] if p.suffix != ".md"),
    ids=lambda p: p.name,
)
def test_every_example_file_is_detected_and_small(path):
    out = parse_file(path.read_bytes(), path.name)
    assert out["status"] == "ok", out
    assert out["software"] in {k for k, _ in SOFTWARE_CHOICES}
    assert out["kind"] in {"plate", "table", "trace", "image", "sequence_trace", "flow"}
    assert len(json.dumps(out)) < 500 * 1024
    assert json.loads(json.dumps(out, allow_nan=False)) == out  # plain JSON, no NaN


# ---- vendor exports (allotropy) ----------------------------------------------------------------


def test_gen5_plate_with_two_wavelengths():
    out = parse_fixture("gen5_absorbance_two_wavelengths.txt")
    assert out["software"] == "agilent_gen5" and out["kind"] == "plate"
    names = [p["name"] for p in out["plates"]]
    assert names == ["Plate 1 Absorbance 280 nm", "Plate 1 Absorbance 325 nm"]
    plate = out["plates"][0]
    assert (plate["rows"], plate["cols"], plate["unit"]) == (8, 12, "OD")
    assert plate["wells"]["A1"] == 1.8012 and plate["wells"]["H12"] == 0.0517
    assert out["instrument_serial"] == "1234567"
    assert out["measured_at"].startswith("2025-01-02T12:30:25")
    assert {"label": "Wavelengths", "value": "280, 325 nm"} in out["fields"]
    table = out["tables"][0]  # both wavelengths side by side in one row per well
    assert table["columns"][-2:] == ["Absorbance 280 nm (OD)", "Absorbance 325 nm (OD)"]
    assert table["rows"][0][-2:] == [1.8012, 0.9066]


def test_gen5_kinetic_gives_one_trace_per_well():
    out = parse_fixture("gen5_kinetic.txt")
    assert out["kind"] == "trace" and len(out["traces"]) == 12
    assert out["traces"][0]["name"].startswith("A1")
    assert any("first 12 of 24" in w for w in out["warnings"])


def test_nanodrop_is_a_table_not_a_plate():
    out = parse_fixture("nanodrop_8000.txt")
    assert out["software"] == "nanodrop_8000" and out["kind"] == "table" and "plates" not in out
    table = out["tables"][0]
    assert "Mass concentration (mg/mL)" in table["columns"]
    assert table["rows"][0][table["columns"].index("Mass concentration (mg/mL)")] == 1.961
    assert len(table["rows"]) == 7


@pytest.mark.parametrize(
    ("name", "software"),
    [("nanodrop_eight_rna.txt", "nanodrop_eight"), ("nanodrop_one_dsdna.csv", "nanodrop_one")],
)
def test_other_nanodrops(name, software):
    out = parse_fixture(name)
    assert out["software"] == software and out["kind"] == "table"
    assert "Mass concentration (ng/µL)" in out["tables"][0]["columns"]


def test_qubit():
    out = parse_fixture("qubit4.csv")
    assert out["software"] == "qubit" and out["kind"] == "table"
    assert out["tables"][0]["rows"][0][1] == 1303.11


def test_cfx_cq_as_plate():
    out = parse_fixture("cfx_maestro_cq.csv")
    assert out["software"] == "bio_rad_cfx" and out["kind"] == "plate"
    assert out["plates"][0]["wells"]["A1"] == pytest.approx(21.18775, abs=1e-4)
    assert (out["plates"][0]["rows"], out["plates"][0]["cols"]) == (4, 6)
    assert out["measured_at"] is None  # the file has no date; 1970 is a placeholder


def test_unicorn_traces():
    out = parse_fixture("unicorn_single_uv.zip")
    assert out["software"] == "cytiva_unicorn" and out["kind"] == "trace"
    uv = out["traces"][0]
    assert uv["name"] == "UV" and uv["x_label"].startswith("Retention volume")
    assert len(uv["x"]) == len(uv["y"]) > 10


def test_demo_files_say_what_they_are():
    gen5 = parse_fixture("gen5_sialyltransferase_phosphate_assay.txt", folder=DEMOS)
    assert gen5["plates"][0]["wells"]["A1"] < gen5["plates"][0]["wells"]["H1"]
    nano = parse_fixture("nanodrop_purified_MBP_ST6GAL1.txt", folder=DEMOS)
    assert [r[0] for r in nano["tables"][0]["rows"]][:2] == ["Lysate", "Flow-through"]
    unicorn = parse_fixture("unicorn_MBP_ST6GAL1_NiNTA_run.zip", folder=DEMOS)
    uv = next(t for t in unicorn["traces"] if t["name"] == "UV")
    assert max(uv["y"]) > 800
    assert 80 < uv["x"][uv["y"].index(max(uv["y"]))] < 95  # the elution peak


def test_chosen_software_must_match_the_file():
    out = parse_fixture("qubit4.csv", software="agilent_gen5")
    assert out["status"] == "failed" and out["software"] == "agilent_gen5"
    assert out["error"].endswith(".") and "Gen5" not in out["error"]


def test_unknown_software_key_is_refused():
    assert parse_file(b"a,b\n1,2\n", "t.csv", "no_such_thing")["status"] == "failed"


# ---- our own readers ---------------------------------------------------------------------------


def test_generic_csv_and_truncation():
    text = "Sample,OD600\n" + "".join(f"S{i},{i / 10}\n" for i in range(1500))
    out = parse_file(text.encode(), "growth.csv", "generic_csv")
    table = out["tables"][0]
    assert out["kind"] == "table" and table["columns"] == ["Sample", "OD600"]
    assert len(table["rows"]) == 1000 and table["truncated"] is True
    assert table["rows"][1] == ["S1", 0.1]  # numbers come back as numbers


def test_plain_csv_is_detected_when_no_vendor_matches():
    out = parse_file(b"Strain;Colonies\nSHuffle;41\nBL21;38\n", "counts.csv")
    assert out["software"] == "generic_csv" and out["tables"][0]["rows"][0] == ["SHuffle", 41.0]


def test_xlsx_sheets():
    book = Workbook()
    book.active.title = "Yields"
    book.active.append(["Construct", "mg/L"])
    book.active.append(["MBP-ST6GAL1", 12.5])
    book.create_sheet("Notes").append(["only a note"])
    buffer = io.BytesIO()
    book.save(buffer)
    out = parse_file(buffer.getvalue(), "yields.xlsx", "generic_csv")
    assert [t["name"] for t in out["tables"]] == ["Yields", "Notes"]
    assert out["tables"][0]["rows"] == [["MBP-ST6GAL1", 12.5]]


def test_tiff_16bit_is_stretched_to_a_small_png():
    rng = np.random.default_rng(1)
    gel = rng.integers(1000, 1200, size=(1500, 3000), dtype=np.uint16)
    gel[700:720, 500:900] = 9000  # a faint band on a dark gel: auto-contrast must show it
    out = parse_file(make_tiff(gel, software="Imager 1.0"), "gel.tif")
    assert out["software"] == "image_tiff" and out["kind"] == "image"
    assert (out["image"]["width"], out["image"]["height"], out["image"]["bit_depth"]) == (
        3000,
        1500,
        16,
    )
    from PIL import Image

    png = Image.open(io.BytesIO(base64.b64decode(out["image"]["png_base64"])))
    assert max(png.size) <= 1024 and png.mode == "L"
    pixels = np.asarray(png)
    assert pixels.max() == 255 and np.median(pixels) < 10  # the band is white on near-black
    assert {"label": "Made by", "value": "Imager 1.0"} in out["fields"]


def test_tiff_rgb_and_multipage():
    rgb = np.zeros((40, 60, 3), dtype=np.uint8)
    rgb[..., 0] = 200
    out = parse_file(make_tiff(rgb), "photo.tiff")
    assert out["image"]["bit_depth"] == 8 and out["image"]["width"] == 60
    stack = np.zeros((3, 30, 30), dtype=np.uint16)
    out = parse_file(make_tiff(stack, photometric="minisblack"), "stack.tif")
    assert any("3 images" in w for w in out["warnings"])


def test_fcs_events_and_histogram():
    rng = np.random.default_rng(2)
    events = np.column_stack(
        [rng.uniform(0, 250000, 500), rng.uniform(0, 100000, 500), rng.normal(5000, 800, 500)]
    )
    data = make_fcs(
        events,
        ["FSC-A", "SSC-A", "FITC-A"],
        ["", "", "GFP"],
        {"$DATE": "24-NOV-2026", "$CYT": "Demo cytometer"},
    )
    out = parse_file(data, "sample.fcs")
    assert out["software"] == "fcs" and out["kind"] == "flow"
    assert {"label": "Events", "value": "500"} in out["fields"]
    assert out["measured_at"] == "2026-11-24"
    trace = out["traces"][0]
    assert trace["name"] == "FITC-A GFP" and len(trace["y"]) == 128 and sum(trace["y"]) == 500
    assert [r[0] for r in out["tables"][0]["rows"]] == ["FSC-A", "SSC-A", "FITC-A"]
    assert parse_file(data[:-100], "cut.fcs")["status"] == "failed"


def test_abif_bases_quality_and_traces():
    bases = "ACGTACGTAC"
    traces = {b: [i * 3 % 100 for i in range(4000)] for b in "GATC"}
    out = parse_file(make_abif(bases, [60] * 8 + [10, 10], traces, "Clone 7"), "clone7.ab1")
    assert out["software"] == "abi_sanger" and out["kind"] == "sequence_trace"
    assert out["title"] == "Clone 7"
    fields = {f["label"]: f["value"] for f in out["fields"]}
    assert fields["Bases called"] == "10" and fields["Sequence"] == bases
    assert fields["Bases at Q20 or better"] == "80%"
    assert [t["name"] for t in out["traces"]] == ["G", "A", "T", "C"]
    assert all(len(t["x"]) == len(t["y"]) <= 1500 for t in out["traces"])


# ---- hostile and broken input ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "name", "software"),
    [
        (b"", "empty.csv", ""),
        (b"\x00\x01\x02garbage" * 50, "mystery.bin", ""),
        (b"\x00\x01\x02garbage" * 50, "data.csv", ""),
        (b"\x00\x01\x02garbage" * 50, "data.csv", "agilent_gen5"),
        (b"ABIF" + b"\xff" * 60, "bad.ab1", ""),
        (b"FCS3.1    " + b"9" * 48, "bad.fcs", ""),
        (b"II*\x00" + b"\xff" * 40, "bad.tif", ""),
        (b"PK\x03\x04" + b"\x00" * 30, "bad.xlsx", ""),
        (b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>", "x.xml", "bd_facsdiva"),
    ],
)
def test_garbage_never_raises(data, name, software):
    out = parse_file(data, name, software)
    assert out["status"] in ("failed", "unsupported")
    assert out["error"].endswith(".")
    assert "Traceback" not in out["error"] and "Error" not in out["error"]


def test_too_large_and_too_slow(monkeypatch):
    monkeypatch.setattr(instrument_parsers, "MAX_BYTES", 10)
    assert "too large" in parse_file(b"a,b\n1,2\n3,4\n", "big.csv")["error"]
    monkeypatch.setattr(instrument_parsers, "MAX_BYTES", 50 * 1024 * 1024)
    monkeypatch.setattr(instrument_parsers, "TIMEOUT", 0.01)
    assert "too long" in parse_file(b"a,b\n1,2\n", "slow.csv")["error"]


def test_huge_image_is_refused_before_it_is_decoded():
    big = make_tiff(np.zeros((12000, 12000), dtype=np.uint8), compression="zlib")
    out = parse_file(big, "huge.tif")
    assert out["status"] == "failed" and "too large" in out["error"]


def test_child_works_in_a_scratch_directory_and_cannot_write_outside(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    parse_file(b"a,b\n1,2\n", "t.csv")
    assert list(tmp_path.iterdir()) == []


def test_image_that_decodes_to_too_many_bytes_is_refused_before_it_is_decoded(monkeypatch):
    # 11000 x 9000 float64 zeros is a 750 KB zlib file that decodes to 790 MB and passes MAX_PIXELS
    monkeypatch.setattr(formats, "MAX_DECODED", 1024**2)
    data = make_tiff(np.zeros((1000, 1000), dtype=np.float64), compression="zlib")
    with pytest.raises(formats.Unreadable, match="too large"):
        formats.tiff_image(data, "big.tif")
    monkeypatch.setattr(formats, "MAX_DECODED", 300 * 1024**2)
    assert formats.tiff_image(data, "big.tif")["kind"] == "image"


def test_long_digit_cell_is_not_scanned_slowly():
    data = b"a,b\n" + b"1" * 100_000 + b"x,2\n"
    started = time.monotonic()
    out = formats.generic_table(data, "t.csv")
    assert time.monotonic() - started < 1
    assert out["tables"][0]["rows"][0][1] == 2.0
    assert formats._number(" -1.5e3 ") == -1500.0 and formats._number("1.") == 1.0
    assert formats._number(".5") == 0.5 and formats._number("1e") == "1e"


def test_scratch_directory_is_removed_even_when_the_child_is_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(instrument_parsers, "TIMEOUT", 0.01)
    assert "too long" in parse_file(b"a,b\n1,2\n", "slow.csv")["error"]
    assert list(tmp_path.iterdir()) == []


def test_child_output_is_read_only_up_to_the_limit(monkeypatch):
    monkeypatch.setattr(instrument_parsers, "MAX_SUMMARY", 0)
    rows = b"".join(b"%d,%d,%d,%d\n" % (i, i, i, i) for i in range(2000))
    out = parse_file(b"a,b,c,d\n" + rows, "big.csv")
    assert out["status"] == "failed" and "too large" in out["error"]


def test_plate_bigger_than_1536_wells_becomes_a_table(monkeypatch):
    path = FIXTURES / "gen5_absorbance_two_wavelengths.txt"
    assert asm.convert(path.read_bytes(), path.name, "agilent_gen5")["plates"]
    monkeypatch.setattr(asm, "PLATE_FORMATS", [(2, 3)])
    out = asm.convert(path.read_bytes(), path.name, "agilent_gen5")
    assert "plates" not in out and out["tables"]
    assert any("table" in w for w in out["warnings"])


def test_unreadable_file_without_a_chosen_software_does_not_blame_the_choice():
    out = parse_file(b"II*\x00" + b"\xff" * 40, "bad.tif")
    assert out["status"] == "failed" and "software you chose" not in out["error"]
