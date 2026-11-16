from decimal import Decimal

import pytest

from labs.units import compatible_units, convert, normalize


@pytest.mark.parametrize(
    ("amount", "src", "dst", "expected"),
    [
        ("10", "mL", "L", "0.01"),
        ("100", "L", "mL", "100000"),
        ("250", "ug", "mg", "0.25"),
        ("1", "kg", "g", "1000"),
        ("2", "µL", "uL", "2"),
        ("1.5", "milliliters", "ml", "1.5"),
        ("3", "vials", "vials", "3"),
        ("1", "mmol", "umol", "1000"),
    ],
)
def test_converts_within_a_kind_of_unit(amount, src, dst, expected):
    assert convert(Decimal(amount), src, dst) == Decimal(expected)


@pytest.mark.parametrize(
    ("src", "dst"), [("mL", "g"), ("vials", "mL"), ("mL", ""), ("", "g"), ("tubes", "boxes")]
)
def test_other_kinds_do_not_convert(src, dst):
    assert convert(Decimal("1"), src, dst) is None


def test_names_are_read_loosely():
    assert normalize(" ML. ") == "ml" and normalize("μL") == "ul" and normalize("Litres") == "l"
    assert "ml" in compatible_units("L") and compatible_units("vials") == []


def test_a_microlitre_off_a_hundred_litres_is_not_lost():
    assert convert(Decimal("1"), "uL", "L") == Decimal("0.000001")
