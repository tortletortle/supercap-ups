#!/usr/bin/env python3
"""Integrate 2S supercapacitor hold-up using a measured LTspice efficiency map.

The map is a TPS61088 macro-model calibration, not hardware efficiency data.
No extrapolation is permitted outside the seven validated fixed-VIN points.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
from pathlib import Path
from typing import Iterable
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
from compare_storage_architectures import DESIGNS, pack_equivalent  # noqa: E402

P_OUT_W = 12.0
TASK_S = 1.2
DEFAULT_DT_S = 1e-4
MAX_SIMULATION_S = 5.0
PATH_RESISTANCE_OHM = 0.002
EXPECTED_CASES = (
    "tps61088_vin_2p8v",
    "tps61088_vin_3p0v",
    "tps61088_vin_3p2v",
    "tps61088_vin_3p6v",
    "tps61088_vin_4p0v",
    "tps61088_vin_4p4v",
    "tps61088_vin_4p8v",
)
CANDIDATE_DESIGNS = (
    "2S30F_KAM_HP_44",
    "2S30F_KAM_HP_40",
    "2S25F_KAM_LR",
)


class EfficiencyMapError(ValueError):
    """The requested operating point is outside validated map coverage."""


class InsufficientPowerError(RuntimeError):
    """The calibrated converter map cannot deliver the requested load power."""


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EfficiencyMap:
    """Piecewise-linear efficiency and steady peak-current map vs converter VIN."""

    def __init__(self, points: Iterable[dict]):
        self.points = sorted(
            (
                {
                    "case": str(point["case"]),
                    "vin_v": float(point["vin_v"]),
                    "efficiency": float(point["efficiency"]),
                    "peak_i_a": float(point["peak_i_a"]),
                }
                for point in points
            ),
            key=lambda point: point["vin_v"],
        )
        if len(self.points) < 2:
            raise ValueError("at least two validated efficiency-map points are required")
        for point in self.points:
            if not math.isfinite(point["vin_v"]):
                raise ValueError("map VIN values must be finite")
            if not 0.0 < point["efficiency"] <= 1.0:
                raise ValueError(
                    f"efficiency must be in (0, 1] for {point['case']}"
                )
            if not math.isfinite(point["peak_i_a"]) or point["peak_i_a"] <= 0.0:
                raise ValueError(
                    f"steady peak inductor current must be positive for {point['case']}"
                )
        for left, right in zip(self.points, self.points[1:]):
            if right["vin_v"] - left["vin_v"] <= 1e-6:
                raise ValueError("efficiency-map VIN points must be unique")

    @property
    def min_vin_v(self) -> float:
        return self.points[0]["vin_v"]

    @property
    def max_vin_v(self) -> float:
        return self.points[-1]["vin_v"]

    def _interpolate(self, vin_v: float, field: str) -> float:
        if vin_v < self.min_vin_v - 1e-9 or vin_v > self.max_vin_v + 1e-9:
            raise EfficiencyMapError(
                f"VIN {vin_v:.4f} V is outside calibrated range "
                f"{self.min_vin_v:.4f}–{self.max_vin_v:.4f} V"
            )
        if vin_v <= self.min_vin_v:
            return self.points[0][field]
        if vin_v >= self.max_vin_v:
            return self.points[-1][field]
        for left, right in zip(self.points, self.points[1:]):
            if left["vin_v"] <= vin_v <= right["vin_v"]:
                fraction = (
                    (vin_v - left["vin_v"])
                    / (right["vin_v"] - left["vin_v"])
                )
                return left[field] + fraction * (right[field] - left[field])
        raise AssertionError("interpolation interval not found")

    def efficiency_at(self, vin_v: float) -> float:
        return self._interpolate(vin_v, "efficiency")

    def peak_current_at(self, vin_v: float) -> float:
        return self._interpolate(vin_v, "peak_i_a")


def load_efficiency_map(csv_path: Path) -> tuple[EfficiencyMap, dict]:
    """Load only the complete seven-point, hash-verified fixed-VIN test matrix."""
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    by_case = {row.get("case", ""): row for row in rows}
    missing_cases = [case for case in EXPECTED_CASES if case not in by_case]
    if missing_cases:
        raise ValueError(
            "fixed-VIN calibration matrix is incomplete; missing: "
            + ", ".join(missing_cases)
        )

    points = []
    rejected = []
    for case in EXPECTED_CASES:
        row = by_case[case]
        if row.get("screen_result") != "screen_pass":
            rejected.append(f"{case}: {row.get('screen_result', 'missing result')}")
            continue
        point_rejected = False
        for field in (
            "simulation_complete", "timing_order_ok",
            "deck_hash_ok", "log_hash_ok", "raw_hash_ok", "model_hash_ok",
        ):
            if not _truthy(row.get(field, "")):
                rejected.append(f"{case}: {field} is not true")
                point_rejected = True
        if point_rejected:
            continue

        try:
            vin = float(row["vin_avg_v"])
            efficiency = float(row["eff_model_pct"]) / 100.0
            peak_i = float(row["peak_i_a"])
            vout = float(row["avg_vout_v"])
            iout = float(row["iout_avg_a"])
            ripple = float(row["ripple_mVpp"])
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append(f"{case}: missing or invalid numeric result ({exc})")
            continue

        if not (11.9 <= vout <= 12.1 and 0.98 <= iout <= 1.02 and ripple <= 100.0):
            rejected.append(f"{case}: output voltage/current/ripple screen failed")
            continue
        if not (0.0 < efficiency <= 1.0):
            rejected.append(f"{case}: macro-model efficiency outside (0, 100%]")
            continue
        points.append({
            "case": case,
            "vin_v": vin,
            "efficiency": efficiency,
            "peak_i_a": peak_i,
        })

    if rejected:
        raise ValueError(
            "efficiency map refused; every calibration point must pass with "
            "matching evidence hashes:\n- " + "\n- ".join(rejected)
        )
    if len(points) != len(EXPECTED_CASES):
        raise ValueError("efficiency map requires all seven validated fixed-VIN points")

    efficiency_map = EfficiencyMap(points)
    metadata = {
        "source_csv": str(csv_path),
        "source_csv_sha256": sha256_file(csv_path),
        "point_count": len(points),
        "min_vin_v": efficiency_map.min_vin_v,
        "max_vin_v": efficiency_map.max_vin_v,
    }
    return efficiency_map, metadata


def _solve_midpoint_current(
    voc_start_v: float,
    dt_s: float,
    c_eq_f: float,
    r_total_ohm: float,
    efficiency_map: EfficiencyMap,
    p_out_w: float,
    scan_steps: int = 256,
) -> dict:
    """Find the lower-current operating root at the integration midpoint."""
    denominator = r_total_ohm + dt_s / (2.0 * c_eq_f)
    if denominator <= 0.0:
        raise ValueError("total series resistance and midpoint denominator must be positive")

    current_min = max(0.0, (voc_start_v - efficiency_map.max_vin_v) / denominator)
    map_limited_current = (voc_start_v - efficiency_map.min_vin_v) / denominator
    max_power_current = voc_start_v / (2.0 * denominator)
    current_max = min(map_limited_current, max_power_current)
    if current_max <= current_min or current_max <= 0.0:
        raise EfficiencyMapError(
            f"no high-voltage operating branch inside calibrated VIN range "
            f"at OCV={voc_start_v:.4f} V"
        )

    def evaluate(current_a: float) -> tuple[float, float, float, float]:
        vin_mid_v = voc_start_v - current_a * denominator
        efficiency = efficiency_map.efficiency_at(vin_mid_v)
        peak_i = efficiency_map.peak_current_at(vin_mid_v)
        return (
            current_a * vin_mid_v * efficiency - p_out_w,
            vin_mid_v,
            efficiency,
            peak_i,
        )

    low_i = current_min
    low_f, _, _, _ = evaluate(low_i)
    if low_f >= 0.0:
        raise EfficiencyMapError(
            "the load operating root lies above the maximum calibrated VIN"
        )

    previous_i = low_i
    bracket = None
    for index in range(1, scan_steps + 1):
        current_i = current_min + (
            (current_max - current_min) * index / scan_steps
        )
        current_f, _, _, _ = evaluate(current_i)
        if current_f >= 0.0:
            bracket = (previous_i, current_i)
            break
        previous_i = current_i

    if bracket is None:
        if map_limited_current < max_power_current * (1.0 - 1e-8):
            raise EfficiencyMapError(
                "required operating point would fall below the minimum "
                "calibrated VIN"
            )
        raise InsufficientPowerError(
            f"calibrated converter map cannot deliver {p_out_w:.3f} W "
            f"at OCV={voc_start_v:.4f} V"
        )

    low_i, high_i = bracket
    for _ in range(56):
        mid_i = (low_i + high_i) / 2.0
        mid_f, _, _, _ = evaluate(mid_i)
        if mid_f >= 0.0:
            high_i = mid_i
        else:
            low_i = mid_i

    current_a = (low_i + high_i) / 2.0
    _, vin_mid_v, efficiency, peak_i = evaluate(current_a)
    return {
        "current_a": current_a,
        "vin_mid_v": vin_mid_v,
        "efficiency": efficiency,
        "peak_i_a": peak_i,
    }


def simulate_calibrated_hold_up(
    design: dict,
    efficiency_map: EfficiencyMap,
    cap_factor: float,
    esr_factor: float,
    task_s: float = TASK_S,
    dt_s: float = DEFAULT_DT_S,
    max_s: float = MAX_SIMULATION_S,
    p_out_w: float = P_OUT_W,
    path_resistance_ohm: float = PATH_RESISTANCE_OHM,
) -> dict:
    """Integrate capacitor OCV using a midpoint, voltage-dependent converter map."""
    if dt_s <= 0.0 or task_s <= 0.0 or max_s <= 0.0:
        raise ValueError("dt_s, task_s, and max_s must be positive")
    if path_resistance_ohm < 0.0:
        raise ValueError("path resistance must be non-negative")

    c_eq_f, r_pack_ohm = pack_equivalent(design, cap_factor, esr_factor)
    r_total = r_pack_ohm + path_resistance_ohm
    initial_voc_v = design["n_series"] * design["cell_start_v"]
    voc_v = initial_voc_v
    time_s = 0.0
    task_state = None
    stop_reason = "maximum_simulation_time"
    min_vin_v = math.inf
    max_input_current_a = 0.0
    max_peak_inductor_current_a = 0.0
    converter_input_energy_j = 0.0
    output_energy_j = 0.0
    pack_esr_loss_j = 0.0
    path_loss_j = 0.0
    max_efficiency = 0.0
    min_efficiency = 1.0

    while time_s < max_s - 1e-12:
        step_s = min(dt_s, max_s - time_s)
        if time_s < task_s < time_s + step_s:
            step_s = task_s - time_s

        try:
            op = _solve_midpoint_current(
                voc_v, step_s, c_eq_f, r_total, efficiency_map, p_out_w
            )
        except EfficiencyMapError:
            stop_reason = "efficiency_map_out_of_range"
            break
        except InsufficientPowerError:
            stop_reason = "insufficient_converter_power"
            break

        current_a = op["current_a"]
        vin_mid_v = op["vin_mid_v"]
        if vin_mid_v <= design["pack_cutoff_v"]:
            stop_reason = "converter_input_cutoff"
            break

        next_voc_v = voc_v - current_a * step_s / c_eq_f
        if next_voc_v <= 0.0:
            stop_reason = "capacitor_voltage_nonphysical"
            break

        midpoint_voc_v = (voc_v + next_voc_v) / 2.0
        midpoint_converter_vin_v = midpoint_voc_v - current_a * r_total
        converter_input_power_w = midpoint_converter_vin_v * current_a
        output_power_w = converter_input_power_w * op["efficiency"]

        converter_input_energy_j += converter_input_power_w * step_s
        output_energy_j += output_power_w * step_s
        pack_esr_loss_j += current_a * current_a * r_pack_ohm * step_s
        path_loss_j += current_a * current_a * path_resistance_ohm * step_s

        min_vin_v = min(min_vin_v, midpoint_converter_vin_v)
        max_input_current_a = max(max_input_current_a, current_a)
        max_peak_inductor_current_a = max(
            max_peak_inductor_current_a, op["peak_i_a"]
        )
        max_efficiency = max(max_efficiency, op["efficiency"])
        min_efficiency = min(min_efficiency, op["efficiency"])

        voc_v = next_voc_v
        time_s += step_s

        if task_state is None and abs(time_s - task_s) < 1e-9:
            try:
                endpoint = _solve_midpoint_current(
                    voc_v, 0.0, c_eq_f, r_total, efficiency_map, p_out_w
                )
                endpoint_vin = endpoint["vin_mid_v"]
                if endpoint_vin <= design["pack_cutoff_v"]:
                    task_state = {"passed": False, "reason": "converter_input_cutoff"}
                else:
                    task_state = {
                        "passed": True,
                        "reason": "operating_point_available",
                        "ocv_v": voc_v,
                        "converter_vin_v": endpoint_vin,
                        "pack_terminal_v": voc_v - endpoint["current_a"] * r_pack_ohm,
                        "input_current_a": endpoint["current_a"],
                        "efficiency_pct": endpoint["efficiency"] * 100.0,
                        "steady_peak_inductor_current_a": endpoint["peak_i_a"],
                    }
            except EfficiencyMapError:
                task_state = {
                    "passed": False,
                    "reason": "efficiency_map_out_of_range",
                }
            except InsufficientPowerError:
                task_state = {
                    "passed": False,
                    "reason": "insufficient_converter_power",
                }

    if task_state is None and time_s >= task_s - 1e-9:
        task_state = {"passed": False, "reason": "task_endpoint_not_verified"}

    capacitor_energy_removed_j = 0.5 * c_eq_f * (
        initial_voc_v * initial_voc_v - voc_v * voc_v
    )
    energy_balance_error_j = capacitor_energy_removed_j - (
        converter_input_energy_j + pack_esr_loss_j + path_loss_j
    )

    endpoint_current = ""
    endpoint_vin = ""
    endpoint_pack_terminal = ""
    if time_s > 0.0:
        try:
            endpoint = _solve_midpoint_current(
                voc_v, 0.0, c_eq_f, r_total, efficiency_map, p_out_w
            )
            endpoint_current = endpoint["current_a"]
            endpoint_vin = endpoint["vin_mid_v"]
            endpoint_pack_terminal = voc_v - endpoint_current * r_pack_ohm
        except (EfficiencyMapError, InsufficientPowerError):
            pass

    return {
        "design": design.get("name", ""),
        "hold_verified_s": time_s,
        "task_s": task_s,
        "task_pass": bool(task_state and task_state.get("passed")),
        "task_endpoint_reason": task_state.get("reason", "") if task_state else "",
        "stop_reason": stop_reason,
        "initial_ocv_v": initial_voc_v,
        "end_ocv_v": voc_v,
        "end_pack_terminal_v": endpoint_pack_terminal,
        "end_converter_vin_v": endpoint_vin,
        "end_input_current_a": endpoint_current,
        "min_converter_vin_v": min_vin_v if math.isfinite(min_vin_v) else "",
        "max_input_current_a": max_input_current_a,
        "max_steady_peak_inductor_current_a": max_peak_inductor_current_a,
        "min_map_efficiency_pct": min_efficiency * 100.0 if time_s else "",
        "max_map_efficiency_pct": max_efficiency * 100.0 if time_s else "",
        "converter_input_energy_j": converter_input_energy_j,
        "output_energy_j": output_energy_j,
        "pack_esr_loss_j": pack_esr_loss_j,
        "path_loss_j": path_loss_j,
        "capacitor_energy_removed_j": capacitor_energy_removed_j,
        "energy_balance_error_j": energy_balance_error_j,
        "c_eq_f": c_eq_f,
        "r_pack_ohm": r_pack_ohm,
        "path_resistance_ohm": path_resistance_ohm,
    }


def build_candidate_results(
    efficiency_map: EfficiencyMap,
    task_s: float = TASK_S,
    dt_s: float = DEFAULT_DT_S,
) -> list[dict]:
    results = []
    for design_id in CANDIDATE_DESIGNS:
        design = dict(DESIGNS[design_id])
        design["name"] = design_id
        results.append(simulate_calibrated_hold_up(
            design=design,
            efficiency_map=efficiency_map,
            cap_factor=design["capacity_tolerance_min"] * design["life_cap_factor"],
            esr_factor=design["life_esr_factor"],
            task_s=task_s,
            dt_s=dt_s,
        ))
    return results


def write_outputs(output_dir: Path, results: list[dict], metadata: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "calibrated_hold_up_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(results[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(results)

    lines = [
        "# TPS61088 macro-model-calibrated 2S hold-up estimate",
        "",
        f"- Source analysis CSV: {metadata['source_csv']}",
        f"- Source analysis SHA-256: {metadata['source_csv_sha256']}",
        f"- Validated map points: {metadata['point_count']}",
        f"- Calibrated VIN range: {metadata['min_vin_v']:.4f}–{metadata['max_vin_v']:.4f} V",
        f"- Output load: {P_OUT_W:.3f} W",
        f"- Required task: {TASK_S:.3f} s",
        f"- Input path resistance: {PATH_RESISTANCE_OHM * 1000:.3f} mΩ",
        "",
        "| Candidate | Verified duration in map | 1.2 s task | End OCV | End VIN | Max IIN | Max steady peak IL | Stop reason |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in results:
        def fmt(key: str, digits: int = 3) -> str:
            value = row.get(key, "")
            return f"{float(value):.{digits}f}" if value != "" else "—"
        lines.append(
            f"| {row['design']} | {fmt('hold_verified_s')} s | "
            f"{'PASS' if row['task_pass'] else 'NOT VERIFIED'} | "
            f"{fmt('end_ocv_v')} V | {fmt('end_converter_vin_v')} V | "
            f"{fmt('max_input_current_a')} A | "
            f"{fmt('max_steady_peak_inductor_current_a')} A | "
            f"{row['stop_reason']} |"
        )
    lines.extend([
        "",
        "## Evidence and model limits",
        "",
        "- Efficiency is interpolated only between the seven passing fixed-VIN LTspice macro-model points; extrapolation is rejected.",
        "- A 1.2 s PASS means the calibrated behavioral model can find a valid 12 W operating point through the endpoint. It is not a continuous switching-level simulation.",
        "- This model includes the pack EOL DC ESR and a 2 mΩ series input path. It does not include wiring inductance, fuse resistance, connector resistance, PCB parasitics, capacitor frequency-dependent ESR, thermal drift, or cell imbalance.",
        "- The reported steady peak inductor current is interpolated from fixed-VIN measurements; it is not the transient peak during the 1.2 s event.",
        "- Macro-model efficiency is not hardware efficiency. Hardware qualification and BOM release remain blocked on measured prototype evidence.",
        "- hold_verified_s is the time integrated inside the calibrated map. If the run stops at efficiency_map_out_of_range, it is not a prediction of the true physical cutoff time.",
        "",
        "## Per-candidate detail",
        "",
    ])
    for row in results:
        lines.extend([
            f"### {row['design']}",
            "",
            f"- Task endpoint: {row['task_endpoint_reason'] or 'not reached'}",
            f"- Stop reason: {row['stop_reason']}",
            f"- Pack ESR loss: {fmt_value(row.get('pack_esr_loss_j'), 'J')}",
            f"- Input path loss: {fmt_value(row.get('path_loss_j'), 'J')}",
            f"- Converter input energy: {fmt_value(row.get('converter_input_energy_j'), 'J')}",
            f"- Output energy: {fmt_value(row.get('output_energy_j'), 'J')}",
            f"- Capacitor energy removed: {fmt_value(row.get('capacitor_energy_removed_j'), 'J')}",
            f"- Energy balance residual: {fmt_value(row.get('energy_balance_error_j'), 'J')}",
            "",
        ])
    (output_dir / "calibrated_hold_up_report.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def fmt_value(value: object, suffix: str) -> str:
    return "not available" if value == "" else f"{float(value):.6f} {suffix}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="defaults to the directory containing --analysis-csv",
    )
    parser.add_argument("--task-s", type=float, default=TASK_S)
    parser.add_argument("--dt-s", type=float, default=DEFAULT_DT_S)
    args = parser.parse_args()

    efficiency_map, metadata = load_efficiency_map(args.analysis_csv)
    results = build_candidate_results(
        efficiency_map, task_s=args.task_s, dt_s=args.dt_s
    )
    output_dir = args.output_dir or args.analysis_csv.parent
    write_outputs(output_dir, results, metadata)
    for row in results:
        print(
            f"{row['design']}: {'PASS' if row['task_pass'] else 'NOT VERIFIED'} "
            f"({row['hold_verified_s']:.4f}s, {row['stop_reason']})"
        )
    print(
        "Wrote calibrated_hold_up_summary.csv and "
        f"calibrated_hold_up_report.md to {output_dir}"
    )


if __name__ == "__main__":
    main()
