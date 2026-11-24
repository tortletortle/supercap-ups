#!/usr/bin/env python3
"""Check the retained ngspice wrdata output for the residual-path test."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

EXPECTED_COLUMNS = [
    "time", "v(out_live)", "v(out100)", "v(out470)", "v(pg100)",
    "v(pg470)", "v(proof_live)", "v(proof100)", "v(proof470)",
    "v(ready470a)", "v(ready474l)", "v(main)",
    "v(load_voltage_only)", "v(load_qualified)",
]


def read_wrdata(path: Path) -> tuple[list[str], list[list[float]]]:
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise SystemExit(f"FAIL: empty ngspice data file: {path}")
    try:
        [float(value) for value in lines[0]]
        headers = EXPECTED_COLUMNS
        data_lines = lines
    except ValueError:
        headers = [item.lower() for item in lines[0]]
        data_lines = lines[1:]
    rows: list[list[float]] = []
    for number, line in enumerate(data_lines, start=1):
        try:
            row = [float(value) for value in line]
        except ValueError as exc:
            raise SystemExit(f"FAIL: invalid numeric row {number}: {line}") from exc
        if len(row) != len(headers):
            raise SystemExit(f"FAIL: row {number} has {len(row)} columns, expected {len(headers)}")
        if not all(math.isfinite(value) for value in row):
            raise SystemExit(f"FAIL: non-finite value in row {number}")
        rows.append(row)
    if not rows:
        raise SystemExit("FAIL: ngspice data contains no samples")
    return headers, rows


def sample(headers: list[str], rows: list[list[float]], time_s: float, name: str) -> float:
    try:
        column = headers.index(name.lower())
    except ValueError as exc:
        raise SystemExit(f"FAIL: missing vector {name}; got {headers}") from exc
    row = min(rows, key=lambda item: abs(item[0] - time_s))
    if abs(row[0] - time_s) > 2.1e-6:
        raise SystemExit(f"FAIL: no sample near {time_s:g} s for {name}")
    return row[column]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_spice_results.py DATA.csv OUTPUT.json")
    data_path, output_path = map(Path, sys.argv[1:])
    headers, rows = read_wrdata(data_path)
    points = {
        "live_during_proof_V": sample(headers, rows, 1.2e-3, "v(out_live)"),
        "residual_100uF_after_proof_V": sample(headers, rows, 1.299e-3, "v(out100)"),
        "residual_470uF_after_proof_V": sample(headers, rows, 1.299e-3, "v(out470)"),
        "pg_100uF_after_proof_V": sample(headers, rows, 1.299e-3, "v(pg100)"),
        "pg_470uF_after_proof_V": sample(headers, rows, 1.299e-3, "v(pg470)"),
        "proof_live_after_V": sample(headers, rows, 1.299e-3, "v(proof_live)"),
        "proof_470uF_after_V": sample(headers, rows, 1.299e-3, "v(proof470)"),
        "ready_470A_after_V": sample(headers, rows, 1.299e-3, "v(ready470a)"),
        "ready_474L_after_V": sample(headers, rows, 1.299e-3, "v(ready474l)"),
        "load_voltage_only_after_main_loss_V": sample(headers, rows, 2.5e-3, "v(load_voltage_only)"),
        "load_qualified_after_main_loss_V": sample(headers, rows, 2.5e-3, "v(load_qualified)"),
    }

    checks = {
        "live_path_drop_below_100mV": 11.90 < points["live_during_proof_V"] < 12.0,
        "100uF_residual_drops_below_output_window": points["residual_100uF_after_proof_V"] < 10.5,
        "470uF_residual_remains_above_11V": 11.4 < points["residual_470uF_after_proof_V"] < 11.7,
        "100uF_PG_deasserts": points["pg_100uF_after_proof_V"] < 2.5,
        "470uF_PG_can_remain_asserted": points["pg_470uF_after_proof_V"] > 2.5,
        "live_path_proof_passes": points["proof_live_after_V"] > 2.5,
        "residual_path_proof_fails": points["proof_470uF_after_V"] < 2.5,
        "470A_status_only_does_not_ready": points["ready_470A_after_V"] < 2.5,
        "474L_PG_only_does_not_ready": points["ready_474L_after_V"] < 2.5,
        "voltage_only_mux_exposes_residual_false_backup": (
            points["load_voltage_only_after_main_loss_V"]
            > points["load_qualified_after_main_loss_V"] + 2.0
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    summary = {
        "evidence_level": "behavioral_spice",
        "vendor_macromodels": False,
        "hardware_verified": False,
        "points": points,
        "checks": checks,
        "passed": len(checks) - len(failed),
        "total": len(checks),
    }
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(json.dumps(points, indent=2))
    if failed:
        raise SystemExit(f"FAIL: {len(failed)} SPICE acceptance checks: {', '.join(failed)}")
    print(f"PASS: {len(checks)} behavioral SPICE checks")


if __name__ == "__main__":
    main()
