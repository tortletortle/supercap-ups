#!/usr/bin/env python3
"""Fail-closed TPS61088 final validation runner for a Windows LTspice host.

The runner reprocesses archived 50/25 ns RAW files first. It only launches
12.5 ns when pairing-v2 requires it, and only launches RILIM and dynamic tests
after 12.5 ns passes the explicit convergence gate. Inputs and outputs are
isolated under a unique timestamped directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parents[1]
REPO_ROOT = HERE.parents[1]
SCRIPTS = HERE / "scripts"
DIAGNOSTICS = HERE / "diagnostics"
RESULTS = HERE / "results" / "final_device_audit"
MODEL = HERE.parent / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB"
PAIRING_RUNNER = SCRIPTS / "run_fsw_internal_pairing_v2.py"
ANALYZER = SCRIPTS / "analyze_fsw_internal.py"
MATRIX_GENERATOR = SCRIPTS / "generate_rilim_matrix.py"
DYNAMIC_GENERATOR = SCRIPTS / "generate_dynamic_cases.py"
EOL_SWEEP = SCRIPTS / "eol_efficiency_budget_sweep.py"

MEASUREMENT_NAMES = (
    "t90", "t98", "sw_t6001", "sw_t6101", "f_sw_khz",
    "avg_vout", "vout_min", "ripple", "peak_i", "peak_i_steady",
    "peak_start", "il_rms", "peak_switch_sense", "peak_switch_sense_steady",
    "ilim_threshold", "ilim_threshold_min", "ilim_threshold_max",
    "ilim_margin_steady", "vout_min_overcurrent", "peak_i_overcurrent",
    "peak_switch_sense_overcurrent", "ilim_threshold_overcurrent",
    "ilim_margin_overcurrent", "iin_peak_overcurrent", "vout_after_overcurrent",
    "iin_avg", "iout_avg", "pin_avg", "pout_avg", "eta_pct",
    "vload_min_step", "vout_min_step", "il_peak_step", "iin_peak_step",
    "vload_recover", "vout_min_short", "il_peak_short", "iin_peak_short", "vout_recover",
)
RILIM_REQUIRED = (
    "t90", "t98", "f_sw_khz", "avg_vout", "vout_min", "ripple",
    "peak_i", "peak_i_steady", "peak_start", "il_rms", "peak_switch_sense",
    "peak_switch_sense_steady", "ilim_threshold", "ilim_threshold_min",
    "ilim_threshold_max", "ilim_margin_steady", "iin_avg", "iout_avg",
    "pin_avg", "pout_avg", "eta_pct", "vout_min_overcurrent",
    "peak_i_overcurrent", "peak_switch_sense_overcurrent",
    "ilim_threshold_overcurrent", "ilim_margin_overcurrent",
    "iin_peak_overcurrent", "vout_after_overcurrent",
)
LOADSTEP_REQUIRED = ("vload_min_step", "vout_min_step", "il_peak_step", "iin_peak_step", "vload_recover")
SHORT_REQUIRED = ("vout_min_short", "il_peak_short", "iin_peak_short", "vout_recover")
OVERCURRENT_REQUIRED = (
    "vout_min_overcurrent", "peak_i_overcurrent", "peak_switch_sense_overcurrent",
    "ilim_threshold_overcurrent", "ilim_margin_overcurrent", "iin_peak_overcurrent",
    "vout_after_overcurrent",
)
VIN_SCAN_REQUIRED = (
    "f_sw_khz", "avg_vout", "vout_min", "ripple", "peak_i", "peak_start",
    "il_rms", "peak_switch_sense", "ilim_threshold", "iin_avg", "iout_avg",
    "pin_avg", "pout_avg", "eta_pct",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_ltspice(requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"LTspice executable not found: {path}")
        return path
    candidates = []
    for env_name in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value) / "Programs" / "ADI" / "LTspice" / "LTspice.exe")
            candidates.append(Path(value) / "ADI" / "LTspice" / "LTspice.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError("LTspice.exe not found; pass --ltspice with its absolute path")


def parse_measurements(log_path: Path | None) -> dict[str, str]:
    values = {name: "" for name in MEASUREMENT_NAMES}
    if not log_path or not log_path.is_file():
        return values
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for name in MEASUREMENT_NAMES:
        pattern = rf"(?im)^\s*{re.escape(name)}\s*[:=]\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
        match = re.search(pattern, text)
        if match:
            values[name] = match.group(1)
    return values


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_run_root() -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = RESULTS / stem
    suffix = 1
    while candidate.exists():
        candidate = RESULTS / f"{stem}_{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def run_logged(command: list[str], cwd: Path, out_dir: Path, stem: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, errors="replace", check=False)
    (out_dir / f"{stem}.stdout.log").write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    (out_dir / f"{stem}.stderr.log").write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    return completed


def required_measurement_fields(category: str) -> tuple[str, ...]:
    if category == "RILIM_MATRIX":
        return RILIM_REQUIRED
    if category == "DYNAMIC_LOADSTEP":
        return LOADSTEP_REQUIRED
    if category == "DYNAMIC_SHORT":
        return SHORT_REQUIRED
    if category == "DYNAMIC_OVERCURRENT":
        return OVERCURRENT_REQUIRED
    if category == "VIN_SCAN":
        return VIN_SCAN_REQUIRED
    return ()


def run_case(deck: Path, category: str, ltspice: Path, run_root: Path) -> tuple[dict[str, Any], dict[str, Any], Path | None, Path]:
    case_dir = run_root / "cases" / deck.stem
    case_dir.mkdir(parents=True, exist_ok=False)
    original_text = deck.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"(?im)^\s*\.include\s+", original_text):
        raise ValueError(f"No .include directive in {deck}")
    executed_text = re.sub(r"(?im)^\s*\.include\s+.*$", ".include TPS61088_LT.LIB", original_text, count=1)
    executed_deck = case_dir / deck.name
    executed_deck.write_text(executed_text, encoding="ascii", newline="\n")
    shutil.copy2(MODEL, case_dir / MODEL.name)

    row: dict[str, Any] = {
        "category": category, "case": deck.stem, "source_deck_path": str(deck),
        "source_deck_sha256": sha256(deck), "executed_deck_path": str(executed_deck),
        "executed_deck_sha256": sha256(executed_deck), "model_sha256": sha256(MODEL),
        "ltspice_exit_code": "", "status": "", "raw_path": "", "raw_bytes": 0,
        "raw_sha256": "", "log_path": "", "log_sha256": "", "op_raw_sha256": "", "db_sha256": "",
        "error": "",
    }
    completed = subprocess.run([str(ltspice), "-b", executed_deck.name], cwd=case_dir,
                               capture_output=True, text=True, errors="replace", check=False)
    (case_dir / "ltspice_stdout.log").write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    (case_dir / "ltspice_stderr.log").write_text(completed.stderr or "", encoding="utf-8", errors="replace")
    row["ltspice_exit_code"] = completed.returncode

    raw_path = case_dir / f"{deck.stem}.raw"
    log_path = case_dir / f"{deck.stem}.log"
    op_raw = case_dir / f"{deck.stem}.op.raw"
    db_path = case_dir / f"{deck.stem}.db"
    if completed.returncode == 0 and raw_path.is_file() and log_path.is_file():
        row["status"] = "LTSPICE_EXIT0_RAW_LOG_SAVED"
        row["raw_path"] = str(raw_path)
        row["raw_bytes"] = raw_path.stat().st_size
        row["raw_sha256"] = sha256(raw_path)
        row["log_path"] = str(log_path)
        row["log_sha256"] = sha256(log_path)
        if op_raw.is_file(): row["op_raw_sha256"] = sha256(op_raw)
        if db_path.is_file(): row["db_sha256"] = sha256(db_path)
    else:
        row["status"] = "INCOMPLETE_OR_FAILED"
        row["error"] = "LTspice nonzero exit or missing RAW/LOG"
        raw_path = None
        log_path = None

    measurements = {"category": category, "case": deck.stem, **parse_measurements(log_path)}
    required = required_measurement_fields(category)
    missing = [name for name in required if not measurements.get(name)]
    if row["status"] == "LTSPICE_EXIT0_RAW_LOG_SAVED" and missing:
        row["status"] = "INCOMPLETE_MEASUREMENT_FIELDS"
        row["error"] = "missing .meas outputs: " + ", ".join(missing)
    measurements["missing_required_measurements"] = ";".join(missing)
    return row, measurements, raw_path, case_dir


def write_sha256_manifest(root: Path) -> None:
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"):
        lines.append(f"{sha256(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-50", type=Path, required=True)
    parser.add_argument("--raw-25", type=Path, required=True)
    parser.add_argument("--ltspice", help="absolute path to LTspice.exe; auto-detected if omitted")
    parser.add_argument("--stop-after-pairing", action="store_true")
    parser.add_argument("--stop-after-12p5", action="store_true")
    parser.add_argument("--skip-matrix", action="store_true")
    parser.add_argument("--skip-dynamic", action="store_true")
    args = parser.parse_args()

    if not MODEL.is_file():
        raise FileNotFoundError(f"TPS61088 macro-model missing: {MODEL}")
    run_root = make_run_root()
    session: dict[str, Any] = {
        "started_local": datetime.now().astimezone().isoformat(),
        "branch_intended": "specialist/tps61088-final-verification",
        "base_commit": "360508c08f23f63cdd74fba7e0c201b0907d3825",
        "model_path": str(MODEL), "model_sha256": sha256(MODEL),
        "raw_50_input": str(args.raw_50.resolve()), "raw_25_input": str(args.raw_25.resolve()),
        "run_root": str(run_root),
        "scope_note": "SPICE and post-processing evidence only; no component or BOM approval is implied.",
    }
    manifest_rows: list[dict[str, Any]] = []
    measurement_rows: list[dict[str, Any]] = []
    write_json(run_root / "session.json", session)

    pairing_out = run_root / "pairing_v2"
    pairing_command = [sys.executable, str(PAIRING_RUNNER), "--raw-50", str(args.raw_50.resolve()),
                       "--raw-25", str(args.raw_25.resolve()), "--out-root", str(pairing_out)]
    pairing = run_logged(pairing_command, REPO_ROOT, run_root, "pairing_v2")
    pairing_report_path = pairing_out / "fsw_internal_pairing_v2_session" / "pairing_v2_execution_report.json"
    session["pairing_v2_exit_code"] = pairing.returncode
    session["pairing_v2_report_path"] = str(pairing_report_path)
    if pairing.returncode != 0 or not pairing_report_path.is_file():
        session["status"] = "BLOCKED_PAIRING_V2_FAILURE"
        session["error"] = "pairing-v2 did not produce a successful, complete report; 12.5 ns and RILIM runs are prohibited"
        write_json(run_root / "session.json", session)
        write_sha256_manifest(run_root)
        return 2

    from gate_and_screen import GateError, decide_12p5, assess_12p5, write_rilim_screen, write_parameter_sweep
    pairing_report = json.loads(pairing_report_path.read_text(encoding="utf-8"))
    try:
        decision = decide_12p5(pairing_report)
    except GateError as exc:
        session["status"] = "BLOCKED_PAIRING_V2_GATE"
        session["error"] = str(exc)
        write_json(run_root / "session.json", session)
        write_sha256_manifest(run_root)
        return 2
    session["pairing_v2_gate"] = decision
    summary25_path = pairing_out / "fsw_internal_probe_25ns_pairing_v2" / "fsw_internal_summary.json"
    session["pairing_v2_25ns_summary"] = str(summary25_path)
    if args.stop_after_pairing:
        session["status"] = "PAIRING_V2_COMPLETE_AWAITING_12P5_OR_MATRIX"
        write_json(run_root / "session.json", session)
        write_sha256_manifest(run_root)
        return 0

    need_12p5 = decision["run_12p5"]
    session["12p5_required_by_gate"] = need_12p5
    if need_12p5:
        ltspice = find_ltspice(args.ltspice)
        session["ltspice_executable"] = str(ltspice)
        deck12 = DIAGNOSTICS / "freq_vin7_rfsw324k_internal_probe_12p5ns.cir"
        row, meas, raw_path, case_dir = run_case(deck12, "FSW_12P5NS", ltspice, run_root)
        manifest_rows.append(row)
        measurement_rows.append(meas)
        if row["status"] != "LTSPICE_EXIT0_RAW_LOG_SAVED" or raw_path is None:
            session["status"] = "BLOCKED_12P5_SPICE_FAILURE"
            session["12p5_case"] = row
            write_csv(run_root / "manifest.csv", manifest_rows)
            write_csv(run_root / "measurements.csv", measurement_rows)
            write_json(run_root / "session.json", session)
            write_sha256_manifest(run_root)
            return 2
        analysis_dir = case_dir / "analysis"
        analyze_command = [sys.executable, str(ANALYZER), "--raw", str(raw_path), "--out", str(analysis_dir),
                           "--max-step-ns", "12.5", "--solver-label", "Gear", "--compare-with", str(summary25_path)]
        analysis = run_logged(analyze_command, REPO_ROOT, case_dir, "analyze_12p5ns")
        summary12_path = analysis_dir / "fsw_internal_summary.json"
        comparison12_path = analysis_dir / "fsw_internal_comparison.json"
        cycles12_path = analysis_dir / "fsw_internal_cycles.csv"
        if analysis.returncode != 0 or not all(p.is_file() for p in (summary12_path, comparison12_path, cycles12_path)):
            session["status"] = "BLOCKED_12P5_ANALYSIS_FAILURE"
            session["analysis_12p5_exit_code"] = analysis.returncode
            write_csv(run_root / "manifest.csv", manifest_rows)
            write_csv(run_root / "measurements.csv", measurement_rows)
            write_json(run_root / "session.json", session)
            write_sha256_manifest(run_root)
            return 2
        audit = assess_12p5(
            json.loads(summary25_path.read_text(encoding="utf-8")),
            json.loads(summary12_path.read_text(encoding="utf-8")),
            json.loads(comparison12_path.read_text(encoding="utf-8")),
            cycles12_path,
        )
        session["12p5_convergence_audit"] = audit
        if not audit["matrix_allowed"]:
            session["status"] = "BLOCKED_12P5_NOT_CONVERGED"
            write_csv(run_root / "manifest.csv", manifest_rows)
            write_csv(run_root / "measurements.csv", measurement_rows)
            write_json(run_root / "session.json", session)
            write_sha256_manifest(run_root)
            return 2
    else:
        session["12p5_convergence_audit"] = {
            "status": "NOT_REQUIRED_BY_50NS_25NS_GATE",
            "matrix_allowed": True,
        }

    if args.stop_after_12p5:
        session["status"] = "FSW_CONVERGENCE_GATE_PASSED_AWAITING_POWER_TESTS"
        write_json(run_root / "session.json", session)
        write_sha256_manifest(run_root)
        return 0

    if args.skip_matrix and args.skip_dynamic:
        session["status"] = "FSW_CONVERGENCE_GATE_PASSED_NO_POWER_CASES_REQUESTED"
        write_json(run_root / "session.json", session)
        write_sha256_manifest(run_root)
        return 0

    ltspice = find_ltspice(args.ltspice)
    session["ltspice_executable"] = str(ltspice)
    planned: list[tuple[Path, str]] = []
    if not args.skip_matrix:
        matrix_dir = run_root / "generated_netlists"
        generated = run_logged([sys.executable, str(MATRIX_GENERATOR), "--out-dir", str(matrix_dir), "--max-step-ns", "25"],
                               REPO_ROOT, run_root, "generate_rilim_matrix")
        if generated.returncode != 0:
            session["status"] = "BLOCKED_RILIM_DECK_GENERATION"
            write_json(run_root / "session.json", session)
            write_sha256_manifest(run_root)
            return 2
        for vin_label in ("7", "9p4"):
            for rilim in (100, 160, 174, 180, 200, 220):
                planned.append((matrix_dir / f"ilim_vin{vin_label}_rilim{rilim}k.cir", "RILIM_MATRIX"))

    if not args.skip_dynamic:
        dynamic_dir = run_root / "generated_diagnostics"
        generated = run_logged([sys.executable, str(DYNAMIC_GENERATOR), "--out-dir", str(dynamic_dir)],
                               REPO_ROOT, run_root, "generate_dynamic_cases")
        if generated.returncode != 0:
            session["status"] = "BLOCKED_DYNAMIC_DECK_GENERATION"
            write_json(run_root / "session.json", session)
            write_sha256_manifest(run_root)
            return 2
        for vin_label in ("7", "7p5", "8", "8p5", "9", "9p4"):
            for rilim in (160, 174):
                planned.append((dynamic_dir / f"dynamic_vin{vin_label}_rilim{rilim}k_vinscan.cir", "VIN_SCAN"))
        for vin_label in ("7", "9p4"):
            for rilim in (160, 174):
                for kind in ("loadstep", "overcurrent", "short"):
                    category = {"loadstep": "DYNAMIC_LOADSTEP", "overcurrent": "DYNAMIC_OVERCURRENT", "short": "DYNAMIC_SHORT"}[kind]
                    planned.append((dynamic_dir / f"dynamic_vin{vin_label}_rilim{rilim}k_{kind}.cir", category))

    session["planned_case_count"] = len(planned)
    any_failed = False
    for deck, category in planned:
        row, meas, raw_path, case_dir = run_case(deck, category, ltspice, run_root)
        manifest_rows.append(row)
        measurement_rows.append(meas)
        if row["status"] != "LTSPICE_EXIT0_RAW_LOG_SAVED":
            any_failed = True
        write_csv(run_root / "manifest.csv", manifest_rows)
        write_csv(run_root / "measurements.csv", measurement_rows)
        session["cases_completed"] = len(manifest_rows)
        session["last_case"] = deck.stem
        write_json(run_root / "session.json", session)

    if not args.skip_matrix:
        write_csv(run_root / "rilim_matrix_results.csv", [r for r in measurement_rows if r.get("category") == "RILIM_MATRIX"])
        write_rilim_screen(run_root / "data" / "rilim_analytical_screen.csv")
        write_parameter_sweep(run_root / "data" / "parameter_sensitivity_5184_rows.csv")
    eol_result = run_logged([sys.executable, str(EOL_SWEEP), "--out", str(run_root / "data" / "eol_efficiency_budget_sensitivity_4s20f.csv")],
                            REPO_ROOT, run_root, "eol_efficiency_budget")
    session["eol_efficiency_sweep_exit_code"] = eol_result.returncode
    if eol_result.returncode != 0:
        any_failed = True

    session["finished_local"] = datetime.now().astimezone().isoformat()
    session["cases_recorded"] = len(manifest_rows)
    session["status"] = "PARTIAL_OR_FAILED_CASES" if any_failed else "SPICE_CASES_COMPLETE_REVIEW_REQUIRED"
    session["important_limit"] = "SPICE/model results do not constitute silicon characterization, inductor approval, or 1.2 s full-system transient proof."
    write_csv(run_root / "manifest.csv", manifest_rows)
    write_csv(run_root / "measurements.csv", measurement_rows)
    write_json(run_root / "session.json", session)
    write_sha256_manifest(run_root)
    print(f"Evidence directory: {run_root}")
    print(f"Status: {session['status']}")
    return 2 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
