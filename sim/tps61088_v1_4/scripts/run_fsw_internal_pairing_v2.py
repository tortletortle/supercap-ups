"""Run the read-only FSW pairing-v2 analysis on the archived 50/25 ns RAW files.

The script never launches LTspice and never edits a circuit. It verifies the
archived RAW files against the SHA-256 inventory, runs the existing unit tests,
runs the analyzer into new non-overwriting output directories, and records a
machine-readable execution report.
"""
import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path


V14_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = V14_ROOT.parents[1]
INVENTORY = V14_ROOT / "results" / "fsw_internal_probe_session" / "native_files_local_inventory.csv"
ANALYZER = V14_ROOT / "scripts" / "analyze_fsw_internal.py"
TEST_ROOT = V14_ROOT / "tests"

EXPECTED = {
    50: {
        "bytes": 555189092,
        "sha256": "b817d10d13cfc83027764796eafcf4e3bb8b0b05fbb420c68879417f051bc719",
        "candidate_cycles": 884,
        "complete_valid_cycles": 883,
        "right_censored_cycles": 1,
        "invalid_cycles": 0,
    },
    25: {
        "bytes": 654022700,
        "sha256": "2d5b2ddbb5a9c27a25322143a426741cfbe1e01623c9ceeb9b7940481ab7e552",
        "candidate_cycles": 883,
        "complete_valid_cycles": 882,
        "right_censored_cycles": 1,
        "invalid_cycles": 0,
    },
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_inventory_rows(path=INVENTORY):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    by_step = {}
    for row in rows:
        step_value = float(row["max_step_ns"])
        if step_value not in (50.0, 25.0):
            continue
        step = int(step_value)

        # The inventory also records .db, .log and .op.raw sidecars.
        # Only the main transient RAW is an analyzer input.
        normalized_path = row["path"].replace("\\", "/").rstrip("/")
        basename = normalized_path.rsplit("/", 1)[-1].lower()
        if not basename.endswith(".raw") or basename.endswith(".op.raw"):
            continue

        if step in by_step:
            raise ValueError(f"Duplicate primary {step} ns RAW entry in inventory")
        by_step[step] = row
    missing = sorted(set((50, 25)) - set(by_step))
    if missing:
        raise ValueError(f"RAW inventory is missing max-step entries: {missing}")
    return by_step


def resolve_and_verify_raw(step, inventory_row, override=None):
    path = Path(override) if override is not None else Path(inventory_row["path"])
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"{step} ns RAW not found: {path}\n"
            "Use --raw-50 or --raw-25 if the file was moved."
        )

    expected = EXPECTED[step]
    inventory_size = int(inventory_row["bytes"])
    inventory_hash = inventory_row["sha256"].strip().lower()
    if inventory_size != expected["bytes"] or inventory_hash != expected["sha256"]:
        raise ValueError(
            f"{step} ns inventory entry no longer matches the audited baseline: "
            f"bytes={inventory_size}, sha256={inventory_hash}"
        )

    actual_size = path.stat().st_size
    if actual_size != expected["bytes"]:
        raise ValueError(
            f"{step} ns RAW size mismatch: expected {expected['bytes']}, got {actual_size}"
        )
    actual_hash = sha256_file(path)
    if actual_hash != expected["sha256"]:
        raise ValueError(
            f"{step} ns RAW SHA-256 mismatch: expected {expected['sha256']}, got {actual_hash}"
        )
    return path, actual_hash


def run_logged(command, cwd, stdout_path, stderr_path):
    with Path(stdout_path).open("w", encoding="utf-8") as stdout, \
            Path(stderr_path).open("w", encoding="utf-8") as stderr:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd),
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    return result.returncode


def cycle_accounting_check(summary, step):
    observed = {
        key: int(summary.get("cycle_accounting", {}).get(key, -1))
        for key in (
            "candidate_cycles",
            "complete_valid_cycles",
            "right_censored_cycles",
            "invalid_cycles",
        )
    }
    expected = {
        key: EXPECTED[step][key]
        for key in (
            "candidate_cycles",
            "complete_valid_cycles",
            "right_censored_cycles",
            "invalid_cycles",
        )
    }
    return {"observed": observed, "expected": expected, "match": observed == expected}


def event_completeness_check(summary):
    valid = int(summary.get("cycle_accounting", {}).get("complete_valid_cycles", 0))
    counts = summary.get("event_completeness", {})
    required = (
        "pvin_cross_s",
        "u5_toff_0p5V_rise_s",
        "gate_l_rise_s",
        "cap_reset_0p5V_fall_s",
        "sw_fall_10V_s",
    )
    observed = {key: int(counts.get(key, -1)) for key in required}
    diagnostic_only = {
        "comparator_output_rise_s": int(counts.get("comparator_output_rise_s", -1))
    }
    return {
        "valid_cycle_count": valid,
        "required_event_counts": observed,
        "diagnostic_only_event_counts": diagnostic_only,
        "all_required_event_counts_cover_valid_cycles": all(
            value >= valid for value in observed.values()
        ),
    }


def event_multiplicity_check(summary):
    counts = summary.get("event_multiplicity", {})
    required = (
        "pvin_cross",
        "u5_toff_0p5V_rise",
        "gate_l_rise",
        "cap_reset_0p5V_fall",
        "sw_fall_10V",
    )
    observed = {}
    for name in required:
        item = counts.get(name, {})
        observed[name] = {
            "missing_cycles": int(item.get("missing_cycles", -1)),
            "multiple_cycles": int(item.get("multiple_cycles", -1)),
        }
    diagnostic_item = counts.get("comparator_output_rise", {})
    diagnostic_only = {
        "comparator_output_rise": {
            "missing_cycles": int(diagnostic_item.get("missing_cycles", -1)),
            "multiple_cycles": int(diagnostic_item.get("multiple_cycles", -1)),
            "hard_gate": False,
        }
    }
    clean = all(
        item["missing_cycles"] == 0 and item["multiple_cycles"] == 0
        for item in observed.values()
    )
    return {
        "required_event_counts": observed,
        "diagnostic_only": diagnostic_only,
        "required_events_no_missing_or_multiple": clean,
    }


CSV_EVENT_FIELDS = {
    "pvin_cross": ("pvin_cross_count", "pvin_cross_s"),
    "comparator_output_rise": (
        "comparator_output_rise_count", "comparator_output_rise_s"
    ),
    "u5_toff_0p5V_rise": (
        "u5_toff_0p5V_rise_count", "u5_toff_0p5V_rise_s"
    ),
    "gate_l_rise": ("gate_l_rise_count", "gate_l_rise_s"),
    "cap_reset_0p5V_fall": (
        "cap_reset_0p5V_fall_count", "cap_reset_0p5V_fall_s"
    ),
    "sw_fall_10V": ("sw_fall_10V_count", "sw_fall_10V_s"),
}
REQUIRED_CSV_EVENT_NAMES = frozenset(CSV_EVENT_FIELDS) - {
    "comparator_output_rise"
}


def csv_summary_consistency_check(csv_path, summary):
    """Independently recompute row accounting and event totals from the CSV."""
    try:
        with Path(csv_path).open("r", newline="", encoding="utf-8-sig") as stream:
            rows = list(csv.DictReader(stream))

        def number(value):
            return None if value in (None, "") else float(value)

        def integer(value):
            return int(value)

        def boolean(value):
            if value == "True":
                return True
            if value == "False":
                return False
            raise ValueError(f"invalid CSV boolean: {value!r}")

        statuses = [row["cycle_status"] for row in rows]
        valid_flags = [boolean(row["cycle_valid"]) for row in rows]
        order_flags = [boolean(row["event_order_valid"]) for row in rows]
        accounting = {
            "candidate_cycles": len(rows),
            "complete_valid_cycles": sum(valid_flags),
            "right_censored_cycles": statuses.count("right_censored_at_raw_end"),
            "invalid_cycles": statuses.count("invalid"),
        }
        summary_accounting = summary.get("cycle_accounting", {})
        accounting_match = all(
            int(summary_accounting.get(key, -1)) == value
            for key, value in accounting.items()
        )

        completeness = {
            time_field: sum(number(row[time_field]) is not None for row in rows)
            for _, time_field in CSV_EVENT_FIELDS.values()
        }
        summary_completeness = summary.get("event_completeness", {})
        completeness_match = summary_completeness == completeness

        complete_rows = [
            row for row in rows if number(row["next_cycle_start_s"]) is not None
        ]
        multiplicity = {
            name: {
                "missing_cycles": sum(
                    integer(row[count_field]) == 0 for row in complete_rows
                ),
                "multiple_cycles": sum(
                    integer(row[count_field]) > 1 for row in complete_rows
                ),
            }
            for name, (count_field, _) in CSV_EVENT_FIELDS.items()
        }
        summary_multiplicity = summary.get("event_multiplicity", {})
        multiplicity_match = summary_multiplicity == multiplicity

        cycle_valid_matches_status = True
        complete_rows_have_one_primary_event_each = True
        event_times_match_counts = True
        event_times_in_half_open_period = True
        event_order_matches_timestamps = True
        period_matches_boundaries = True
        sw_high_matches_boundaries = True
        allowed_statuses = {"complete", "invalid", "right_censored_at_raw_end"}

        for row, is_valid, order_valid in zip(rows, valid_flags, order_flags):
            status = row["cycle_status"]
            if status not in allowed_statuses:
                cycle_valid_matches_status = False
            if is_valid != (status == "complete" and order_valid):
                cycle_valid_matches_status = False

            start = number(row["cycle_start_s"])
            end = number(row["next_cycle_start_s"])
            period = number(row["period_s"])
            sw_fall = number(row["sw_fall_10V_s"])
            sw_high = number(row["sw_high_s"])

            if start is None:
                period_matches_boundaries = False
                continue
            if end is None:
                if status != "right_censored_at_raw_end" or period is not None:
                    period_matches_boundaries = False
            else:
                if status == "right_censored_at_raw_end" or period is None:
                    period_matches_boundaries = False
                elif not math.isclose(
                    period, end - start, rel_tol=1e-9, abs_tol=1e-15
                ):
                    period_matches_boundaries = False

            if sw_fall is None:
                if sw_high is not None:
                    sw_high_matches_boundaries = False
            elif sw_high is None or not math.isclose(
                sw_high, sw_fall - start, rel_tol=1e-9, abs_tol=1e-15
            ):
                sw_high_matches_boundaries = False

            primary_times = {}
            for name, (count_field, time_field) in CSV_EVENT_FIELDS.items():
                count = integer(row[count_field])
                event_time = number(row[time_field])
                if count < 0 or ((count == 0) != (event_time is None)):
                    event_times_match_counts = False
                if name in REQUIRED_CSV_EVENT_NAMES:
                    if status == "complete" and count != 1:
                        complete_rows_have_one_primary_event_each = False
                    if status == "complete" and (
                        event_time is None or end is None
                        or not (start <= event_time < end)
                    ):
                        event_times_in_half_open_period = False
                    if event_time is not None:
                        primary_times[name] = event_time

            if status == "complete":
                if integer(row["raw_10v_rises_in_period"]) != 1:
                    complete_rows_have_one_primary_event_each = False
                if not order_valid:
                    event_order_matches_timestamps = False

            ordered_names = (
                "pvin_cross",
                "u5_toff_0p5V_rise",
                "gate_l_rise",
                "cap_reset_0p5V_fall",
                "sw_fall_10V",
            )
            ordered_values = [primary_times.get(name) for name in ordered_names]
            timestamps_present = all(value is not None for value in ordered_values)
            timestamp_order_valid = (
                timestamps_present
                and all(
                    ordered_values[i] <= ordered_values[i + 1] + 1e-15
                    for i in range(len(ordered_values) - 1)
                )
            )
            if order_valid != timestamp_order_valid:
                event_order_matches_timestamps = False
            if status == "complete" and not timestamp_order_valid:
                event_order_matches_timestamps = False

        checks = {
            "csv_cycle_accounting_matches_summary": accounting_match,
            "csv_event_completeness_matches_summary": completeness_match,
            "csv_event_multiplicity_matches_summary": multiplicity_match,
            "cycle_valid_flags_match_status": cycle_valid_matches_status,
            "complete_cycles_have_one_primary_event_each": (
                complete_rows_have_one_primary_event_each
            ),
            "event_times_match_event_counts": event_times_match_counts,
            "primary_event_times_are_inside_half_open_cycle": (
                event_times_in_half_open_period
            ),
            "primary_event_order_matches_timestamps": event_order_matches_timestamps,
            "period_matches_cycle_boundaries": period_matches_boundaries,
            "sw_high_matches_cycle_boundaries": sw_high_matches_boundaries,
        }
        return {
            "csv_path": str(Path(csv_path)),
            "csv_row_count": len(rows),
            "recomputed_cycle_accounting": accounting,
            "recomputed_event_completeness": completeness,
            "recomputed_event_multiplicity": multiplicity,
            "checks": checks,
            "match": all(checks.values()),
        }
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return {
            "csv_path": str(Path(csv_path)),
            "match": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_configuration_check(summary, step):
    parameters = summary.get("run_parameters", {})
    observed = {
        "max_step_ns": parameters.get("max_step_ns"),
        "solver_label": parameters.get("solver_label"),
        "rfsw_ohm": parameters.get("rfsw_ohm"),
        "cfsw_f": parameters.get("cfsw_f"),
        "roff_ohm": parameters.get("roff_ohm"),
        "analysis_window_s": summary.get("analysis_window_s"),
    }
    expected = {
        "max_step_ns": float(step),
        "solver_label": "Gear",
        "rfsw_ohm": 324000.0,
        "cfsw_f": 23e-12,
        "roff_ohm": 1e6,
        "analysis_window_s": [0.024, 0.026],
    }
    return {"observed": observed, "expected": expected, "match": observed == expected}


def prescribed_frequency_check(summary):
    measurement = summary.get("prescribed_edge_measurement", {})
    frequency = measurement.get("frequency_kHz")
    valid_frequency = (
        isinstance(frequency, (int, float))
        and math.isfinite(frequency)
        and frequency > 0
    )
    return {
        "timing_valid": measurement.get("timing_valid") is True,
        "frequency_khz": frequency,
        "finite_positive_frequency": bool(valid_frequency),
        "match": measurement.get("timing_valid") is True and bool(valid_frequency),
    }


def comparison_extract(comparison):
    deltas = comparison.get("distribution_deltas", {})
    wanted = (
        "period_s",
        "cross_to_u5_toff_0p5V_s",
        "u5_toff_0p5V_to_gate_l_rise_s",
        "gate_l_rise_to_cap_reset_0p5V_s",
        "cross_to_sw_fall_s",
        "cap_reset_to_sw_fall_s",
    )
    extracted = {}
    for field in wanted:
        value = deltas.get(field)
        if value is not None:
            extracted[field] = value
    return {
        "same_electrical_parameters": comparison.get("same_electrical_parameters"),
        "frequency_delta_khz": comparison.get("frequency_delta_khz"),
        "distribution_deltas": extracted,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-50", type=Path, default=None,
                        help="optional relocated 50 ns RAW; must match the archived SHA-256")
    parser.add_argument("--raw-25", type=Path, default=None,
                        help="optional relocated 25 ns RAW; must match the archived SHA-256")
    parser.add_argument("--out-root", type=Path, default=V14_ROOT / "results",
                        help="output root; existing pairing-v2 directories are never overwritten")
    return parser.parse_args()


def main():
    args = parse_args()
    inventory = load_inventory_rows()
    raw50, hash50 = resolve_and_verify_raw(50, inventory[50], args.raw_50)
    raw25, hash25 = resolve_and_verify_raw(25, inventory[25], args.raw_25)

    out_root = args.out_root.expanduser().resolve()
    session_dir = out_root / "fsw_internal_pairing_v2_session"
    out50 = out_root / "fsw_internal_probe_50ns_pairing_v2"
    out25 = out_root / "fsw_internal_probe_25ns_pairing_v2"
    targets = (session_dir, out50, out25)
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite prior evidence. Existing paths:\n"
            + "\n".join(existing)
            + "\nChoose a new --out-root to preserve all previous runs."
        )

    session_dir.mkdir(parents=True, exist_ok=False)
    test_stdout = session_dir / "unit_tests.stdout.log"
    test_stderr = session_dir / "unit_tests.stderr.log"
    test_command = [
        sys.executable, "-m", "unittest", "discover",
        "-s", str(TEST_ROOT), "-v",
    ]
    test_rc = run_logged(test_command, REPO_ROOT, test_stdout, test_stderr)
    if test_rc != 0:
        report = {
            "status": "BLOCKED_UNIT_TEST_FAILURE",
            "unit_tests_return_code": test_rc,
            "unit_tests_stdout": str(test_stdout),
            "unit_tests_stderr": str(test_stderr),
        }
        (session_dir / "pairing_v2_execution_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        raise SystemExit(2)

    log50_out = session_dir / "analysis_50ns.stdout.log"
    log50_err = session_dir / "analysis_50ns.stderr.log"
    cmd50 = [
        sys.executable, str(ANALYZER), "--raw", str(raw50),
        "--out", str(out50), "--max-step-ns", "50", "--solver-label", "Gear",
    ]
    rc50 = run_logged(cmd50, REPO_ROOT, log50_out, log50_err)
    if rc50 != 0:
        raise RuntimeError(
            f"50 ns pairing-v2 analysis failed with exit code {rc50}; "
            f"inspect {log50_err} and {log50_out}"
        )

    summary50_path = out50 / "fsw_internal_summary.json"
    if not summary50_path.is_file():
        raise FileNotFoundError(f"50 ns analyzer did not create {summary50_path}")

    log25_out = session_dir / "analysis_25ns.stdout.log"
    log25_err = session_dir / "analysis_25ns.stderr.log"
    cmd25 = [
        sys.executable, str(ANALYZER), "--raw", str(raw25),
        "--out", str(out25), "--max-step-ns", "25", "--solver-label", "Gear",
        "--compare-with", str(summary50_path),
    ]
    rc25 = run_logged(cmd25, REPO_ROOT, log25_out, log25_err)
    if rc25 != 0:
        raise RuntimeError(
            f"25 ns pairing-v2 analysis failed with exit code {rc25}; "
            f"inspect {log25_err} and {log25_out}"
        )

    summary25_path = out25 / "fsw_internal_summary.json"
    comparison_path = out25 / "fsw_internal_comparison.json"
    for required_path in (summary25_path, comparison_path):
        if not required_path.is_file():
            raise FileNotFoundError(f"25 ns analyzer did not create {required_path}")

    summary50 = json.loads(summary50_path.read_text(encoding="utf-8"))
    summary25 = json.loads(summary25_path.read_text(encoding="utf-8"))
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    csv50_path = out50 / "fsw_internal_cycles.csv"
    csv25_path = out25 / "fsw_internal_cycles.csv"
    csv_audit50 = csv_summary_consistency_check(csv50_path, summary50)
    csv_audit25 = csv_summary_consistency_check(csv25_path, summary25)

    accounting50 = cycle_accounting_check(summary50, 50)
    accounting25 = cycle_accounting_check(summary25, 25)
    events50 = event_completeness_check(summary50)
    events25 = event_completeness_check(summary25)
    multiplicity50 = event_multiplicity_check(summary50)
    multiplicity25 = event_multiplicity_check(summary25)
    config50 = run_configuration_check(summary50, 50)
    config25 = run_configuration_check(summary25, 25)
    frequency50 = prescribed_frequency_check(summary50)
    frequency25 = prescribed_frequency_check(summary25)
    same_parameters = comparison.get("same_electrical_parameters") is True

    checks = {
        "unit_tests_passed": test_rc == 0,
        "raw_50ns_hash_verified": hash50 == EXPECTED[50]["sha256"],
        "raw_25ns_hash_verified": hash25 == EXPECTED[25]["sha256"],
        "50ns_expected_cycle_accounting": accounting50["match"],
        "25ns_expected_cycle_accounting": accounting25["match"],
        "50ns_event_completeness": events50["all_required_event_counts_cover_valid_cycles"],
        "25ns_event_completeness": events25["all_required_event_counts_cover_valid_cycles"],
        "50ns_no_missing_or_multiple_events": multiplicity50["required_events_no_missing_or_multiple"],
        "25ns_no_missing_or_multiple_events": multiplicity25["required_events_no_missing_or_multiple"],
        "50ns_csv_summary_consistency": csv_audit50["match"],
        "25ns_csv_summary_consistency": csv_audit25["match"],
        "50ns_run_configuration": config50["match"],
        "25ns_run_configuration": config25["match"],
        "50ns_prescribed_frequency_measurement": frequency50["match"],
        "25ns_prescribed_frequency_measurement": frequency25["match"],
        "same_electrical_parameters": same_parameters,
    }
    all_checks = all(checks.values())

    report = {
        "status": (
            "PAIRING_V2_POSTPROCESSING_COMPLETE_EXPECTED_COUNTS"
            if all_checks else "PAIRING_V2_POSTPROCESSING_COMPLETE_REQUIRES_REVIEW"
        ),
        "important_limit": (
            "This report validates read-only post-processing and event accounting. "
            "It does not prove solver convergence, identify a unique frequency-error "
            "root cause, or approve RFSW/RILIM/BOM changes."
        ),
        "raw_inputs": {
            "50ns": {
                "path": str(raw50),
                "bytes": raw50.stat().st_size,
                "sha256": hash50,
            },
            "25ns": {
                "path": str(raw25),
                "bytes": raw25.stat().st_size,
                "sha256": hash25,
            },
        },
        "unit_tests": {
            "return_code": test_rc,
            "stdout_log": str(test_stdout),
            "stderr_log": str(test_stderr),
        },
        "analysis": {
            "50ns": {
                "summary": str(summary50_path),
                "analysis_status": summary50.get("analysis_status"),
                "cycle_accounting": accounting50,
                "event_completeness": events50,
                "event_multiplicity": multiplicity50,
                "csv_consistency_audit": csv_audit50,
                "run_configuration": config50,
                "prescribed_frequency_measurement": frequency50,
            },
            "25ns": {
                "summary": str(summary25_path),
                "cycle_accounting": accounting25,
                "event_completeness": events25,
                "event_multiplicity": multiplicity25,
                "csv_consistency_audit": csv_audit25,
                "run_configuration": config25,
                "prescribed_frequency_measurement": frequency25,
                "analysis_status": summary25.get("analysis_status"),
            },
        },
        "comparison": {
            "path": str(comparison_path),
            **comparison_extract(comparison),
        },
        "checks": checks,
        "logs": {
            "50ns_stdout": str(log50_out),
            "50ns_stderr": str(log50_err),
            "25ns_stdout": str(log25_out),
            "25ns_stderr": str(log25_err),
        },
    }

    report_path = session_dir / "pairing_v2_execution_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not all_checks:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
