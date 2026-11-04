"""D18: `.unscoped` and `_base_manager` are allowed only in tenancy, permissions,
admin and migrations."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"\.unscoped\b|_base_manager")
ALLOWED_NAMES = {"tenancy.py", "permissions.py", "admin.py", "test_tenancy_lint.py"}


def test_unscoped_only_in_allowed_files():
    offenders = [
        str(p.relative_to(BACKEND))
        for p in BACKEND.rglob("*.py")
        if p.name not in ALLOWED_NAMES
        and "migrations" not in p.parts
        and ".venv" not in p.parts
        and PATTERN.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
