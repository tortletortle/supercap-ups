#!/usr/bin/env python3
"""Run averaged storage decks with ngspice; preserve measurement log, RAW, LOG and SHA256."""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from pathlib import Path

EXPECTED = {
    "baseline_1p374803.cir": ("t_boost_floor", 1.3748025771548633),
    "joint_failure_1p146229.cir": ("t_boost_floor", 1.1462287868163392),
    "alternate_1p144457.cir": ("t_boost_floor", 1.1444568315153263),
    "weak_cell_cuv_1p135937.cir": ("t_cell1_cuv", 1.1359367287290603),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_measurement(log_text: str, name: str) -> float:
    match = re.search(rf"(?im)^\\s*{re.escape(name)}\\s*=\\s*([-+0-9.eE]+)", log_text)
    if not match:
        raise RuntimeError(f"measurement {name!r} missing from ngspice measurement log")
    return float(match.group(1))


def run_ngspice(args: list[str], label: str, out: Path) -> subprocess.CompletedProcess:
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    (out / f"{label}.runner.txt").write_text(
        f"command={' '.join(args)}\\nreturncode={completed.returncode}\\n"
        f"stdout:\\n{completed.stdout}\\nstderr:\\n{completed.stderr}",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ngspice {label} failed: {completed.stderr}")
    return completed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ngspice", default="ngspice")
    parser.add_argument("--decks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tolerance-ms", type=float, default=0.25)
    args = parser.parse_args()

    decks = args.decks.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for filename, (measure, expected_s) in EXPECTED.items():
        deck = decks / filename
        if not deck.exists():
            raise FileNotFoundError(deck)
        stem = filename.replace(".cir", "")
        measure_log = out / f"{stem}.measure.log"
        raw = out / f"{stem}.raw"
        raw_log = out / f"{stem}.raw.log"

        # ngspice 45 does not execute .measure in batch mode when -r is used.
        # Run once for measurements, then again to preserve the binary RAW.
        measure_run = run_ngspice(
            [args.ngspice, "-b", "-o", str(measure_log), str(deck)],
            f"{stem}.measure", out,
        )
        measure_text = measure_log.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?i)fatal error|timestep too small|singular matrix|no convergence", measure_text):
            raise RuntimeError(f"ngspice reported a fatal numerical issue in {filename}")
        measured_s = parse_measurement(measure_text, measure)

        raw_run = run_ngspice(
            [args.ngspice, "-b", "-r", str(raw), "-o", str(raw_log), str(deck)],
            f"{stem}.raw", out,
        )
        raw_text = raw_log.read_text(encoding="utf-8", errors="replace")
        if re.search(r"(?i)fatal error|timestep too small|singular matrix|no convergence", raw_text):
            raise RuntimeError(f"ngspice RAW run reported a fatal numerical issue in {filename}")
        if not raw.exists() or raw.stat().st_size == 0:
            raise RuntimeError(f"ngspice did not create a non-empty RAW for {filename}")

        error_ms = (measured_s - expected_s) * 1000.0
        rows.append({
            "deck": filename, "measurement": measure,
            "expected_s": expected_s, "measured_s": measured_s,
            "error_ms": error_ms, "pass": abs(error_ms) <= args.tolerance_ms,
            "raw_bytes": raw.stat().st_size, "raw_sha256": sha256(raw),
            "measure_log_sha256": sha256(measure_log), "raw_log_sha256": sha256(raw_log),
        })
        if abs(error_ms) > args.tolerance_ms:
            raise AssertionError(f"{filename}: {measured_s:.9f}s differs by {error_ms:.3f}ms")

    with (out / "spice_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\\n")
        writer.writeheader()
        writer.writerows(rows)

    manifest = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.csv":
            manifest.append({"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    with (out / "SHA256SUMS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "bytes", "sha256"], lineterminator="\\n")
        writer.writeheader()
        writer.writerows(manifest)
    print(f"ngspice passed {len(rows)}/{len(rows)} averaged storage decks; artifacts: {out}")


if __name__ == "__main__":
    main()
