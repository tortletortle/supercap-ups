#!/usr/bin/env python3
"""Audit LTspice low-VIN run folders without treating process success as electrical pass."""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path

FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
REQUIRED_MEASUREMENTS = (
    "vin_avg", "avg_vout", "vmin", "vmax", "ripple", "peak_i",
    "peak_start", "iin_avg", "iout_avg", "pin", "pout", "eff",
    "t_en", "t98", "t98_delay", "sw_t6001", "sw_t6101", "f_sw_khz",
)
PACK_REQUIRED_MEASUREMENTS = (
    "pack_ocv_avg", "pack_terminal_avg", "pack_input_avg",
    "ppack", "pack_esr_loss_w", "path_loss_w", "eff_pack",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_spice_number(token: str) -> float:
    """Parse a basic LTspice number with common engineering suffixes."""
    match = re.fullmatch(rf"\s*({FLOAT})\s*(meg|[tgkmunpf])?\s*", token, re.I)
    if not match:
        raise ValueError(f"unsupported SPICE number: {token!r}")
    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    scale = {
        "": 1.0, "t": 1e12, "g": 1e9, "meg": 1e6,
        "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9,
        "p": 1e-12, "f": 1e-15,
    }[suffix]
    return value * scale


def parse_tran_stop_s(deck_text: str) -> float | None:
    match = re.search(
        rf"(?im)^\s*\.tran\s+\S+\s+({FLOAT}\s*(?:meg|[tgkmunpf])?)",
        deck_text,
    )
    if not match:
        return None
    return parse_spice_number(match.group(1))


def parse_ltspice_log(log_text: str) -> dict:
    measurements: dict[str, float] = {}
    failed: set[str] = set()
    warnings = 0

    for line in log_text.splitlines():
        fail_match = re.search(
            r'Measurement\s+"([^"]+)"\s+FAIL', line, re.IGNORECASE
        )
        if fail_match:
            failed.add(fail_match.group(1).lower())
            continue

        if re.search(r"Emission coefficient,\s*N=", line, re.IGNORECASE):
            warnings += 1

        match = re.match(r"^\s*([A-Za-z_]\w*)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue

        name = match.group(1).lower()
        body = match.group(2)

        # WHEN measurements report their timestamp after AT; the first
        # numeric value in the expression is the threshold, not the time.
        at_match = re.search(rf"\bAT\s+({FLOAT})\b", body, re.IGNORECASE)
        if at_match:
            measurements[name] = float(at_match.group(1))
            continue

        values = re.findall(rf"=\s*({FLOAT})(?=\s|$)", body)
        if values:
            measurements[name] = float(values[-1])

    # A FAIL marker is authoritative even if an earlier duplicate or
    # partial measurement line with the same name appeared in the log.
    for name in failed:
        measurements.pop(name, None)

    elapsed = re.search(
        rf"(?im)^\s*Total elapsed time:\s*({FLOAT})\s*seconds\b",
        log_text,
    )
    fatal_error = bool(re.search(
        r"fatal error|simulation aborted|no convergence",
        log_text, re.IGNORECASE
    ))
    timestep_too_small = bool(re.search(
        r"time step too small", log_text, re.IGNORECASE
    ))

    return {
        "measurements": measurements,
        "failed_measurements": sorted(failed),
        "warning_count": warnings,
        "has_elapsed_record": elapsed is not None,
        "elapsed_seconds": float(elapsed.group(1)) if elapsed else None,
        "fatal_error": fatal_error,
        "timestep_too_small": timestep_too_small,
    }


def _as_int(value: str | int | None, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _ms(measurements: dict, name: str):
    value = measurements.get(name)
    return "" if value is None else value * 1000.0


def analyze_case(row: dict, case_dir: Path, model_path: Path) -> dict:
    case = row["case"]
    log_path = case_dir / f"{case}.log"
    raw_path = case_dir / f"{case}.raw"
    deck_path = case_dir / f"{case}.cir"

    file_checks = {
        "deck": deck_path.is_file(),
        "log": log_path.is_file(),
        "raw": raw_path.is_file(),
        "model": model_path.is_file(),
    }
    expected_hashes = {
        "deck": row.get("input_deck_sha256", ""),
        "log": row.get("log_sha256", ""),
        "raw": row.get("raw_sha256", ""),
        "model": row.get("model_sha256", ""),
    }
    actual_paths = {
        "deck": deck_path, "log": log_path, "raw": raw_path, "model": model_path
    }
    hash_checks = {
        key: bool(
            file_checks[key] and expected
            and sha256_file(actual_paths[key]).lower() == expected.lower()
        )
        for key, expected in expected_hashes.items()
    }

    log = parse_ltspice_log(
        log_path.read_text(encoding="utf-8", errors="replace")
        if log_path.is_file() else ""
    )
    m = log["measurements"]
    required_measurements = set(REQUIRED_MEASUREMENTS)
    if row.get("architecture"):
        required_measurements.update(PACK_REQUIRED_MEASUREMENTS)
    missing = sorted(required_measurements - set(m))
    failed_required = sorted(required_measurements & set(log["failed_measurements"]))

    exit_code = _as_int(row.get("exit_code"))
    process_files_ok = (
        exit_code == 0 and file_checks["log"] and file_checks["raw"]
    )
    simulation_complete = (
        process_files_ok and log["has_elapsed_record"]
        and not log["fatal_error"] and not log["timestep_too_small"]
    )
    hashes_ok = all(hash_checks.values())

    reasons = []
    if not hashes_ok:
        reasons.append("one or more deck/log/raw/model files are missing or their SHA-256 differs from the run manifest")
    if not simulation_complete:
        reasons.append("LTspice process/log/raw completion is not established")
    if log["fatal_error"]:
        reasons.append("fatal error or no-convergence marker")
    if log["timestep_too_small"]:
        reasons.append("time-step-too-small marker")
    if missing:
        reasons.append("missing measurements: " + ", ".join(missing))
    if failed_required:
        reasons.append("failed measurements: " + ", ".join(failed_required))

    stop_s = parse_tran_stop_s(
        deck_path.read_text(encoding="utf-8", errors="replace")
        if deck_path.is_file() else ""
    )
    timing_ok = False
    if all(name in m for name in ("t_en", "t98", "sw_t6001", "sw_t6101")) and stop_s:
        timing_ok = (
            m["t_en"] < m["t98"] < m["sw_t6001"] < m["sw_t6101"] < stop_s
        )
    if not timing_ok:
        reasons.append("required timing order t_en < t98 < sw_t6001 < sw_t6101 < .tran stop is not satisfied")

    electrical_checks = {
        "vout_in_range": "avg_vout" in m and 11.9 <= m["avg_vout"] <= 12.1,
        "iout_in_range": "iout_avg" in m and 0.98 <= m["iout_avg"] <= 1.02,
        "ripple_at_most_100mVpp": "ripple" in m and m["ripple"] <= 0.100,
    }
    electrical_ok = all(electrical_checks.values())
    if not electrical_ok:
        reasons.extend(
            name for name, passed in electrical_checks.items() if not passed
        )

    if not hashes_ok:
        result = "artifact_integrity_failure"
    elif not simulation_complete:
        result = "simulation_incomplete"
    elif missing or failed_required:
        result = "measurement_incomplete"
    elif not timing_ok:
        result = "measurement_timing_invalid"
    elif electrical_ok:
        result = "screen_pass"
    else:
        result = "screen_fail"

    expected_pack_terminal = row.get("expected_pack_terminal_v", "")
    expected_pack_ocv = row.get("expected_pack_ocv_v", "")
    expected_input_current = row.get("expected_input_current_a", "")
    pack_terminal_actual = m.get("pack_terminal_avg", "")
    pack_ocv_actual = m.get("pack_ocv_avg", "")
    pack_terminal_delta = (
        float(pack_terminal_actual) - float(expected_pack_terminal)
        if pack_terminal_actual != "" and expected_pack_terminal != "" else ""
    )
    input_current_delta = (
        float(m["iin_avg"]) - float(expected_input_current)
        if "iin_avg" in m and expected_input_current != "" else ""
    )

    return {
        "case": case,
        "architecture": row.get("architecture", ""),
        "checkpoint_s": row.get("checkpoint_s", ""),
        "vin_source_v": row.get("vin_source_v", ""),
        "expected_pack_ocv_v": expected_pack_ocv,
        "pack_ocv_avg_v": pack_ocv_actual,
        "expected_pack_terminal_v": expected_pack_terminal,
        "pack_terminal_avg_v": pack_terminal_actual,
        "pack_terminal_delta_v": pack_terminal_delta,
        "expected_input_current_a": expected_input_current,
        "input_current_delta_a": input_current_delta,
        "pack_input_avg_v": m.get("pack_input_avg", ""),
        "exit_code": exit_code,
        "simulation_complete": simulation_complete,
        "warning_count": log["warning_count"],
        "failed_measurements": ";".join(log["failed_measurements"]),
        "missing_measurements": ";".join(missing),
        "deck_hash_ok": hash_checks["deck"],
        "log_hash_ok": hash_checks["log"],
        "raw_hash_ok": hash_checks["raw"],
        "model_hash_ok": hash_checks["model"],
        "t_en_ms": _ms(m, "t_en"),
        "t98_ms": _ms(m, "t98"),
        "sw_t6001_ms": _ms(m, "sw_t6001"),
        "sw_t6101_ms": _ms(m, "sw_t6101"),
        "avg_vout_v": m.get("avg_vout", ""),
        "vmin_v": m.get("vmin", ""),
        "vmax_v": m.get("vmax", ""),
        "ripple_mVpp": m.get("ripple", "") * 1000 if "ripple" in m else "",
        "iin_avg_a": m.get("iin_avg", ""),
        "iout_avg_a": m.get("iout_avg", ""),
        "peak_i_a": m.get("peak_i", ""),
        "peak_start_a": m.get("peak_start", ""),
        "pin_w": m.get("pin", ""),
        "pack_pin_w": m.get("ppack", ""),
        "pout_w": m.get("pout", ""),
        "eff_model_pct": m.get("eff", ""),
        "eff_pack_pct": m.get("eff_pack", ""),
        "pack_esr_loss_w": m.get("pack_esr_loss_w", ""),
        "path_loss_w": m.get("path_loss_w", ""),
        "f_sw_khz": m.get("f_sw_khz", ""),
        "timing_order_ok": timing_ok,
        **{f"check_{key}": value for key, value in electrical_checks.items()},
        "screen_result": result,
        "screen_reasons": "; ".join(reasons),
        "ltspice_elapsed_s": log["elapsed_seconds"] or "",
        "stop_time_s": stop_s or "",
    }


def analyze_run_dir(run_dir: Path, model_path: Path) -> list[dict]:
    manifest_path = run_dir / "run_manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing run manifest: {manifest_path}")
    with manifest_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("run_manifest.csv contains no cases")
    return [
        analyze_case(row, run_dir / row["case"], model_path)
        for row in rows
    ]


def write_outputs(run_dir: Path, rows: list[dict]) -> None:
    csv_path = run_dir / "analysis_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# TPS61088 low-VIN LTspice run analysis",
        "",
        "This report audits the collected run artifacts and .meas results. "
        "A screen_pass is only a limited macro-model screening result; it is "
        "not hardware qualification or BOM release.",
        "",
        "| Case | Expected pack terminal | Measured VIN | VOUT avg | IOUT avg | Ripple | Peak IL | FSW observed | Result |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        def fmt(key, digits=3, suffix=""):
            value = row.get(key, "")
            return f"{float(value):.{digits}f}{suffix}" if value != "" else "—"
        case_label = row.get("architecture") or row["case"]
        expected_pack = row.get("expected_pack_terminal_v", "")
        expected_pack_text = f"{float(expected_pack):.3f} V" if expected_pack != "" else "—"
        lines.append(
            f"| {case_label} | {expected_pack_text} | {fmt('vin_avg_v')} V | "
            f"{fmt('avg_vout_v')} V | {fmt('iout_avg_a')} A | "
            f"{fmt('ripple_mVpp')} mVpp | {fmt('peak_start_a')} A | "
            f"{fmt('f_sw_khz', 2)} kHz | {row['screen_result']} |"
        )
    lines.extend([
        "",
        "## Interpretation limits",
        "",
        "- f_sw_khz is reported as observed; this script does not impose an "
        "approved frequency target because the V1.4 RFSW discrepancy remains unresolved.",
        "- eff_model_pct is the macro-model input/output power ratio, not measured hardware efficiency.",
        "- The inductor model contains inductance and DCR only; it cannot establish saturation, core loss, or thermal safety.",
        "- The fixed-VIN cases do not reproduce the supercapacitor's dynamic voltage/ESR trajectory.",
        "- A successful run or screen does not establish the 1.2 s backup requirement.",
        "",
        "## Per-case detail",
        "",
    ])
    for row in rows:
        lines.extend([
            f"### {row['case']}",
            "",
            f"- Result: {row['screen_result']}",
            f"- FSW observed: {fmt_value(row.get('f_sw_khz'), 'kHz')}",
            f"- Model power ratio: {fmt_value(row.get('eff_model_pct'), '%')} (not hardware efficiency)",
            f"- Average input current: {fmt_value(row.get('iin_avg_a'), 'A')}",
            f"- Expected pack terminal: {fmt_value(row.get('expected_pack_terminal_v'), 'V')}",
            f"- Measured pack terminal: {fmt_value(row.get('pack_terminal_avg_v'), 'V')}",
            f"- Pack terminal delta vs behavioral checkpoint: {fmt_value(row.get('pack_terminal_delta_v'), 'V')}",
            f"- Pack ESR loss: {fmt_value(row.get('pack_esr_loss_w'), 'W')}",
            f"- Macro-model efficiency at converter input: {fmt_value(row.get('eff_model_pct'), '%')}",
            f"- Startup peak inductor current: {fmt_value(row.get('peak_start_a'), 'A')}",
            f"- Warnings: {row['warning_count']}",
            f"- Reasons: {row['screen_reasons'] or 'none'}",
            "",
        ])
    (run_dir / "analysis_report.md").write_text("\n".join(lines), encoding="utf-8")


def fmt_value(value, suffix: str) -> str:
    return "not available" if value == "" else f"{float(value):.4f} {suffix}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "sim" / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB",
    )
    args = parser.parse_args()
    rows = analyze_run_dir(args.run_dir, args.model_path)
    write_outputs(args.run_dir, rows)
    for row in rows:
        print(f"{row['case']}: {row['screen_result']}")
    print(f"Wrote analysis_summary.csv and analysis_report.md under {args.run_dir}")


if __name__ == "__main__":
    main()
