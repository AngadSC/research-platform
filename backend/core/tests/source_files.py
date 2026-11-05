"""Backend .py files for the lint tests, without walking the host's git-ignored .venv."""

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def backend_py_files():
    yield from BACKEND.glob("*.py")
    for d in BACKEND.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            yield from d.rglob("*.py")
