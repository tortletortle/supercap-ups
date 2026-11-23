#!/usr/bin/env python3
"""Validate power-stage budgets, BOM, acceptance matrix, and KiCad interlock pages."""
from __future__ import annotations

import csv
import re
from pathlib import Path

from power_stage_budget import TARGET_HOLD_S, hold_time, max_path_for_hold

ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("FAIL: " + message)


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


def balanced_sexpr(text: str) -> bool:
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not quoted


def extract_expr(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"FAIL: schematic is missing {marker}")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise SystemExit(f"FAIL: unbalanced schematic expression starting {marker}")


def instance_blocks(text: str) -> list[tuple[str, str, str]]:
    pattern = re.compile(
        r'\(symbol \(lib_id "([^"]+)"\)[\s\S]*?\(property "Reference" "([^"]+)"'
    )
    return pattern.findall(text)


def main() -> None:
    bom_path = ROOT / "hardware/kicad/BOM_PRELIMINARY.csv"
    acceptance_path = ROOT / "sim/design_convergence/acceptance_matrix.csv"
    design_path = ROOT / "hardware/kicad/POWER_STAGE_DESIGN_CONVERGENCE.md"
    cell_uv_path = ROOT / "hardware/kicad/cell-uv-monitor-design.md"
    interlock_design_path = ROOT / "hardware/kicad/system-interlock-design.md"
    readme_path = ROOT / "hardware/kicad/README.md"
    root_sch_path = ROOT / "hardware/kicad/supercap-ups-4s.kicad_sch"
    cell_sch_path = ROOT / "hardware/kicad/cell-uv-monitor.kicad_sch"
    interlock_sch_path = ROOT / "hardware/kicad/system-interlock.kicad_sch"
    interlock_lib_path = ROOT / "hardware/kicad/Power_Interlock.kicad_sym"
    sym_table_path = ROOT / "hardware/kicad/sym-lib-table"

    bom_header, bom_rows = read_table(bom_path, 11)
    required_bom_columns = {
        "RefDes", "Subsystem", "Manufacturer", "MPN", "Value_or_Rating",
        "Footprint_or_Package", "Key_Rating_or_Constraint",
        "Alternative_or_Second_Source", "Status", "Open_Checks", "Evidence_URL",
    }
    require(required_bom_columns.issubset(set(bom_header)), "BOM schema is missing required fields")
    bom_refs = [row["RefDes"] for row in bom_rows]
    require(len(bom_refs) == len(set(bom_refs)), "BOM RefDes groups must be unique")
    required_bom_values = (
        "RefDes", "Subsystem", "Manufacturer", "MPN", "Value_or_Rating",
        "Footprint_or_Package", "Key_Rating_or_Constraint", "Status", "Open_Checks",
    )
    require(all(all(row[key].strip() for key in required_bom_values) for row in bom_rows),
            "every BOM row must identify its part, rating, package, status, and open checks")
    require(not any(row["Status"].lower() in {"released", "approved", "production"} for row in bom_rows),
            "preliminary BOM must not silently mark unqualified parts as released")

    _, tests = read_table(acceptance_path, 7)
    test_ids = [row["test_id"] for row in tests]
    require(len(test_ids) == len(set(test_ids)), "acceptance test IDs must be unique")
    require(all(all(value.strip() for value in row.values()) for row in tests),
            "every acceptance test field must be populated")
    allowed_status = {"MODEL_ONLY", "NOT_TESTED", "BLOCKED_SPEC"}
    require(all(row["status"] in allowed_status for row in tests),
            "acceptance matrix contains an unknown or release-like status")
    require({"SYS-001", "CHG-002", "CELL-UV-001", "MUX-002", "SAFE-001", "ILK-001", "ILK-009", "MUX-005", "MUX-006", "MUX-007", "MUX-008", "MUX-009"}.issubset(set(test_ids)),
            "acceptance matrix is missing a critical subsystem test")

    design = design_path.read_text(encoding="utf-8")
    cell_uv = cell_uv_path.read_text(encoding="utf-8")
    interlock_design = interlock_design_path.read_text(encoding="utf-8")
    readme = readme_path.read_text(encoding="utf-8")
    sym_table = sym_table_path.read_text(encoding="utf-8")
    interlock_lib = interlock_lib_path.read_text(encoding="utf-8")
    for token in ("9.400 V", "12 W", "1.200 s", "100 mΩ", "9.2451–9.3049 V"):
        require(token in design, f"design contract missing immutable constraint: {token}")
    for token in ("VC4A ↔ VC4B", "VC3A ↔ VC3B", "VC3B ↔ VC2",
                  "BOOST_READY 不是该锁存的置位条件", "CELL_PROTECT_VALID", "10 Ω", "220 nF"):
        require(token in cell_uv, f"4S cell-monitor design missing interface/filter rule: {token}")
    require("cell-uv-monitor.kicad_sch" in design and "cell-uv-monitor.kicad_sch" in readme,
            "BQ76905 schematic page must be linked from design review and README")
    for token in ("ARM_PERMIT", "SN74LVC1G74", "TPS3839G33", "D910", "启动超时", "not implemented"):
        require(token.lower() in interlock_design.lower(), f"interlock design missing rule: {token}")
    require("system-interlock.kicad_sch" in readme, "system interlock schematic must be linked from README")
    require('(lib (name "Power_Interlock")' in sym_table, "symbol table is missing Power_Interlock library")
    for token in ("SN74LVC1G74DCT", "SN74LVC1G08DBVR", "SN74LVC1G17DBVR",
                  "TPS3839G33DQNT", "J910_HOST_ARM", "D_FAST_DISCHARGE"):
        require(token in interlock_lib, f"Power_Interlock library missing symbol {token}")

    root_sch = root_sch_path.read_text(encoding="utf-8")
    cell_sch = cell_sch_path.read_text(encoding="utf-8")
    interlock_sch = interlock_sch_path.read_text(encoding="utf-8")
    require(balanced_sexpr(root_sch), "top-level KiCad schematic has unbalanced S-expression")
    require(balanced_sexpr(cell_sch), "BQ76905 KiCad schematic has unbalanced S-expression")
    require(balanced_sexpr(interlock_sch), "system interlock KiCad schematic has unbalanced S-expression")
    require('Sheetfile" "cell-uv-monitor.kicad_sch"' in root_sch,
            "BQ76905 page is not attached to top-level hierarchy")
    require('uuid "5db7c0a1-6a2c-4b73-9a41-23f4c8d0e801"' in root_sch,
            "top-level sheet UUID does not match BQ76905 page")
    require('Sheetfile" "system-interlock.kicad_sch"' in root_sch,
            "system interlock page is not attached to top-level hierarchy")
    require('uuid "8a9c4e61-72b3-4f5a-9d10-0b2c3d4e5f61"' in root_sch,
            "top-level sheet UUID does not match system interlock page")
    require('/4f184fe9-3a22-483f-9ea4-3479fb50ee2d/5db7c0a1-6a2c-4b73-9a41-23f4c8d0e801' in cell_sch,
            "BQ76905 component paths do not match parent sheet")
    require('/4f184fe9-3a22-483f-9ea4-3479fb50ee2d/8a9c4e61-72b3-4f5a-9d10-0b2c3d4e5f61' in interlock_sch,
            "system interlock component paths do not match parent sheet")

    lib_ids = set(re.findall(r'\(symbol "([^"]+)"', cell_sch))
    instances = instance_blocks(cell_sch)
    refs = [ref for _, ref in instances]
    require(len(refs) == len(set(refs)), "BQ76905 schematic contains duplicate references")
    require(len(instances) == 28, f"expected 28 BQ76905 page components, found {len(instances)}")
    require(all(lib_id in lib_ids for lib_id, _ in instances),
            "BQ76905 instance references a missing embedded library symbol")
    bq_instance = extract_expr(cell_sch, '(symbol (lib_id "BQ76905:BQ76905")')
    pin_numbers = re.findall(r'\(pin "(\d+)"', bq_instance)
    require(sorted(pin_numbers, key=int) == [str(i) for i in range(1, 21)],
            "BQ76905 instance must contain pins 1 through 20 exactly once")
    require(len(re.findall(r'\(no_connect ', cell_sch)) == 2,
            "unused BQ76905 DSG/CHG pins must be explicitly no-connect")
    labels = re.findall(r'\(global_label "([^"]+)"', cell_sch)
    required_labels = {
        "GND", "CELL_1", "CELL_2", "CELL_3", "PACK_4S", "VC0_SENSE",
        "VC1_SENSE", "CELL2_SENSE", "CELL3_SENSE", "PACK_SENSE",
        "BAT_FILTERED", "REGSRC_FILTERED", "CELL_3V3",
        "CELL_I2C_SCL", "CELL_I2C_SDA", "CELL_MON_ALERT_L",
    }
    require(required_labels.issubset(set(labels)),
            f"BQ76905 page missing labels: {sorted(required_labels - set(labels))}")
    require(labels.count("CELL2_SENSE") >= 6, "4S VC2/VC3A/VC3B short group is incomplete")
    require(labels.count("CELL3_SENSE") >= 4, "4S VC4A/VC4B short group is incomplete")
    require(len(re.findall(r'\(symbol \(lib_id "power:PWR_FLAG"\)', cell_sch)) == 7,
            "filtered VC/BAT/REGSRC rails must carry explicit ERC source flags")

    interlock_lib_ids = set(re.findall(r'\(symbol "([^"]+)"', interlock_sch))
    interlock_instances = instance_blocks(interlock_sch)
    interlock_refs = [ref for _, ref in interlock_instances]
    require(len(interlock_refs) == len(set(interlock_refs)), "system interlock has duplicate references")
    require(len(interlock_instances) == 15,
            f"expected 15 system interlock components, found {len(interlock_instances)}")
    require(all(lib_id in interlock_lib_ids for lib_id, _ in interlock_instances),
            "system interlock instance references a missing embedded library symbol")
    dff = extract_expr(interlock_sch, '(symbol (lib_id "Power_Interlock:SN74LVC1G74DCT")')
    dff_pins = re.findall(r'\(pin "(\d+)"', dff)
    require(sorted(dff_pins, key=int) == [str(i) for i in range(1, 9)],
            "SN74LVC1G74 DFF instance must contain pins 1 through 8")
    supervisor = extract_expr(interlock_sch, '(symbol (lib_id "Power_Interlock:TPS3839G33DQNT")')
    supervisor_pins = re.findall(r'\(pin "(\d+)"', supervisor)
    require(sorted(supervisor_pins, key=int) == ["1", "2", "3", "4"],
            "TPS3839G33 supervisor instance must contain pins 1 through 4")
    interlock_labels = set(re.findall(r'\(global_label "([^"]+)"', interlock_sch))
    interlock_required = {
        "PACK_UV_OK", "CELL_MON_PG", "CELL_CONFIG_VALID", "CELL_MON_ALERT_L",
        "MANUAL_ARM_REQ", "ARM_PERMIT", "DISCHARGE_ARM", "BOOST_EN_DELAY",
        "BOOST_EN", "CELL_3V3", "GND", "SAFE_A", "SAFE_B",
    }
    require(interlock_required.issubset(interlock_labels),
            f"system interlock missing labels: {sorted(interlock_required - interlock_labels)}")
    require(len(re.findall(r'\(no_connect ', interlock_sch)) == 3,
            "DFF Q_N, supervisor NC and Schmitt NC pins must be explicitly no-connect")
    interlock_uuids = re.findall(r'\(uuid "([^"]+)"\)', interlock_sch)
    require(len(interlock_uuids) == len(set(interlock_uuids)),
            "system interlock page contains duplicate UUIDs")

    bom_ref_set = set(bom_refs)
    for ref in ("U801", "R801-R805", "R806", "R807", "R808-R810",
                "C801-C805", "C806", "C807", "C808", "D801/D802",
                "U910", "U911-U913", "U914", "U915", "J910", "R910", "R911",
                "R912-R915", "C910", "D910"):
        require(ref in bom_ref_set, f"preliminary BOM missing item {ref}")

    corner = hold_time(0.85, 0.100)
    boundary = hold_time(0.85, 0.150)
    failing = hold_time(0.85, 0.200)
    r_limit = max_path_for_hold(0.85, TARGET_HOLD_S)
    require(corner["hold_s"] >= TARGET_HOLD_S, "100 mOhm EOL corner does not meet 1.2 s")
    require(boundary["hold_s"] >= TARGET_HOLD_S, "150 mOhm boundary regression changed")
    require(failing["hold_s"] < TARGET_HOLD_S, "200 mOhm failure boundary regression changed")
    require(0.150 < r_limit < 0.160, "85% path-resistance limit drifted outside expected range")

    print(f"PASS: BOM rows={len(bom_rows)}, acceptance tests={len(tests)}")
    print(f"PASS: BQ76905 page components={len(instances)}, pins={len(pin_numbers)}")
    print(f"PASS: system interlock components={len(interlock_instances)}, DFF pins={len(dff_pins)}")
    print(f"PASS: EOL hold at 85% / 100 mOhm = {corner['hold_s']:.6f} s")
    print(f"PASS: 85% path limit for 1.2 s = {r_limit * 1000:.2f} mOhm")


if __name__ == "__main__":
    main()
