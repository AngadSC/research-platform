"""Readable previews of exported instrument files (plate readers, NanoDrop, qPCR, FPLC, gels, ...).

`parse_file` is the only entry point and never raises. The files are hostile input and the parsers
are big (pandas, openpyxl, allotropy), so all parsing runs in a short-lived child process with CPU,
memory and file-size limits, as in papers/pdftext.py. This module imports only the standard library.
Call `parse_file` only from the Celery worker, never from a web request: the machine-wide limit on
parsing at once is the worker's concurrency (each worker process runs up to _SLOTS children).
Keys here must match the ones in dispatch.py (a test checks it).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

# (key, label) in the order the UI shows them. The first four groups use Benchling's allotropy.
SOFTWARE_CHOICES: list[tuple[str, str]] = [
    ("agilent_gen5", "Agilent BioTek Gen5 (plate reader)"),
    ("moldev_softmax_pro", "Molecular Devices SoftMax Pro (plate reader)"),
    ("thermo_skanit", "Thermo Scientific SkanIt (plate reader)"),
    ("tecan_magellan", "Tecan Magellan (plate reader)"),
    ("bmg_mars", "BMG LABTECH MARS (plate reader)"),
    ("revvity_envision", "Revvity EnVision (plate reader)"),
    ("nanodrop_one", "Thermo NanoDrop One"),
    ("nanodrop_eight", "Thermo NanoDrop Eight"),
    ("nanodrop_8000", "Thermo NanoDrop 8000"),
    ("qubit", "Thermo Qubit 4"),
    ("bio_rad_cfx", "Bio-Rad CFX Maestro (qPCR)"),
    ("quantstudio", "Applied Biosystems QuantStudio (qPCR)"),
    ("quantstudio_design_analysis", "QuantStudio Design & Analysis (qPCR)"),
    ("cytiva_unicorn", "Cytiva UNICORN (AKTA chromatography)"),
    ("thermo_chromeleon", "Thermo Chromeleon (HPLC, JSON export)"),
    ("agilent_openlab", "Agilent OpenLab CDS (HPLC)"),
    ("agilent_tapestation", "Agilent TapeStation"),
    ("flowjo", "FlowJo workspace"),
    ("bd_facsdiva", "BD FACSDiva (XML export)"),
    ("biacore_insight", "Cytiva Biacore Insight"),
    ("biacore_t200_control", "Cytiva Biacore T200 control"),
    ("biacore_t200_evaluation", "Cytiva Biacore T200 evaluation"),
    ("generic_csv", "Table (CSV, TSV or Excel)"),
    ("image_tiff", "Image (TIFF, gel or blot)"),
    ("fcs", "Flow cytometry events (FCS)"),
    ("abi_sanger", "DNA sequencing trace (.ab1, .fsa)"),
]

MAX_BYTES = 50 * 1024 * 1024
MAX_SUMMARY = 500 * 1024
TIMEOUT = 45  # seconds, wall clock and CPU; importing pandas and allotropy alone takes a few
MEMORY = 1024**3  # as in papers/pdftext.py; the child sets it on itself (_child.py)
_SLOTS = threading.BoundedSemaphore(3)  # concurrent children per worker process
_KEYS = {key for key, _ in SOFTWARE_CHOICES}


def _failed(message: str, software: str = "") -> dict:
    return {"status": "failed", "software": software, "error": message}


def _run_child(data: bytes, filename: str, software: str) -> tuple[bytes, bool]:
    """Run _child.py on `data`. Returns (stdout, timed_out); stdout is cut at the size limit, and
    the child is killed once it has written more than that or has run for TIMEOUT seconds. The
    scratch directory is ours, so it goes even when the child is killed."""
    scratch = tempfile.mkdtemp(prefix="instrument-")
    try:
        child = subprocess.Popen(  # noqa: S603 (our own interpreter and file; the data is stdin)
            [sys.executable, "-I", "-B", os.path.join(os.path.dirname(__file__), "_child.py")]
            + [os.path.basename(filename or "")[:200], software],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=scratch,
            env={
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "TMPDIR": scratch,
            },
        )
        timed_out = threading.Event()

        def stop() -> None:
            timed_out.set()
            child.kill()

        def feed() -> None:
            try:
                child.stdin.write(data)
                child.stdin.close()
            except OSError:  # the child died or was killed before reading it all
                pass

        timer = threading.Timer(TIMEOUT, stop)
        timer.start()
        threading.Thread(target=feed, daemon=True).start()
        try:
            stdout = child.stdout.read(MAX_SUMMARY + 10_001)
        finally:
            timer.cancel()
            child.kill()
            child.wait()
            child.stdout.close()
        return stdout, timed_out.is_set()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def parse_file(data: bytes, filename: str, software: str = "") -> dict:
    """A JSON-safe summary of an instrument export (see the contract in .night/WETLAB.md). Never
    raises. `software=""` detects the format from the name and content."""
    try:
        if software and software not in _KEYS:
            return _failed("This instrument software is not one we can read yet.")
        if len(data) > MAX_BYTES:
            return _failed("This file is too large to preview (50 MB maximum).", software)
        if not data:
            return _failed("This file is empty.", software)
        if not _SLOTS.acquire(timeout=10):
            return _failed("Too many files are being read right now. Try again in a moment.")
        try:
            stdout, timed_out = _run_child(data, filename, software)
        finally:
            _SLOTS.release()
        if timed_out:
            return _failed("Reading this file took too long, so it was stopped.", software)
        if len(stdout) > MAX_SUMMARY + 10_000:
            return _failed("This file is too large to preview.", software)
        out = json.loads(stdout)  # empty or cut off when a limit killed the child
        if not isinstance(out, dict) or out.get("status") not in ("ok", "unsupported", "failed"):
            raise ValueError
        return out
    except Exception:  # noqa: BLE001 (callers rely on this never raising)
        return _failed("This file could not be read; it may be damaged.", software)
