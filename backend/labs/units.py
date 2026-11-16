"""Units of volume, mass and amount of substance, so "10 mL" can come off "100 L" (D328).

Only units of the same kind convert (litres to millilitres, grams to milligrams). Everything else
(vials, tubes, boxes, "each") only matches itself: we never guess how many vials make a litre.
Factors are exact decimals, and results keep six decimal places, the precision stock is stored in.
"""

import re
from decimal import ROUND_HALF_EVEN, Decimal

PLACES = Decimal("0.000001")

_D = Decimal
FAMILIES: dict[str, dict[str, Decimal]] = {
    "volume": {  # litres
        "l": _D(1),
        "dl": _D("0.1"),
        "cl": _D("0.01"),
        "ml": _D("0.001"),
        "ul": _D("0.000001"),
        "nl": _D("0.000000001"),
    },
    "mass": {  # grams
        "kg": _D(1000),
        "g": _D(1),
        "mg": _D("0.001"),
        "ug": _D("0.000001"),
        "ng": _D("0.000000001"),
    },
    "amount": {  # moles
        "mol": _D(1),
        "mmol": _D("0.001"),
        "umol": _D("0.000001"),
        "nmol": _D("0.000000001"),
    },
}
ALIASES = {
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "microliter": "ul",
    "microliters": "ul",
    "microlitre": "ul",
    "microlitres": "ul",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "milligram": "mg",
    "milligrams": "mg",
    "microgram": "ug",
    "micrograms": "ug",
    "mole": "mol",
    "moles": "mol",
}


def normalize(unit: str) -> str:
    """ "mL", " ML ", "µl" and "microliters" all read as one spelling per unit."""
    text = re.sub(r"[\s.]", "", (unit or "").casefold()).replace("µ", "u").replace("μ", "u")
    return ALIASES.get(text, text)


def _family(unit: str) -> str | None:
    return next((name for name, units in FAMILIES.items() if unit in units), None)


def convert(amount: Decimal, source: str, target: str) -> Decimal | None:
    """`amount` of `source` expressed in `target`, or None if they are not the same kind of unit."""
    a, b = normalize(source), normalize(target)
    if a == b:
        return amount.quantize(PLACES, rounding=ROUND_HALF_EVEN)
    fam = _family(a)
    if fam is None or fam != _family(b):
        return None
    units = FAMILIES[fam]
    return (amount * units[a] / units[b]).quantize(PLACES, rounding=ROUND_HALF_EVEN)


def compatible_units(unit: str) -> list[str]:
    """Units that convert to and from `unit` (none for vials, tubes and so on)."""
    fam = _family(normalize(unit))
    return list(FAMILIES[fam]) if fam else []
