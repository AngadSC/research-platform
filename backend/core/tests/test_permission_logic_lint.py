"""Permission checks live only in core/permissions.py: views and serializers may not compare
roles themselves (ARCHITECTURE section 3). Use can()/require() or a permission-module helper."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PATTERN = re.compile(
    r"\brole\s*(==|!=|\bnot\s+in\b|\bin\b)"
    r"|\.role\s*(==|!=|\bnot\s+in\b|\bin\b)"
    r"|(==|!=)\s*(Lab|Project)Role\b"
    r"|\b(is_superuser|is_staff)\b"
)


def _files():
    for p in BACKEND.rglob("*.py"):
        if p.name in ("views.py", "serializers.py") and ".venv" not in p.parts:
            yield p


def test_no_ad_hoc_permission_logic_in_views_or_serializers():
    offenders = [
        f"{p.relative_to(BACKEND)}:{n}: {line.strip()}"
        for p in _files()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if PATTERN.search(line.split("#")[0])
    ]
    assert offenders == []


def test_pattern_catches_the_usual_suspects():
    for bad in (
        "if user.role == 'pi':",
        "if m.role in ADMINS:",
        "x != LabRole.PI",
        "if role not in R:",
    ):
        assert PATTERN.search(bad), bad
