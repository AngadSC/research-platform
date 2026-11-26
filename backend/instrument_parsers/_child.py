"""Child process of parse_file: reads the file from stdin, prints the JSON summary to stdout.

Runs under `python -I`, so the package's parent folder is added to the path by hand. Sets its own
memory, CPU and file-size limits before importing any parser. Its working directory and TMPDIR are a
throwaway directory made (and removed) by the parent, so a killed child leaves nothing behind.
"""

import json
import os
import sys

TIMEOUT = 45
MEMORY = 1024**3


def main() -> None:
    import resource

    for limit, value in (
        (resource.RLIMIT_AS, MEMORY),
        (resource.RLIMIT_CPU, TIMEOUT),
        (resource.RLIMIT_FSIZE, 64 * 1024**2),  # scratch files some vendor parsers need
    ):
        resource.setrlimit(limit, (value, value))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    filename, software = sys.argv[1], sys.argv[2]
    data = sys.stdin.buffer.read()
    try:
        from instrument_parsers.dispatch import run

        out = run(data, filename, software)
    except BaseException:  # noqa: BLE001 (any parser failure on a hostile file is the same answer)
        out = {
            "status": "failed",
            "software": software,
            "error": "This file could not be read; it may be damaged or in a format we don't know.",
        }
    sys.stdout.write(json.dumps(out, allow_nan=False))


if __name__ == "__main__":
    main()
