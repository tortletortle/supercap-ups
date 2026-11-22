#!/usr/bin/env python3
"""Reproducible constant-power comparison of three supercapacitor packs.

Behavioral storage/ESR model only; this is not a switching-converter simulation.
Python standard library only.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

P_OUT_W = 12.0
PATH_EFFICIENCY = 0.99
TASK_S = 1.2
BOOST_EFFICIENCIES = (0.90, 0.92, 0.94)
DEFAULT_DT_S = 1e-4

DESIGNS = {
    "4S10F_HCC": {
        "n_series": 4,
        "cell_cap_f": 10.0,
        "cell_dc_esr_ohm": 0.065,
        "cell_start_v": 2.35,
        "capacity_tolerance_min": 0.90,
        "life_cap_factor": 0.70,
        "life_esr_factor": 2.0,
        "pack_cutoff_v": 7.0,
    },
    "2S30F_KAM_HP": {
        "n_series": 2,
        "cell_cap_f": 30.0,
        "cell_dc_esr_ohm": 0.044,
        "cell_start_v": 2.40,
        "capacity_tolerance_min": 1.00,
        "life_cap_factor": 0.70,
        "life_esr_factor": 4.0,
        "pack_cutoff_v": 2.7,
    },
    "2S25F_KAM_LR": {
        "n_series": 2,
        "cell_cap_f": 25.0,
        "cell_dc_esr_ohm": 0.025,
        "cell_start_v": 2.40,
        # Public product table does not state this model's capacity tolerance.
        # 1.00 is provisional; the report also runs a -10% sensitivity case.
        "capacity_tolerance_min": 1.00,
        "life_cap_factor": 0.70,
        "life_esr_factor": 4.0,
        "pack_cutoff_v": 2.7,
    },
}


def pack_equivalent(design: dict, cap_factor: float, esr_factor: float) -> tuple[float, float]:
    """Return equivalent series capacitance (F) and pack DC ESR (ohm)."""
    n = design["n_series"]
    c_eq = design["cell_cap_f"] * cap_factor / n
    r_pack = design["cell_dc_esr_ohm"] * esr_factor * n
    return c_eq, r_pack


def solve_state(v_oc_v: float, r_pack_ohm: float, p_cap_w: float):
    """Solve P = I * (Voc - I*R); return (I, Vterminal), or None."""
    discriminant = v_oc_v * v_oc_v - 4.0 * r_pack_ohm * p_cap_w
    if discriminant <= 0.0:
        return None
    current_a = 2.0 * p_cap_w / (v_oc_v + math.sqrt(discriminant))
    terminal_v = v_oc_v - current_a * r_pack_ohm
    return current_a, terminal_v


def simulate(
    design: dict,
    cap_factor: float,
    esr_factor: float,
    boost_efficiency: float,
    dt_s: float = DEFAULT_DT_S,
    p_out_w: float = P_OUT_W,
    path_efficiency: float = PATH_EFFICIENCY,
    task_s: float = TASK_S,
    max_s: float = 30.0,
) -> dict:
    """Integrate ideal-capacitor OCV under a constant-power load."""
    if not 0.0 < boost_efficiency <= 1.0:
        raise ValueError("boost_efficiency must be in (0, 1]")
    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")

    c_eq_f, r_pack_ohm = pack_equivalent(design, cap_factor, esr_factor)
    initial_pack_v = design["n_series"] * design["cell_start_v"]
    v_oc_v = initial_pack_v
    p_cap_w = p_out_w / (boost_efficiency * path_efficiency)
    time_s = 0.0
    esr_loss_j = 0.0
    max_input_current_a = 0.0
    task_state = None
    stop_reason = "time_limit"

    while time_s < max_s:
        state = solve_state(v_oc_v, r_pack_ohm, p_cap_w)
        if state is None:
            stop_reason = "constant_power_limit"
            break

        current_a, terminal_v = state
        if terminal_v <= design["pack_cutoff_v"]:
            stop_reason = "pack_cutoff"
            break

        step_s = dt_s
        if time_s < task_s and time_s + step_s > task_s:
            step_s = task_s - time_s

        esr_loss_j += current_a * current_a * r_pack_ohm * step_s
        v_oc_v -= current_a * step_s / c_eq_f
        time_s += step_s
        max_input_current_a = max(max_input_current_a, current_a)

        if task_state is None and abs(time_s - task_s) < 1e-10:
            after_task = solve_state(v_oc_v, r_pack_ohm, p_cap_w)
            if after_task is not None:
                task_current_a, task_terminal_v = after_task
                task_state = {
                    "v_oc_v": v_oc_v,
                    "v_terminal_v": task_terminal_v,
                    "input_current_a": task_current_a,
                    "esr_loss_j": esr_loss_j,
                }
            else:
                task_state = {
                    "v_oc_v": v_oc_v,
                    "v_terminal_v": None,
                    "input_current_a": None,
                    "esr_loss_j": esr_loss_j,
                }

    end_state = solve_state(v_oc_v, r_pack_ohm, p_cap_w)
    if end_state is None:
        end_current_a = None
        end_terminal_v = None
    else:
        end_current_a, end_terminal_v = end_state

    capacitor_energy_removed_j = 0.5 * c_eq_f * (
        initial_pack_v * initial_pack_v - v_oc_v * v_oc_v
    )
    energy_balance_error_j = capacitor_energy_removed_j - (
        p_cap_w * time_s + esr_loss_j
    )

    return {
        "hold_s": time_s,
        "task_pass": time_s >= task_s - 1e-9,
        "stop_reason": stop_reason,
        "c_eq_f": c_eq_f,
        "r_pack_ohm": r_pack_ohm,
        "initial_pack_v": initial_pack_v,
        "end_ocv_v": v_oc_v,
        "end_terminal_v": end_terminal_v,
        "end_input_current_a": end_current_a,
        "max_input_current_a": max_input_current_a,
        "esr_loss_j": esr_loss_j,
        "task_state": task_state,
        "energy_balance_error_j": energy_balance_error_j,
    }


def minimum_efficiency_for_task(
    design: dict,
    cap_factor: float,
    esr_factor: float,
    task_s: float,
    dt_s: float = 2e-5,
    low: float = 0.50,
    high: float = 0.999,
) -> float:
    """Bisection estimate of minimum fixed Boost efficiency for a task."""
    for _ in range(48):
        middle = (low + high) / 2.0
        result = simulate(
            design, cap_factor, esr_factor, middle, dt_s=dt_s, task_s=task_s
        )
        if result["hold_s"] >= task_s:
            high = middle
        else:
            low = middle
    return high


def build_results() -> list[dict]:
    rows = []
    for design_id, design in DESIGNS.items():
        states = (
            ("nominal", 1.0, 1.0),
            (
                "EOL",
                design["capacity_tolerance_min"] * design["life_cap_factor"],
                design["life_esr_factor"],
            ),
        )
        for state_name, cap_factor, esr_factor in states:
            for eta in BOOST_EFFICIENCIES:
                result = simulate(design, cap_factor, esr_factor, eta)
                task = result["task_state"] or {}
                rows.append({
                    "architecture": design_id,
                    "state": state_name,
                    "boost_efficiency": eta,
                    "Ceq_F": result["c_eq_f"],
                    "Rpack_ohm": result["r_pack_ohm"],
                    "hold_time_s": result["hold_s"],
                    "stop_reason": result["stop_reason"],
                    "pass_1s": result["hold_s"] >= 1.0,
                    "pass_1p2s": result["hold_s"] >= TASK_S,
                    "vterminal_at_1p2s_V": task.get("v_terminal_v", ""),
                    "iin_at_1p2s_A": task.get("input_current_a", ""),
                    "esr_loss_at_1p2s_J": task.get("esr_loss_j", ""),
                    "energy_balance_error_J": result["energy_balance_error_j"],
                })
    return rows


def write_results(path: Path) -> None:
    rows = build_results()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("results.csv"),
        help="CSV output path (default: results.csv beside this script)",
    )
    args = parser.parse_args()
    write_results(args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
