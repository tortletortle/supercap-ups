#!/usr/bin/env python3
"""Fail-closed FSW convergence gates and analytical RILIM screening.

This script never runs SPICE. It evaluates pairing-v2 output, audits a completed
12.5 ns run, and emits conservative RILIM and parameter-sensitivity screens.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

PAIRING_OK = "PAIRING_V2_POSTPROCESSING_COMPLETE_EXPECTED_COUNTS"
KEY_TIMING_FIELDS = (
    "period_s",
    "cross_to_u5_toff_0p5V_s",
    "u5_toff_0p5V_to_gate_l_rise_s",
    "gate_l_rise_to_cap_reset_0p5V_s",
    "cross_to_sw_fall_s",
    "cap_reset_to_sw_fall_s",
)


class GateError(ValueError):
    pass


def _finite_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise GateError(f"missing or non-finite numeric field: {label}")
    return float(value)


def _all_true(checks: dict[str, Any]) -> bool:
    return bool(checks) and all(value is True for value in checks.values())


def decide_12p5(pairing_report: dict[str, Any], *, frequency_limit_pct: float = 0.1,
                median_delay_limit_ns: float = 1.0) -> dict[str, Any]:
    """Return whether 12.5 ns is required; fail closed on incomplete evidence."""
    if pairing_report.get("status") != PAIRING_OK:
        raise GateError("pairing-v2 did not finish with the exact expected evidence status")
    if not _all_true(pairing_report.get("checks", {})):
        raise GateError("one or more pairing-v2 integrity checks failed")

    comparison = pairing_report.get("comparison", {})
    if comparison.get("same_electrical_parameters") is not True:
        raise GateError("50 ns and 25 ns electrical parameters are not proven identical")

    frequency_50 = _finite_number(
        pairing_report.get("analysis", {}).get("50ns", {})
        .get("prescribed_frequency_measurement", {}).get("frequency_khz"),
        "analysis.50ns.prescribed_frequency_measurement.frequency_khz",
    )
    frequency_delta = _finite_number(
        comparison.get("frequency_delta_khz"), "comparison.frequency_delta_khz"
    )
    if frequency_50 <= 0:
        raise GateError("50 ns reference frequency must be positive")
    frequency_delta_pct = abs(frequency_delta) / frequency_50 * 100.0

    deltas = comparison.get("distribution_deltas", {})
    observed = {}
    for field in KEY_TIMING_FIELDS:
        item = deltas.get(field)
        if not isinstance(item, dict):
            raise GateError(f"missing timing distribution: {field}")
        if item.get("unit") != "ns":
            raise GateError(f"unexpected timing unit for {field}: {item.get('unit')!r}")
        observed[field] = _finite_number(item.get("median_delta"), f"{field}.median_delta")

    reasons = []
    if frequency_delta_pct > frequency_limit_pct:
        reasons.append(
            f"frequency delta {frequency_delta_pct:.4f}% exceeds {frequency_limit_pct:.4f}%"
        )
    for field, delta in observed.items():
        if abs(delta) > median_delay_limit_ns:
            reasons.append(
                f"{field} median drift {delta:+.4f} ns exceeds {median_delay_limit_ns:.4f} ns"
            )

    return {
        "status": "PASS",
        "run_12p5": bool(reasons),
        "frequency_50_khz": frequency_50,
        "frequency_delta_khz": frequency_delta,
        "frequency_delta_pct": frequency_delta_pct,
        "timing_median_deltas_ns": observed,
        "thresholds": {
            "frequency_delta_pct": frequency_limit_pct,
            "absolute_median_delay_delta_ns": median_delay_limit_ns,
        },
        "reasons": reasons or ["50 ns / 25 ns meet the defined first-stage convergence gate"],
        "matrix_allowed_before_12p5": not bool(reasons),
    }


def assess_12p5(summary_25: dict[str, Any], summary_12p5: dict[str, Any],
                comparison_12p5: dict[str, Any], cycles_csv: Path,
                *, median_delay_limit_ns: float = 0.5,
                frequency_limit_pct: float = 0.05) -> dict[str, Any]:
    """Audit 12.5 ns cycle integrity and convergence against 25 ns."""
    from run_fsw_internal_pairing_v2 import (
        csv_summary_consistency_check,
        event_completeness_check,
        event_multiplicity_check,
        prescribed_frequency_check,
        run_configuration_check,
    )

    checks: dict[str, bool] = {}
    accounting = summary_12p5.get("cycle_accounting", {})
    candidates = int(accounting.get("candidate_cycles", -1))
    valid = int(accounting.get("complete_valid_cycles", -1))
    censored = int(accounting.get("right_censored_cycles", -1))
    invalid = int(accounting.get("invalid_cycles", -1))
    checks["no_invalid_cycles"] = invalid == 0
    checks["cycle_accounting_complete"] = (
        candidates > 0 and valid >= 0 and censored >= 0 and candidates == valid + censored
    )
    checks["at_least_99_5_percent_complete"] = (
        candidates > 0 and (valid / candidates) >= 0.995
    )
    checks["event_completeness"] = event_completeness_check(summary_12p5)[
        "all_required_event_counts_cover_valid_cycles"
    ]
    checks["event_multiplicity"] = event_multiplicity_check(summary_12p5)[
        "required_events_no_missing_or_multiple"
    ]
    checks["csv_summary_consistency"] = csv_summary_consistency_check(
        cycles_csv, summary_12p5
    )["match"]
    checks["run_configuration"] = run_configuration_check(summary_12p5, 12.5)["match"]
    checks["prescribed_frequency"] = prescribed_frequency_check(summary_12p5)["match"]
    checks["same_electrical_parameters"] = (
        comparison_12p5.get("same_electrical_parameters") is True
    )

    frequency_25 = _finite_number(
        summary_25.get("prescribed_edge_measurement", {}).get("frequency_kHz"),
        "summary_25.prescribed_edge_measurement.frequency_kHz",
    )
    frequency_delta = _finite_number(
        comparison_12p5.get("frequency_delta_khz"),
        "comparison_12p5.frequency_delta_khz",
    )
    frequency_delta_pct = abs(frequency_delta) / frequency_25 * 100.0 if frequency_25 else math.inf
    checks["frequency_converged"] = frequency_delta_pct < frequency_limit_pct

    deltas = comparison_12p5.get("distribution_deltas", {})
    timing_deltas = {}
    for field in KEY_TIMING_FIELDS:
        item = deltas.get(field)
        if not isinstance(item, dict) or item.get("unit") != "ns":
            checks[f"timing_{field}"] = False
            timing_deltas[field] = None
            continue
        value = item.get("median_delta")
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            checks[f"timing_{field}"] = False
            timing_deltas[field] = None
            continue
        timing_deltas[field] = float(value)
        checks[f"timing_{field}"] = abs(float(value)) < median_delay_limit_ns

    passed = all(checks.values())
    return {
        "status": "CONVERGED_12P5NS" if passed else "NOT_CONVERGED_NEEDS_6P25NS_OR_REVIEW",
        "matrix_allowed": passed,
        "cycle_accounting": {
            "candidate_cycles": candidates,
            "complete_valid_cycles": valid,
            "right_censored_cycles": censored,
            "invalid_cycles": invalid,
        },
        "frequency_delta_pct": frequency_delta_pct,
        "timing_median_deltas_ns": timing_deltas,
        "thresholds": {
            "frequency_delta_pct": frequency_limit_pct,
            "absolute_median_delay_delta_ns": median_delay_limit_ns,
            "minimum_complete_cycle_fraction": 0.995,
        },
        "checks": checks,
        "next_action": "run RILIM matrix" if passed else "do not run RILIM matrix; investigate and consider 6.25 ns",
    }


def fpwm_limit_typ_a(rilim_ohm: float) -> float:
    if rilim_ohm <= 0:
        raise ValueError("RILIM must be positive")
    return 1_190_000.0 / rilim_ohm - 1.6


def inductor_current_screen(vin_v: float, vout_v: float, iout_a: float,
                            efficiency: float, inductance_h: float,
                            frequency_hz: float) -> dict[str, float]:
    if not (0 < vin_v < vout_v and 0 < efficiency <= 1 and inductance_h > 0 and frequency_hz > 0):
        raise ValueError("invalid boost current-screen inputs")
    i_dc = vout_v * iout_a / (vin_v * efficiency)
    i_pp = 1.0 / (inductance_h * (1.0 / (vout_v - vin_v) + 1.0 / vin_v) * frequency_hz)
    i_peak = i_dc + i_pp / 2.0
    i_rms = math.sqrt(i_dc * i_dc + i_pp * i_pp / 12.0)
    return {"i_dc_a": i_dc, "i_pp_a": i_pp, "i_peak_a": i_peak, "i_rms_a": i_rms}


def build_rilim_screen_rows() -> list[dict[str, Any]]:
    # Engineering screen only. RILIM resistor tolerance is provisionally 1%;
    # TI's 1.3 A reduction is applied to the nominal equation. Stress assumptions:
    # VIN=7/9.4 V, VOUT=12.6 V, IOUT=1 A, eta=75%, Lmin=2.31 uH (-30%), FSW=350 kHz.
    # TI's electrical min/max table does not guarantee the 7-9.4 V input range.
    peak_7 = inductor_current_screen(7.0, 12.6, 1.0, 0.75, 2.31e-6, 350e3)
    peak_94 = inductor_current_screen(9.4, 12.6, 1.0, 0.75, 2.31e-6, 350e3)
    rows = []
    for r_kohm in (100, 160, 174, 180, 200, 220):
        r_ohm = r_kohm * 1000.0
        typical = fpwm_limit_typ_a(r_ohm)
        r_max = r_ohm * 1.01
        r_min = r_ohm * 0.99
        min_screen = fpwm_limit_typ_a(r_max) - 1.3
        resistor_only_upper = fpwm_limit_typ_a(r_min)
        headroom = min_screen - peak_7["i_peak_a"]
        if r_kohm == 100:
            disposition = "HIGH_LIMIT_INDUCTOR_SATURATION_RISK"
        elif headroom > 0:
            disposition = "BEST_OF_TESTED_LOW_MARGIN_NOT_APPROVED"
        else:
            disposition = "INSUFFICIENT_SCREEN_MARGIN"
        rows.append({
            "rilim_kohm": r_kohm,
            "fpwm_typical_limit_a": f"{typical:.6f}",
            "fpwm_min_screen_a": f"{min_screen:.6f}",
            "fpwm_resistor_only_upper_typ_a": f"{resistor_only_upper:.6f}",
            "required_peak_7v_a": f"{peak_7['i_peak_a']:.6f}",
            "required_rms_7v_a": f"{peak_7['i_rms_a']:.6f}",
            "required_peak_9p4v_a": f"{peak_94['i_peak_a']:.6f}",
            "headroom_7v_a": f"{headroom:.6f}",
            "headroom_pct": f"{headroom / peak_7['i_peak_a'] * 100.0:.3f}",
            "disposition": disposition,
            "scope": "analytical screen only; 1% RILIM, 1.3 A TI delta, 75% eta, 350 kHz, Lmin=2.31 uH; not guaranteed or approved",
        })
    return rows


def build_parameter_sweep_rows() -> list[dict[str, Any]]:
    """First-order sensitivity grid; no silicon or magnetic-core model is implied."""
    rows = []
    rilim_values = (100, 160, 174, 180, 200, 220)
    vin_values = (7.0, 7.5, 8.0, 8.5, 9.0, 9.4)
    efficiencies = (0.75, 0.80, 0.85)
    inductance_ratios = (0.70, 0.80, 1.00)
    frequencies = (350e3, 400e3, 441_757.819, 500e3)
    temperatures = (25, 70, 100, 125)
    for vin in vin_values:
        for eta in efficiencies:
            for l_ratio in inductance_ratios:
                for frequency in frequencies:
                    current = inductor_current_screen(
                        vin, 12.6, 1.0, eta, 3.3e-6 * l_ratio, frequency
                    )
                    for temperature in temperatures:
                        dcr_hot = 0.026 * (1.0 + 0.00393 * (temperature - 25.0))
                        p_copper = current["i_rms_a"] ** 2 * dcr_hot
                        for rilim_kohm in rilim_values:
                            r_ohm = rilim_kohm * 1000.0
                            ilim_min_screen = fpwm_limit_typ_a(r_ohm * 1.01) - 1.3
                            headroom = ilim_min_screen - current["i_peak_a"]
                            rows.append({
                                "vin_v": f"{vin:.1f}",
                                "efficiency_assumption": f"{eta:.2f}",
                                "inductance_ratio_to_3p3uH": f"{l_ratio:.2f}",
                                "inductance_uH": f"{3.3 * l_ratio:.4f}",
                                "frequency_khz": f"{frequency / 1e3:.6f}",
                                "temperature_c": temperature,
                                "rilim_kohm": rilim_kohm,
                                "peak_inductor_current_a": f"{current['i_peak_a']:.6f}",
                                "rms_inductor_current_a": f"{current['i_rms_a']:.6f}",
                                "dcr_hot_estimate_ohm": f"{dcr_hot:.6f}",
                                "copper_loss_estimate_w": f"{p_copper:.6f}",
                                "ilim_min_screen_a": f"{ilim_min_screen:.6f}",
                                "headroom_a": f"{headroom:.6f}",
                                "headroom_pct": f"{headroom / current['i_peak_a'] * 100.0:.3f}",
                                "scope": "first-order sensitivity only; copper alpha assumed 0.393%/C; no core loss, thermal feedback, silicon corner, or guaranteed Isat",
                            })
    return rows


def write_parameter_sweep(path: Path) -> None:
    rows = build_parameter_sweep_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_rilim_screen(path: Path) -> None:
    rows = build_rilim_screen_rows()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairing-report", type=Path)
    parser.add_argument("--summary-25", type=Path)
    parser.add_argument("--summary-12p5", type=Path)
    parser.add_argument("--comparison-12p5", type=Path)
    parser.add_argument("--cycles-12p5", type=Path)
    parser.add_argument("--screen-out", type=Path)
    parser.add_argument("--parameter-sweep-out", type=Path)
    parser.add_argument("--decision-out", type=Path)
    args = parser.parse_args()

    report: dict[str, Any] = {}
    if args.pairing_report:
        report = decide_12p5(json.loads(args.pairing_report.read_text(encoding="utf-8")))
    if args.summary_12p5:
        required = (args.summary_25, args.comparison_12p5, args.cycles_12p5)
        if any(item is None for item in required):
            parser.error("12.5 ns audit requires --summary-25, --comparison-12p5, and --cycles-12p5")
        summary25 = json.loads(args.summary_25.read_text(encoding="utf-8"))
        summary12 = json.loads(args.summary_12p5.read_text(encoding="utf-8"))
        comparison12 = json.loads(args.comparison_12p5.read_text(encoding="utf-8"))
        report["12p5_audit"] = assess_12p5(summary25, summary12, comparison12, args.cycles_12p5)
    if args.screen_out:
        write_rilim_screen(args.screen_out)
    if args.parameter_sweep_out:
        write_parameter_sweep(args.parameter_sweep_out)
    if args.decision_out:
        args.decision_out.parent.mkdir(parents=True, exist_ok=True)
        args.decision_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.summary_12p5 and not report.get("12p5_audit", {}).get("matrix_allowed", False):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
