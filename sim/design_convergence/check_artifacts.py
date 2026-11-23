#!/usr/bin/env python3
"""Validate the hand-maintained design budget, BOM, and acceptance matrix."""
from __future__ import annotations

import csv
from pathlib import Path

from power_stage_budget import TARGET_HOLD_S, hold_time, max_path_for_hold

ROOT = Path(__file__).resolve().parents[2]


def read_table(path: Path, expected_columns: int) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != expected_columns:
            raise SystemExit(f"{path}: expected {expected_columns} columns, got {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise SystemExit(f"{path}: no data rows")
    for index, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise SystemExit(f"{path}:{index}: malformed CSV row")
    return list(reader.fieldnames), rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("FAIL: " + message)


def main() -> None:
    bom_path = ROOT / "hardware/kicad/BOM_PRELIMINARY.csv"
    acceptance_path = ROOT / "sim/design_convergence/acceptance_matrix.csv"
    design_path = ROOT / "hardware/kicad/POWER_STAGE_DESIGN_CONVERGENCE.md"
    cell_uv_path = ROOT / "hardware/kicad/cell-uv-monitor-design.md"
    readme_path = ROOT / "hardware/kicad/README.md"

    bom_header, bom_rows = read_table(bom_path, 11)
    required_bom_columns = {
        "RefDes", "Subsystem", "Manufacturer", "MPN", "Value_or_Rating",
        "Footprint_or_Package", "Key_Rating_or_Constraint",
        "Alternative_or_Second_Source", "Status", "Open_Checks", "Evidence_URL",
    }
    require(required_bom_columns.issubset(set(bom_header)), "BOM schema is missing required fields")
    refs = [row["RefDes"] for row in bom_rows]
    require(len(refs) == len(set(refs)), "BOM RefDes groups must be unique")
    required_bom_values = (
        "RefDes", "Subsystem", "Manufacturer", "MPN", "Value_or_Rating",
        "Footprint_or_Package", "Key_Rating_or_Constraint", "Status", "Open_Checks",
    )
    require(all(all(row[key].strip() for key in required_bom_values) for row in bom_rows),
            "every BOM row must identify its part, rating, package, status, and open checks")
    require(all(all(value.strip() for value in row.values()) for row in tests),
            "every acceptance test field must be populated")
    require(not any(row["Status"].lower() in {"released", "approved", "production"} for row in bom_rows),
            "preliminary BOM must not silently mark unqualified parts as released")

    _, tests = read_table(acceptance_path, 7)
    test_ids = [row["test_id"] for row in tests]
    require(len(test_ids) == len(set(test_ids)), "acceptance test IDs must be unique")
    allowed_status = {"MODEL_ONLY", "NOT_TESTED", "BLOCKED_SPEC"}
    require(all(row["status"] in allowed_status for row in tests),
            "acceptance matrix contains an unknown or release-like status")
    require({"SYS-001", "CHG-002", "CELL-UV-001", "MUX-002", "SAFE-001"}.issubset(set(test_ids)),
            "acceptance matrix is missing a critical subsystem test")

    design = design_path.read_text(encoding="utf-8")
    cell_uv = cell_uv_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")
    for token in ("9.400 V", "12 W", "1.200 s", "100 mΩ", "9.2451–9.3049 V"):
        require(token in design, f"design contract missing immutable constraint: {token}")
    for token in ("VC4A ↔ VC4B", "VC3A ↔ VC3B", "VC3B ↔ VC2",
                  "BOOST_READY 不是该锁存的置位条件", "CELL_PROTECT_VALID"):
        require(token in cell_uv, f"4S cell-monitor design missing interface rule: {token}")
    require("BOM_PRELIMINARY.csv" in readme and "cell-uv-monitor-design.md" in readme,
            "hardware README must link the preliminary BOM and cell UV interface")

    corner = hold_time(0.85, 0.100)
    boundary = hold_time(0.85, 0.150)
    failing = hold_time(0.85, 0.200)
    r_limit = max_path_for_hold(0.85, TARGET_HOLD_S)
    require(corner["hold_s"] >= TARGET_HOLD_S, "100 mOhm EOL corner does not meet 1.2 s")
    require(boundary["hold_s"] >= TARGET_HOLD_S, "150 mOhm boundary regression changed")
    require(failing["hold_s"] < TARGET_HOLD_S, "200 mOhm failure boundary regression changed")
    require(0.150 < r_limit < 0.160, "calculated 85% path-resistance limit drifted outside expected range")

    print(f"PASS: BOM rows={len(bom_rows)}, acceptance tests={len(tests)}")
    print(f"PASS: EOL hold at 85% / 100 mOhm = {corner['hold_s']:.6f} s")
    print(f"PASS: 85% path limit for 1.2 s = {r_limit * 1000:.2f} mOhm")
    print("PASS: 9.4 V ceiling, 4S BQ76905 pin map, pre-start interlock, and document links")


if __name__ == "__main__":
    main()
