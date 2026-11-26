"""STUB until wl-parsers merges (.night/WETLAB.md): same signature, parses nothing.

The real package runs each parser in a child process with CPU and memory limits and returns a
JSON-safe summary. `parse_file` never raises.
"""

SOFTWARE_CHOICES: list[tuple[str, str]] = [
    ("agilent_gen5", "Agilent BioTek Gen5"),
    ("molecular_devices_softmax_pro", "Molecular Devices SoftMax Pro"),
    ("thermo_nanodrop_one", "Thermo NanoDrop One"),
    ("biorad_cfx_maestro", "Bio-Rad CFX Maestro"),
    ("thermo_quantstudio", "Thermo QuantStudio"),
    ("cytiva_unicorn", "Cytiva UNICORN (ÄKTA)"),
    ("thermo_chromeleon", "Thermo Chromeleon"),
    ("generic_csv", "Spreadsheet or CSV"),
    ("image_tiff", "Image (TIFF)"),
    ("fcs", "Flow cytometry (FCS)"),
    ("abi_sanger", "Sanger sequencing (AB1)"),
]


def parse_file(data: bytes, filename: str, software: str = "") -> dict:
    return {"status": "unsupported", "software": software}
