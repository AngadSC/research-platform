"""Fail if any installed Python package has a license outside the D2 allowlist."""

import json
import re
import subprocess
import sys

# D2 allowlist, plus LGPL (allowed for backend Python packages only).
ALLOWED = {
    "MIT",
    "MIT-0",  # D34, confirmed in Run 2
    "BSD-2-Clause",
    "BSD-3-Clause",
    "Apache-2.0",
    "ISC",
    "MPL-2.0",
    "PostgreSQL",
    "PSF-2.0",
    "Python-2.0",
    "0BSD",
    "CC0-1.0",
    "Unlicense",
    "BlueOak-1.0.0",
    "HPND",
    "LGPL-2.0-only",
    "LGPL-2.0-or-later",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
}
# CC-BY-4.0 is data-only; allowed for these packages alone.
ALLOWED_FOR_PACKAGE = {"caniuse-lite": {"CC-BY-4.0"}}
# Skipped entirely. The backend is not installed as a package, so it has no own packages.
SKIP = {"pip", "setuptools", "wheel"}
# Unknown or missing license, verified from the package's metadata or LICENSE file.
# name: (SPDX id, one-line reason)
OVERRIDES: dict[str, tuple[str, str]] = {
    "qrcode": ("BSD-3-Clause", "LICENSE is BSD-3-Clause; Other/Proprietary classifier is stale"),
}

ALIASES = {
    "mit license": "MIT",
    "mit/x11": "MIT",
    "expat": "MIT",
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "3-clause bsd license": "BSD-3-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "bsd 2-clause license": "BSD-2-Clause",
    "2-clause bsd license": "BSD-2-Clause",
    "simplified bsd license": "BSD-2-Clause",
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache license version 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
    "mpl 2.0": "MPL-2.0",
    "mozilla public license 2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "psf": "PSF-2.0",
    "psf license": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
    "postgresql license": "PostgreSQL",
    "cc0": "CC0-1.0",
    "cc0 1.0 universal": "CC0-1.0",
    "the unlicense": "Unlicense",
    "blue oak model license 1.0.0": "BlueOak-1.0.0",
    "historical permission notice and disclaimer": "HPND",
    "cc by 4.0": "CC-BY-4.0",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0-only",
    "gnu lesser general public license v3 or later (lgplv3+)": "LGPL-3.0-or-later",
}
CANONICAL = {spdx.lower(): spdx for spdx in ALLOWED | {"CC-BY-4.0"}}

TOKEN_RE = re.compile(
    r"\(|\)|\bAND\b|\bOR\b|\bWITH\b|[^()\s][^()]*?(?=\s+(?:AND|OR|WITH)\b|\s*\)|$)"
)


def normalise_leaf(text: str) -> str:
    text = " ".join(text.split())
    if text.startswith("License :: "):  # trove classifier: keep the last segment
        text = text.split("::")[-1].strip()
    key = text.lower()
    return ALIASES.get(key) or CANONICAL.get(key) or text


def evaluate(expr: str, package: str) -> bool:
    """True if the SPDX-ish expression passes. OR needs one allowed part, AND needs all."""
    tokens = TOKEN_RE.findall(expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def leaf_ok(text: str) -> bool:
        spdx = normalise_leaf(text)
        return spdx in ALLOWED or spdx in ALLOWED_FOR_PACKAGE.get(package, set())

    def parse_or() -> bool:
        nonlocal pos
        result = parse_and()
        while peek() == "OR":
            pos += 1
            result = parse_and() or result
        return result

    def parse_and() -> bool:
        nonlocal pos
        result = parse_atom()
        while peek() == "AND":
            pos += 1
            result = parse_atom() and result
        return result

    def parse_atom() -> bool:
        nonlocal pos
        tok = peek()
        pos += 1
        if tok == "(":
            result = parse_or()
            pos += 1  # closing ")"
            return result
        if peek() == "WITH":  # "X WITH exception" is judged by X alone
            pos += 2
        return leaf_ok(tok or "")

    return bool(tokens) and parse_or()


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json"],
        check=True,
        capture_output=True,
        text=True,
    )
    packages = json.loads(out.stdout)
    offenders = []
    checked = 0
    for pkg in packages:
        name, version = pkg["Name"], pkg["Version"]
        if name.lower() in SKIP:
            continue
        checked += 1
        license_text = pkg.get("License", "").strip()
        if name in OVERRIDES:
            license_text = OVERRIDES[name][0]
        elif license_text.upper() in {"", "UNKNOWN"}:
            offenders.append(f"{name} {version}: missing license")
            continue
        # pip-licenses joins several license classifiers with "; ". Each one must pass.
        if not evaluate(license_text.replace(";", " AND "), name):
            offenders.append(f"{name} {version}: {license_text}")
    if offenders:
        print(f"License check failed for {len(offenders)} package(s):")
        for line in sorted(offenders):
            print(f"  - {line}")
        return 1
    print(f"License check passed for {checked} Python packages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
