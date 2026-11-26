"""Demo instruments for the wet-lab pilot (.night/WETLAB.md). Files come later (the integrator
drops wl-parsers' demo files onto these). Safe to run twice."""

from labs.models import InventoryCategory, InventoryItem

INSTRUMENTS = [
    # name, location, software, serial (fake)
    ("Plate reader (Synergy H1)", "Room 2-104, bench 3", "agilent_gen5", "DEMO-SH1-0001"),
    ("NanoDrop 8000", "Room 2-104, bench 1", "nanodrop_8000", "DEMO-ND8-0002"),
    ("ÄKTA pure 25", "Cold room 2-110", "cytiva_unicorn", "DEMO-AKTA-0003"),
    ("Gel imager (ChemiDoc)", "Room 2-106", "image_tiff", "DEMO-GEL-0004"),
    ("qPCR (CFX Opus 96)", "Room 2-108", "bio_rad_cfx", "DEMO-CFX-0005"),
    ("Sanger sequencing (DNA core)", "DNA core facility", "abi_sanger", "DEMO-SEQ-0006"),
]


def seed(lab, users: dict) -> None:  # noqa: ARG001 (the shared demo signature)
    for name, location, software, serial in INSTRUMENTS:
        InventoryItem.objects.for_lab(lab).get_or_create(
            lab=lab,
            name=name,
            defaults={
                "category": InventoryCategory.EQUIPMENT,
                "location": location,
                "quantity": 1,
                "serial_number": serial,
                "instrument_software": software,
                "notes": "Demo instrument. Drop exported files on its page.",
            },
        )
