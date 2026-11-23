#!/usr/bin/env python3
"""Package a verified LTspice ASC and every referenced ASY for JLC EDA import.

This script deliberately fails closed when a symbol file is missing, ambiguous,
or has an invalid pin-order table. It does not validate circuit behavior,
pin-to-footprint mapping, or PCB readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

SYMBOL_RE = re.compile(r"^\s*SYMBOL\s+(\S+)", re.IGNORECASE | re.MULTILINE)
PIN_ORDER_RE = re.compile(r"PINATTR\s+SpiceOrder\s+(\d+)", re.IGNORECASE)
EXPECTED_PIN_COUNTS = {"bi": 2, "cap": 2, "ind": 2, "res": 2, "voltage": 2}
SIM_DIRECTIVE_RE = re.compile(
    r"^\s*TEXT\b.*!\.(include|ic|save|options|tran|meas)\b",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def symbol_relpath(symbol: str) -> Path:
    return Path(*symbol.replace("\\", "/").split("/")).with_suffix(".asy")


def candidate_symbols(symbol: str, asc_dir: Path, roots: list[Path]) -> list[Path]:
    rel = symbol_relpath(symbol)
    local = asc_dir / rel
    if local.is_file():
        return [local]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        exact = root / rel
        if exact.is_file():
            found.append(exact)
            continue
        # LTspice library symbols may live in subfolders while ASC stores a bare name.
        if len(rel.parts) == 1:
            found.extend(p for p in root.rglob(rel.name) if p.is_file())
    # Deduplicate identical files, but reject conflicting same-name candidates.
    unique: dict[str, Path] = {}
    for p in found:
        unique.setdefault(sha256(p), p)
    return list(unique.values())


def default_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("LTSPICE_SYM_ROOT")
    if env:
        roots.append(Path(env).expanduser())
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "LTspice" / "lib" / "sym")
    for base in (
        Path("C:/Program Files/ADI/LTspice/lib/sym"),
        Path("C:/Program Files/Analog Devices/LTspice/lib/sym"),
        Path("/mnt/c/Program Files/ADI/LTspice/lib/sym"),
        Path("/mnt/c/Program Files/Analog Devices/LTspice/lib/sym"),
    ):
        roots.append(base)
    return roots


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asc", required=True, type=Path, help="Verified Weave-generated ASC")
    ap.add_argument("--output", required=True, type=Path, help="Destination JLC import ZIP")
    ap.add_argument("--symbol-root", action="append", default=[], type=Path,
                    help="LTspice lib/sym root; may be repeated")
    ap.add_argument("--report", type=Path, help="Optional JSON manifest path")
    args = ap.parse_args()

    asc = args.asc.resolve()
    if not asc.is_file():
        print(f"ERROR: ASC not found: {asc}", file=sys.stderr)
        return 2
    try:
        asc_text = asc.read_text(encoding="latin-1")
    except OSError as exc:
        print(f"ERROR: cannot read ASC: {exc}", file=sys.stderr)
        return 2

    symbols = sorted(set(SYMBOL_RE.findall(asc_text)), key=str.lower)
    if not symbols:
        print("ERROR: no SYMBOL records found in ASC", file=sys.stderr)
        return 2

    roots = [p.expanduser().resolve() for p in args.symbol_root] or default_roots()
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    ambiguous: dict[str, list[str]] = {}
    for symbol in symbols:
        candidates = candidate_symbols(symbol, asc.parent, roots)
        if not candidates:
            missing.append(symbol)
        elif len(candidates) > 1:
            ambiguous[symbol] = [str(p) for p in candidates]
        else:
            resolved[symbol] = candidates[0]

    invalid: dict[str, str] = {}
    pin_orders_by_symbol: dict[str, list[int]] = {}
    for symbol, source in resolved.items():
        try:
            asy_text = source.read_text(encoding="latin-1")
            if not asy_text.lstrip().startswith("Version "):
                raise ValueError("missing LTspice Version header")
            orders = [int(x) for x in PIN_ORDER_RE.findall(asy_text)]
            if not orders:
                raise ValueError("no PINATTR SpiceOrder records")
            if sorted(orders) != list(range(1, len(orders) + 1)):
                raise ValueError(f"SpiceOrder must be unique and contiguous: {orders}")
            expected = EXPECTED_PIN_COUNTS.get(symbol.lower())
            block_match = re.fullmatch(r"__block(\d+)", symbol, re.IGNORECASE)
            if block_match:
                expected = int(block_match.group(1))
            if expected is not None and len(orders) != expected:
                raise ValueError(f"expected {expected} pins, found {len(orders)}")
            pin_orders_by_symbol[symbol] = orders
        except (OSError, UnicodeError, ValueError) as exc:
            invalid[symbol] = str(exc)

    if missing or ambiguous or invalid:
        if missing:
            print("MISSING_ASY=" + ",".join(missing), file=sys.stderr)
        if ambiguous:
            print("AMBIGUOUS_ASY=" + json.dumps(ambiguous, ensure_ascii=False), file=sys.stderr)
        if invalid:
            print("INVALID_ASY=" + json.dumps(invalid, ensure_ascii=False), file=sys.stderr)
        print("ERROR: refusing to create an incomplete, ambiguous, or pin-invalid JLC import ZIP", file=sys.stderr)
        return 3

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # JLC EDA imports the schematic, not LTspice simulation directives or model
    # libraries. Strip only the listed TEXT directives from the ZIP copy; keep the
    # original ASC untouched next to the source netlist and model dependency.
    jlc_lines: list[str] = []
    stripped_directives: list[str] = []
    for line in asc_text.splitlines():
        if SIM_DIRECTIVE_RE.match(line):
            stripped_directives.append(line)
        else:
            jlc_lines.append(line)
    jlc_asc_bytes = ("\n".join(jlc_lines) + "\n").encode("latin-1")

    # The ZIP contains only the JLC-specific ASC copy and its corresponding ASY
    # files, as required by the documented LTspice import flow. Model libraries
    # and the untouched simulation ASC remain outside this import-only ZIP.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(asc.name, jlc_asc_bytes)
        for symbol, source in resolved.items():
            rel = symbol_relpath(symbol)
            zf.write(source, arcname=rel.as_posix())

    jlc_asc_sha = hashlib.sha256(jlc_asc_bytes).hexdigest().upper()
    manifest = {
        "format": "JLCEDA-Pro LTspice import ZIP",
        "asc": {"file": asc.name, "source_sha256": sha256(asc), "jlc_copy_sha256": jlc_asc_sha},
        "stripped_simulation_directives": stripped_directives,
        "symbols": [
            {"name": name, "file": symbol_relpath(name).as_posix(),
             "source": str(resolved[name]), "sha256": sha256(resolved[name]),
             "pin_orders": pin_orders_by_symbol[name]}
            for name in symbols
        ],
        "zip": {"file": str(output), "sha256": sha256(output)},
        "qualification_scope": "file packaging only; GUI import and electrical simulation not implied",
        "not_production_ready": True,
        "warning": "The selected TPS61088 input is a simulation testbench. Its synthetic __blockN symbol is not the real IC pinout or PCB footprint.",
    }
    report = args.report.resolve() if args.report else output.with_suffix(".manifest.json")
    report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"JLC_ZIP={output}")
    print(f"SYMBOL_COUNT={len(symbols)}")
    print(f"STRIPPED_SIM_DIRECTIVES={len(stripped_directives)}")
    print(f"SHA256={sha256(output)}")
    print(f"MANIFEST={report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
