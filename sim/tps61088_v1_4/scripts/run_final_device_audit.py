#!/usr/bin/env python3
"""Run the isolated TPS61088 V1.4 final audit on a Windows LTspice host.

Runs the 12.5 ns FSW convergence deck, the 12-case VIN/RILIM matrix, and
eight diagnostic load-step/output-short cases. Optionally reprocesses the
archived 50/25 ns RAW files first. Every run is isolated under a timestamped
results folder; existing source-folder RAW/LOG files are never overwritten.
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

V14_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = V14_ROOT.parents[1]
DIAGNOSTICS = V14_ROOT / "diagnostics"
NETLISTS = V14_ROOT / "netlists"
RESULTS = V14_ROOT / "results" / "final_device_audit"
MODEL = V14_ROOT.parent / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB"
PAIRING_RUNNER = V14_ROOT / "scripts" / "run_fsw_internal_pairing_v2.py"
ANALYZER = V14_ROOT / "scripts" / "analyze_fsw_internal.py"
DYNAMIC_GENERATOR = V14_ROOT / "scripts" / "generate_dynamic_cases.py"

MEASUREMENT_NAMES = (
    "t90", "t98", "sw_t6001", "sw_t6101", "f_sw_khz",
    "avg_vout", "ripple", "peak_i", "peak_start",
    "iin_avg", "iout_avg", "pin_avg", "pout_avg", "eta_pct",
    "vload_min_step", "vout_min_step", "il_peak_step", "iin_peak_step",
    "vload_recover", "vout_min_short", "il_peak_short",
    "iin_peak_short", "vout_recover",
)
OUTPUT_SUFFIXES = (".raw", ".log", ".op.raw", ".db")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_ltspice(requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"LTspice executable not found: {path}")
        return path

    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if local:
        candidates.append(Path(local) / "Programs" / "ADI" / "LTspice" / "LTspice.exe")
    if program_files:
        candidates.append(Path(program_files) / "ADI" / "LTspice" / "LTspice.exe")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "ADI" / "LTspice" / "LTspice.exe")
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(
        "LTspice.exe was not auto-detected. Pass --ltspice with its absolute path."
    )


def parse_measurements(log_path: Path | None) -> dict[str, str]:
    values = {name: "" for name in MEASUREMENT_NAMES}
    if not log_path or not log_path.is_file():
        return values
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for name in MEASUREMENT_NAMES:
        pattern = (
            rf"(?im)^\s*{re.escape(name)}\s*[:=]\s*"
            r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
        )
        match = re.search(pattern, text)
        if match:
            values[name] = match.group(1)
    return values


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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


def run_case(
    deck: Path,
    category: str,
    ltspice: Path,
    run_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path | None, Path]:
    deck = deck.resolve()
    base = deck.stem
    case_dir = run_root / base
    case_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(deck, case_dir / deck.name)

    source_outputs = {suffix: deck.parent / f"{base}{suffix}" for suffix in OUTPUT_SUFFIXES}
    existing = [str(path) for path in source_outputs.values() if path.exists()]
    base_row: dict[str, Any] = {
        "category": category,
        "case": base,
        "deck_path": str(deck),
        "deck_sha256": sha256(deck),
        "model_sha256": sha256(MODEL) if MODEL.is_file() else "",
        "exit_code": "",
        "status": "",
        "raw_path": "",
        "raw_bytes": 0,
        "raw_sha256": "",
        "log_path": "",
        "log_sha256": "",
        "op_raw_sha256": "",
        "db_sha256": "",
        "error": "",
    }

    if existing:
        base_row["status"] = "BLOCKED_EXISTING_OUTPUTS_NOT_OVERWRITTEN"
        base_row["error"] = "; ".join(existing)
        measurements = {"category": category, "case": base, **parse_measurements(None)}
        return base_row, measurements, None, case_dir

    try:
        completed = subprocess.run(
            [str(ltspice), "-b", deck.name],
            cwd=deck.parent,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        base_row["exit_code"] = completed.returncode
        (case_dir / "ltspice_stdout.log").write_text(
            completed.stdout or "", encoding="utf-8", errors="replace"
        )
        (case_dir / "ltspice_stderr.log").write_text(
            completed.stderr or "", encoding="utf-8", errors="replace"
        )
    except Exception as exc:  # retain the failure in the manifest and continue
        base_row["status"] = "LTSPICE_LAUNCH_ERROR"
        base_row["error"] = f"{type(exc).__name__}: {exc}"
        measurements = {"category": category, "case": base, **parse_measurements(None)}
        return base_row, measurements, None, case_dir

    saved: dict[str, Path] = {}
    for suffix, source in source_outputs.items():
        if source.is_file():
            destination = case_dir / source.name
            shutil.move(str(source), str(destination))
            saved[suffix] = destination

    raw_path = saved.get(".raw")
    log_path = saved.get(".log")
    if completed.returncode == 0 and raw_path and log_path:
        base_row["status"] = "LTSPICE_EXIT0_RAW_LOG_SAVED_REVIEW_MEASUREMENTS"
    else:
        base_row["status"] = "INCOMPLETE_OR_FAILED"

    if raw_path:
        base_row["raw_path"] = str(raw_path)
        base_row["raw_bytes"] = raw_path.stat().st_size
        base_row["raw_sha256"] = sha256(raw_path)
    if log_path:
        base_row["log_path"] = str(log_path)
        base_row["log_sha256"] = sha256(log_path)
    if ".op.raw" in saved:
        base_row["op_raw_sha256"] = sha256(saved[".op.raw"])
    if ".db" in saved:
        base_row["db_sha256"] = sha256(saved[".db"])

    measurements = {"category": category, "case": base, **parse_measurements(log_path)}
    return base_row, measurements, raw_path, case_dir


def run_logged(command: list[str], cwd: Path, out_dir: Path, stem: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, errors="replace", check=False
    )
    (out_dir / f"{stem}.stdout.log").write_text(
        completed.stdout or "", encoding="utf-8", errors="replace"
    )
    (out_dir / f"{stem}.stderr.log").write_text(
        completed.stderr or "", encoding="utf-8", errors="replace"
    )
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ltspice", help="absolute path to LTspice.exe; auto-detected if omitted")
    parser.add_argument("--run-pairing-v2", action="store_true",
                        help="reprocess the archived 50/25 ns RAW files before new LTspice runs")
    parser.add_argument("--raw50", type=Path, help="relocated original 50 ns RAW")
    parser.add_argument("--raw25", type=Path, help="relocated original 25 ns RAW")
    parser.add_argument("--compare-25-summary", type=Path,
                        help="pairing-v2 25 ns summary for the 12.5 ns comparison")
    parser.add_argument("--skip-12p5", action="store_true")
    parser.add_argument("--skip-matrix", action="store_true")
    parser.add_argument("--skip-dynamic", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate/list test decks without invoking LTspice")
    args = parser.parse_args()

    if bool(args.raw50) != bool(args.raw25):
        parser.error("--raw50 and --raw25 must be supplied together")
    if (args.raw50 or args.raw25) and not args.run_pairing_v2:
        parser.error("--raw50/--raw25 require --run-pairing-v2")

    run_root = make_run_root()
    manifest_rows: list[dict[str, Any]] = []
    measurement_rows: list[dict[str, Any]] = []
    session: dict[str, Any] = {
        "started_local": datetime.now().astimezone().isoformat(),
        "repository_root": str(REPO_ROOT),
        "audit_branch_intended": "tps61088-final-device-audit",
        "model_path": str(MODEL),
        "model_sha256": sha256(MODEL) if MODEL.is_file() else "",
        "run_root": str(run_root),
        "note": (
            "Simulation and analysis evidence only. This runner does not approve "
            "RILIM, inductor, efficiency, or BOM."
        ),
    }

    if args.run_pairing_v2:
        pairing_out = run_root / "fsw_pairing_v2"
        command = [
            sys.executable, str(PAIRING_RUNNER), "--out-root", str(pairing_out)
        ]
        if args.raw50:
            command += ["--raw-50", str(args.raw50.expanduser().resolve())]
        if args.raw25:
            command += ["--raw-25", str(args.raw25.expanduser().resolve())]
        result = run_logged(command, REPO_ROOT, run_root, "pairing_v2")
        session["pairing_v2_exit_code"] = result.returncode
        candidate = pairing_out / "fsw_internal_probe_25ns_pairing_v2" / "fsw_internal_summary.json"
        if result.returncode == 0 and candidate.is_file():
            session["pairing_v2_25ns_summary"] = str(candidate)

    compare_summary = args.compare_25_summary
    if compare_summary is None and session.get("pairing_v2_25ns_summary"):
        compare_summary = Path(session["pairing_v2_25ns_summary"])

    planned: list[tuple[Path, str]] = []
    if not args.skip_12p5:
        planned.append((
            DIAGNOSTICS / "freq_vin7_rfsw324k_internal_probe_12p5ns.cir",
            "FSW_12p5ns",
        ))
    if not args.skip_matrix:
        for vin_label in ("7", "9p4"):
            for rilim in (100, 160, 174, 180, 200, 220):
                planned.append((
                    NETLISTS / f"ilim_vin{vin_label}_rilim{rilim}k.cir",
                    "RILIM_MATRIX",
                ))

    if not args.skip_dynamic:
        generated = run_logged(
            [sys.executable, str(DYNAMIC_GENERATOR), "--force"],
            REPO_ROOT, run_root, "generate_dynamic_cases",
        )
        session["dynamic_generator_exit_code"] = generated.returncode
        if generated.returncode != 0:
            session["dynamic_generator_error"] = generated.stderr
        else:
            for vin_label in ("7", "9p4"):
                for rilim in (160, 174):
                    for kind in ("loadstep", "short"):
                        planned.append((
                            DIAGNOSTICS / f"dynamic_vin{vin_label}_rilim{rilim}k_{kind}.cir",
                            f"DYNAMIC_{kind.upper()}",
                        ))

    if args.dry_run:
        print(f"Dry run: {len(planned)} LTspice decks would be executed.")
        for deck, category in planned:
            print(f"{category}: {deck}")
        session["dry_run"] = True
        session["planned_case_count"] = len(planned)
        (run_root / "session.json").write_text(
            json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return 0

    ltspice = find_ltspice(args.ltspice)
    session["ltspice_executable"] = str(ltspice)
    try:
        version = subprocess.run(
            [str(ltspice), "-?"], capture_output=True, text=True, errors="replace", timeout=15
        )
        session["ltspice_version_probe"] = (version.stdout + version.stderr)[:2000]
    except Exception as exc:
        session["ltspice_version_probe_error"] = f"{type(exc).__name__}: {exc}"

    for deck, category in planned:
        if not deck.is_file():
            manifest_rows.append({
                "category": category, "case": deck.stem, "deck_path": str(deck),
                "status": "BLOCKED_MISSING_DECK", "error": "deck file not found",
            })
            measurement_rows.append({
                "category": category, "case": deck.stem, **parse_measurements(None)
            })
        else:
            manifest, measurements, raw_path, case_dir = run_case(
                deck, category, ltspice, run_root
            )
            manifest_rows.append(manifest)
            measurement_rows.append(measurements)

            if category == "FSW_12p5ns" and raw_path:
                analysis_out = case_dir / "analysis"
                command = [
                    sys.executable, str(ANALYZER),
                    "--raw", str(raw_path),
                    "--out", str(analysis_out),
                    "--max-step-ns", "12.5",
                    "--solver-label", "Gear",
                ]
                if compare_summary and compare_summary.is_file():
                    command += ["--compare-with", str(compare_summary.resolve())]
                analysis = run_logged(command, REPO_ROOT, case_dir, "analyze_12p5ns")
                session["fsw_12p5_analysis_exit_code"] = analysis.returncode
                session["fsw_12p5_analysis_stdout"] = str(case_dir / "analyze_12p5ns.stdout.log")
                session["fsw_12p5_analysis_stderr"] = str(case_dir / "analyze_12p5ns.stderr.log")

        write_csv(run_root / "manifest.csv", manifest_rows)
        write_csv(run_root / "measurements.csv", measurement_rows)
        (run_root / "session.json").write_text(
            json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    session["finished_local"] = datetime.now().astimezone().isoformat()
    session["cases_recorded"] = len(manifest_rows)
    session["run_root"] = str(run_root)
    (run_root / "session.json").write_text(
        json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"TPS61088 final audit runner finished: {len(manifest_rows)} cases recorded.")
    print(f"Evidence directory: {run_root}")
    print("Review manifest.csv and measurements.csv; preserve all RAW, LOG, OP.RAW and DB files.")
    print("No RILIM, inductor, efficiency, or BOM approval is implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
