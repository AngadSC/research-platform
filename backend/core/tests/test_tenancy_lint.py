"""D18: `.unscoped` and `_base_manager` are allowed only in tenancy, permissions,
admin and migrations. `.raw(` and `.extra(` skip the scope guard, so they are allowed only
in the tests of that guard (review #5)."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"\.unscoped\b|_base_manager")
ALLOWED_NAMES = {"tenancy.py", "permissions.py", "admin.py", "test_tenancy_lint.py"}
RAW_PATTERN = re.compile(r"\.raw\(|\.extra\(")
RAW_ALLOWED_NAMES = {"test_tenancy_lint.py", "test_phase2_review.py"}


def _offenders(pattern, allowed):
    return [
        str(p.relative_to(BACKEND))
        for p in BACKEND.rglob("*.py")
        if p.name not in allowed
        and "migrations" not in p.parts
        and ".venv" not in p.parts
        and pattern.search(p.read_text(encoding="utf-8"))
    ]


def test_unscoped_only_in_allowed_files():
    assert _offenders(PATTERN, ALLOWED_NAMES) == []


def test_raw_and_extra_only_in_allowed_files():
    assert _offenders(RAW_PATTERN, RAW_ALLOWED_NAMES) == []
