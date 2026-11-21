"""Small, dependency-light reader for LTspice binary real RAW files."""
from pathlib import Path
import re

import numpy as np


def load_raw(path):
    """Return (decoded_header, variable_names, read-only memmap).

    Supports interleaved real-double transient RAW files. Fast-access and
    single-precision RAW layouts are rejected explicitly instead of being
    misinterpreted.
    """
    path = Path(path)
    with path.open("rb") as f:
        header_bytes = f.read(65536)

    offset = None
    for ending in ("Binary:\n", "Binary:\r\n"):
        marker = ending.encode("utf-16le")
        found = header_bytes.find(marker)
        if found >= 0:
            offset = found + len(marker)
            break
    if offset is None:
        raise ValueError("No LTspice UTF-16 Binary marker in first 64 KiB")

    header = header_bytes[:offset].decode("utf-16le")
    nvars_match = re.search(r"No\. Variables:\s+(\d+)", header)
    npoints_match = re.search(r"No\. Points:\s+(\d+)", header)
    flags_match = re.search(r"Flags:\s+([^\r\n]+)", header)
    if not nvars_match or not npoints_match or not flags_match:
        raise ValueError("Incomplete LTspice RAW header")

    nvars = int(nvars_match.group(1))
    npoints = int(npoints_match.group(1))
    flags = flags_match.group(1).lower()
    names = re.findall(r"^\s*\d+\s+([^\t\r\n]+)\t", header, re.M)

    if nvars < 1 or npoints < 1:
        raise ValueError("RAW header declares zero variables or points")
    if "double" not in flags or "fastaccess" in flags:
        raise ValueError(
            "This reader requires interleaved real-double RAW "
            "(Flags must include 'double' and must not include 'fastaccess')"
        )

    expected_size = offset + 8 * nvars * npoints
    actual_size = path.stat().st_size
    if actual_size != expected_size or len(names) != nvars:
        raise ValueError(
            f"Incomplete or unsupported RAW: size {actual_size} != "
            f"expected {expected_size}; variable names {len(names)} != {nvars}"
        )

    data = np.memmap(
        path, mode="r", dtype="<f8", offset=offset, shape=(npoints, nvars)
    )
    return header, names, data
