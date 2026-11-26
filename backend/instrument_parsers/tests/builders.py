"""Tiny synthetic TIFF, FCS and ABIF files for the tests (and for the demo files)."""

import io
import struct

import numpy as np
import tifffile


def make_tiff(array: np.ndarray, **kwargs) -> bytes:
    buffer = io.BytesIO()
    tifffile.imwrite(buffer, array, **kwargs)
    return buffer.getvalue()


def make_fcs(
    events: np.ndarray, names: list[str], labels: list[str] | None = None, extra: dict | None = None
) -> bytes:
    """FCS 3.1, list mode, 32-bit floats, little endian. `events` is (events, parameters)."""
    total, count = events.shape
    keys = {
        "$BEGINANALYSIS": "0",
        "$ENDANALYSIS": "0",
        "$BEGINSTEXT": "0",
        "$ENDSTEXT": "0",
        "$BYTEORD": "1,2,3,4",
        "$DATATYPE": "F",
        "$MODE": "L",
        "$NEXTDATA": "0",
        "$PAR": str(count),
        "$TOT": str(total),
        **(extra or {}),
    }
    for i, name in enumerate(names, 1):
        keys[f"$P{i}N"], keys[f"$P{i}B"], keys[f"$P{i}E"], keys[f"$P{i}R"] = (
            name,
            "32",
            "0,0",
            "262144",
        )
        if labels and labels[i - 1]:
            keys[f"$P{i}S"] = labels[i - 1]
    # the text must know where the data starts, which depends on the text's own length
    text_start = 58
    for _ in range(3):
        keys["$BEGINDATA"], keys["$ENDDATA"] = "0", "0"
        body = "/" + "/".join(f"{k}/{v}" for k, v in keys.items()) + "/"
        data_start = text_start + len(body) + 40
        data = events.astype("<f4").tobytes()
        keys["$BEGINDATA"], keys["$ENDDATA"] = str(data_start), str(data_start + len(data) - 1)
    body = ("/" + "/".join(f"{k}/{v}" for k, v in keys.items()) + "/").encode()
    body += b" " * (data_start - text_start - len(body))
    header = b"FCS3.1    " + b"".join(
        f"{n:>8}".encode()
        for n in (text_start, data_start - 1, data_start, data_start + len(data) - 1, 0, 0)
    )
    return header.ljust(text_start) + body + data


def make_abif(
    bases: str, quality: list[int], channels: dict[str, list[int]], sample: str = "Demo sample"
) -> bytes:
    """ABIF with base calls (PBAS2), quality (PCON2), channel order (FWO_1) and DATA9-12."""
    order = "".join(channels)
    items = [
        ("PBAS", 2, 2, 1, len(bases), bases.encode()),
        ("PCON", 2, 1, 1, len(quality), bytes(quality)),
        ("FWO_", 1, 2, 1, 4, order.encode()),
        ("SMPL", 1, 18, 1, len(sample) + 1, bytes([len(sample)]) + sample.encode()),
    ]
    for n, values in enumerate(channels.values(), 9):
        items.append(("DATA", n, 4, 2, len(values), struct.pack(f">{len(values)}h", *values)))
    out = bytearray(b"ABIF" + struct.pack(">h", 101) + bytes(122))
    entries = []
    for name, number, etype, esize, num, payload in items:
        if len(payload) <= 4:
            offset = struct.unpack(">i", payload.ljust(4, b"\x00"))[0]
        else:
            offset = len(out)
            out += payload + (b"\x00" if len(payload) % 2 else b"")
        entries.append(
            struct.pack(
                ">4siHhiiii", name.encode(), number, etype, esize, num, len(payload), offset, 0
            )
        )
    directory = len(out)
    out += b"".join(entries)
    out[6:34] = struct.pack(
        ">4siHhiiii", b"tdir", 1, 1023, 28, len(entries), len(entries) * 28, directory, 0
    )
    return bytes(out)
