"""Demo reagent lots and expiry dates (wet-lab run). Obviously fake; safe to run twice."""

from datetime import timedelta

from django.utils import timezone

from labs.models import InventoryItem

# name, lot, days until expiry, quantity, unit
REAGENTS = [
    ("CMP-Neu5Ac", "CN-2611-A", 21, 5, "mg"),  # expiring soon: shows the flag
    ("IPTG", "IP-4410", 400, 25, "g"),
    ("Maltose", "MT-0923", 700, 500, "g"),
    ("Ni-NTA resin", "NN-7782", 120, 10, "mL"),
]


def seed(lab, users: dict) -> None:
    today = timezone.localdate()
    owner = next(iter(users.values()), None)
    for name, lot, days, quantity, unit in REAGENTS:
        item = InventoryItem.objects.for_lab(lab).filter(name=name).first()
        if item is None:
            item = InventoryItem(
                lab=lab,
                name=name,
                category="reagent",
                quantity=quantity,
                unit=unit,
                location="-20 C freezer" if name == "CMP-Neu5Ac" else "Reagent shelf",
                owner=owner,
            )
        item.lot_number = lot
        item.expiry_date = today + timedelta(days=days)
        item.save()
