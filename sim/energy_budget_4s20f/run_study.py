#!/usr/bin/env python3
"""Generate reproducible 4Sx20F energy-budget scans, checkpoints and waveforms."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from dataclasses import replace
from pathlib import Path

from model import Scenario, analytic_general, analytic_hold_time, output_operating_point, simulate


BASE = Scenario(name="baseline")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def flatten_waveform_row(row: dict) -> dict:
    result = {k: v for k, v in row.items() if k != "cell_terminal_v"}
    for i, value in enumerate(row["cell_terminal_v"], 1):
        result[f"cell{i}_terminal_v"] = value
    return result


def bisection(fn, lo: float, hi: float, *, decreasing: bool, target: float = 1.2) -> float:
    flo, fhi = fn(lo), fn(hi)
    if (flo - target) * (fhi - target) > 0:
        raise ValueError(f"critical boundary not bracketed: {flo}, {fhi}")
    for _ in range(72):
        mid = (lo + hi) / 2.0
        value = fn(mid)
        if decreasing:
            if value >= target:
                lo = mid
            else:
                hi = mid
        else:
            if value >= target:
                hi = mid
            else:
                lo = mid
    return (lo + hi) / 2.0


def analytic(**kwargs) -> float:
    return analytic_hold_time(replace(BASE, **kwargs))["hold_s"]


def state_at_1p2s(s: Scenario) -> dict:
    checkpoint = replace(s, name=s.name + "_1p2s_checkpoint", max_time_s=1.2, record_interval_s=1.2)
    return simulate(checkpoint)["end_state"]


def make_summary() -> dict:
    baseline = simulate(BASE)
    failure = simulate(replace(
        BASE, name="joint_degradation",
        cell_caps_f=(10.8,) * 4, cell_esrs_ohm=(0.110,) * 4,
        boost_efficiency=0.83, input_path_ohm=0.120,
    ))
    alternate = simulate(replace(
        BASE, name="alternate_1p144457",
        boost_efficiency=0.83, input_path_ohm=0.150,
    ))
    weak = simulate(replace(
        BASE, name="weak_cell_cuv",
        initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
    ))
    weak_delay = simulate(replace(
        BASE, name="weak_cell_4p06ms_delay",
        initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
        cell_uv_delay_s=0.00406,
    ))
    joint_weak = simulate(replace(
        BASE, name="joint_degradation_plus_weak_cell",
        cell_caps_f=(10.8,) * 4, cell_esrs_ohm=(0.110,) * 4,
        initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
        boost_efficiency=0.83, input_path_ohm=0.120,
    ))
    mismatch = simulate(replace(
        BASE, name="one_cell_8pct_low_capacity",
        cell_caps_f=(11.2 / 1.08, 11.2, 11.2, 11.2),
    ))
    checkpoint = state_at_1p2s(BASE)

    fixed_12v_1a = replace(BASE, name="boost_12v_fixed_1a", load_mode="boost_fixed_12v_1a")
    fixed_12v_12w = replace(BASE, name="boost_12v_constant_power_12w", load_mode="boost_fixed_12v_constant_power")
    fixed_12v_1a_result = simulate(fixed_12v_1a)
    fixed_12v_12w_result = simulate(fixed_12v_12w)

    return {
        "metadata": {
            "model": "4S Eaton HVH1230-2R7206-R averaged constant-power per-cell model",
            "baseline_commit": "360508c08f23f63cdd74fba7e0c201b0907d3825",
            "branch": "energy-budget-4s20f-reconciliation",
            "target_hold_s": 1.2,
            "clock_start": "9.0 V rested pack OCV begins supplying the Boost input",
            "clock_end": "first of VIN_BOOST=7.0 V, PACK_4S loaded voltage=7.110123 V, cell terminal CUV=1.05 V, or hard minimum=1.0 V",
            "evidence_class": "averaged behavioral model; not switching-level continuous simulation or hardware validation",
        },
        "baseline": {
            "hold_s": baseline["hold_s"],
            "margin_ms_vs_1p2s": (baseline["hold_s"] - 1.2) * 1000,
            "stop_reason": baseline["stop_reason"],
            "max_input_current_a": baseline["max_input_current_a"],
            "minimum_cell_terminal_v": baseline["minimum_cell_terminal_v"],
            "minimum_load_voltage_v": baseline["minimum_load_voltage_v"],
            "minimum_boost_input_v": baseline["minimum_boost_input_v"],
            "minimum_pack_terminal_v": baseline["minimum_pack_terminal_v"],
            "energy_balance_residual_j": baseline["energy_balance_residual_j"],
            "energies_j": baseline["energies_j"],
        },
        "known_joint_failure": {
            "cell_capacitance_f": 10.8,
            "cell_esr_ohm": 0.110,
            "boost_efficiency": 0.83,
            "input_path_ohm": 0.120,
            "output_path_ohm": 0.145,
            "hold_s": failure["hold_s"],
            "margin_ms_vs_1p2s": (failure["hold_s"] - 1.2) * 1000,
            "stop_reason": failure["stop_reason"],
        },
        "alternate_1p144457": {
            "cell_capacitance_f": 11.2,
            "cell_esr_ohm": 0.106,
            "boost_efficiency": 0.83,
            "input_path_ohm": 0.150,
            "output_path_ohm": 0.145,
            "hold_s": alternate["hold_s"],
            "stop_reason": alternate["stop_reason"],
            "interpretation": "different parameter combination from the 10.8 F / 110 mOhm / 120 mOhm joint-failure case",
        },
        "weak_cell_cuv": {
            "initial_cell_voltages_v": [1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667],
            "cell_cuv_v": 1.05,
            "threshold_crossing_s": weak["threshold_crossing_time_s"],
            "physical_isolation_s_with_zero_delay": weak["physical_isolation_time_s"],
            "stop_reason": weak["stop_reason"],
            "vin_boost_at_cuv_v": weak["end_state"]["vin_boost_v"],
            "pack_terminal_at_cuv_v": weak["end_state"]["pack_terminal_v"],
        },
        "weak_cell_protection_latency_sensitivity": {
            "assumed_delay_s": 0.00406,
            "threshold_crossing_s": weak_delay["threshold_crossing_time_s"],
            "physical_isolation_s": weak_delay["physical_isolation_time_s"],
            "minimum_cell_terminal_v_during_delay": weak_delay["minimum_cell_terminal_v"],
            "delay_basis": "historical model assumption only; not a guaranteed or measured maximum",
        },
        "joint_degradation_plus_weak_cell": {
            "hold_s": joint_weak["hold_s"],
            "stop_reason": joint_weak["stop_reason"],
            "margin_ms_vs_1p2s": (joint_weak["hold_s"] - 1.2) * 1000,
        },
        "capacity_mismatch_8pct": {
            "cell_capacitances_f": [11.2 / 1.08, 11.2, 11.2, 11.2],
            "hold_s": mismatch["hold_s"],
            "stop_reason": mismatch["stop_reason"],
            "minimum_cell_terminal_v": mismatch["minimum_cell_terminal_v"],
        },
        "baseline_1p2s_checkpoint": {
            "vin_boost_v": checkpoint["vin_boost_v"],
            "pack_terminal_v": checkpoint["pack_terminal_v"],
            "input_current_a": checkpoint["input_current_a"],
            "minimum_cell_terminal_v": checkpoint["min_cell_terminal_v"],
            "load_voltage_v": checkpoint["load_voltage_v"],
            "load_power_w": checkpoint["load_power_w"],
        },
        "load_voltage_scenarios": {
            "historical_12v_1a_at_load": {
                **output_operating_point(BASE),
                "hold_s": baseline["hold_s"],
                "interpretation": "requires Boost output setpoint 12.145 V to compensate 145 mOhm at 1 A",
            },
            "12v_boost_setpoint_1a": {
                **output_operating_point(fixed_12v_1a),
                "hold_s": fixed_12v_1a_result["hold_s"],
                "interpretation": "load receives 11.855 V and 11.855 W; not 12 W",
            },
            "12v_boost_setpoint_12w_constant_power": {
                **output_operating_point(fixed_12v_12w),
                "hold_s": fixed_12v_12w_result["hold_s"],
                "interpretation": "load receives 12 W at about 11.8532 V and 1.0124 A; voltage acceptance is unknown",
            },
        },
        "eaton_datasheet_basis": {
            "part_number": "HVH1230-2R7206-R",
            "rated_capacitance_f": 20.0,
            "initial_tolerance": "-20%/+20%",
            "life_capacitance_floor": ">=70% of rated under stated tests",
            "modeled_eol_cell_capacitance_f": 11.2,
            "maximum_dc_esr_25c_ohm": 0.053,
            "modeled_cell_esr_ohm": 0.106,
            "esr_assumption_warning": "2x 25 C maximum DC ESR is a stress assumption, not an Eaton guaranteed EOL DC ESR or DC ESR(T) curve",
            "continuous_current_a_at_15c_rise": 1.92,
            "pulse_current_a_1s_test": 13.0,
            "temperature": "-40 to +70 C standard; +85 C extended with cell voltage linearly derated to 2.5 V",
            "source": "https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hvh-supercapacitors-cylindrical-cells-high-density-data-sheet-elx1538-en.pdf",
        },
        "boost_evidence": {
            "device": "TPS61088",
            "datasheet_input_range_v": [2.7, 12.0],
            "project_energy_model_floor_v": 7.0,
            "floor_warning": "7.0 V is the project's qualified/evidence cutoff, not the IC's datasheet UVLO minimum",
            "available_device_model_evidence": "repository V1.3 macro-model 18 ms windows at 7.0-9.4 V; reported 98.889-99.364% window efficiency",
            "efficiency_warning": "short-window macro-model efficiency is not continuous 1.2 s or hardware efficiency; 85% remains a conservative scenario, not a measured guarantee",
        },
        "timing_and_limitations": [
            "The historical energy clock starts when the rested 9.0 V pack begins supplying the Boost input.",
            "The real load clock must start when LOAD_12V first receives valid backup power after MUX transfer; the allowed load voltage window is not specified.",
            "The model ends on the first of Boost VIN floor, pack UVLO, cell CUV, or hard cell minimum; protection propagation delay is separate and unverified.",
            "No continuous 1.2 s switching-level TPS61088 simulation or bench discharge has been demonstrated.",
            "Eaton does not provide a guaranteed full-temperature DC ESR curve in ELX1538; temperature multipliers are sensitivity assumptions only.",
            "The 145 mOhm output path is a model budget; the actual load-side capacitor position, ESR, and effective capacitance are not confirmed.",
        ],
    }


def generate_scans(out: Path) -> None:
    scans = out / "scans"
    scans.mkdir(parents=True, exist_ok=True)

    single = []
    values = {
        "cell_capacity_f": [8.0, 8.5, 9.0, 9.5, 9.776, 10.0, 10.8, 11.2, 12.0, 14.0],
        "cell_esr_mohm": [80, 90, 100, 106, 110, 115, 119.743, 120, 125, 140, 160],
        "boost_efficiency_pct": [75, 78, 80, 80.121, 82, 83, 85, 88, 90, 95],
        "input_path_mohm": [50, 75, 100, 120, 150, 154.973, 160, 180, 200, 250],
        "output_path_mohm": [0, 50, 100, 145, 200, 300, 500, 884.582, 1000],
        "initial_pack_ocv_v": [8.5, 8.7, 8.8, 8.888632, 8.9, 9.0, 9.1, 9.2, 9.4],
    }
    for parameter, sequence in values.items():
        for value in sequence:
            kw = {}
            if parameter == "cell_capacity_f":
                kw["cell_caps_f"] = (value,) * 4
            elif parameter == "cell_esr_mohm":
                kw["cell_esrs_ohm"] = (value / 1000.0,) * 4
            elif parameter == "boost_efficiency_pct":
                kw["boost_efficiency"] = value / 100.0
            elif parameter == "input_path_mohm":
                kw["input_path_ohm"] = value / 1000.0
            elif parameter == "output_path_mohm":
                kw["output_path_ohm"] = value / 1000.0
            else:
                kw["initial_cells_v"] = (value / 4.0,) * 4
            hold = analytic(**kw)
            single.append({
                "parameter": parameter, "value": value, "hold_s": hold,
                "pass_1p2s": hold >= 1.2, "margin_ms": (hold - 1.2) * 1000,
                "basis": "one-variable change from the 4Sx20F baseline",
            })
    write_csv(scans / "single_parameter_scan.csv", single)

    temperature = []
    for temp in (-40, -20, 25, 50, 70, 85):
        for multiplier in (1.0, 1.05, 1.10, 1.12965, 1.15, 1.25, 1.50, 2.0):
            hold = analytic(cell_esrs_ohm=(0.106 * multiplier,) * 4)
            temperature.append({
                "ambient_C": temp,
                "assumed_esr_multiplier_vs_106mohm": multiplier,
                "cell_dc_esr_mohm": 106.0 * multiplier,
                "hold_s": hold,
                "pass_1p2s": hold >= 1.2,
                "eaton_dc_esr_temperature_curve": "not specified",
                "status": "sensitivity assumption; not a temperature-to-ESR vendor mapping",
                "initial_cell_voltage_2p25V_within_85C_2p5V_limit": True,
            })
    write_csv(scans / "temperature_esr_sensitivity.csv", temperature)

    mismatch = []
    for ratio in (1.0, 1.05, 1.08, 1.12, 1.2, 1.3, 1.4, 1.5, 1.58, 1.6, 2.0):
        caps = (11.2 / ratio, 11.2, 11.2, 11.2)
        hold = analytic_general(caps, (0.106,) * 4, (2.25,) * 4, BASE)
        p_in = output_operating_point(BASE)["boost_output_power_w"] / BASE.boost_efficiency
        r_total = sum(BASE.cell_esrs_ohm) + BASE.input_path_ohm
        vin_cut = max(BASE.boost_input_floor_v, (BASE.pack_uvlo_v + math.sqrt(BASE.pack_uvlo_v**2 - 4*BASE.input_path_ohm*p_in))/2)
        current = p_in / vin_cut
        voc_end = vin_cut + current * r_total
        q_removed = (1.0 / sum(1.0/c for c in caps)) * (9.0 - voc_end)
        min_cell_terminal = 2.25 - q_removed / caps[0] - current * BASE.cell_esrs_ohm[0]
        mismatch.append({
            "cmax_over_cmin": ratio, "weak_cell_capacity_f": caps[0],
            "hold_s_before_cell_cuv": hold,
            "minimum_cell_terminal_at_boost_floor_v": min_cell_terminal,
            "cell_cuv_triggers_before_boost_floor": min_cell_terminal <= BASE.cell_cuv_v,
            "pass_1p2s_if_no_early_cell_cuv": hold >= 1.2,
        })
    write_csv(scans / "cell_capacity_mismatch.csv", mismatch)

    weak_skew = []
    for skew in (0, 0.2, 0.4, 0.6, 0.7, 0.75, 0.78, 0.787, 0.8):
        initial = (2.25 - skew, 2.25 + skew / 3, 2.25 + skew / 3, 2.25 + skew / 3)
        result = simulate(replace(BASE, name=f"weak_skew_{skew}", initial_cells_v=initial))
        weak_skew.append({
            "weak_cell_initial_skew_v": skew,
            "initial_cell_voltages_v": ";".join(f"{v:.9f}" for v in initial),
            "hold_s": result["hold_s"], "stop_reason": result["stop_reason"],
            "minimum_cell_terminal_v": result["minimum_cell_terminal_v"],
            "pass_1p2s": result["hold_s"] >= 1.2,
        })
    write_csv(scans / "weak_cell_voltage_skew.csv", weak_skew)

    weak_threshold = []
    weak_initial = (1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667)
    for threshold in (0.9, 1.0, 1.05, 1.1, 1.2):
        result = simulate(replace(BASE, name=f"cuv_{threshold}", initial_cells_v=weak_initial, cell_cuv_v=threshold))
        weak_threshold.append({
            "cell_cuv_v": threshold, "hold_s": result["hold_s"],
            "stop_reason": result["stop_reason"],
            "vin_boost_at_stop_v": result["end_state"]["vin_boost_v"],
            "minimum_cell_terminal_v": result["minimum_cell_terminal_v"],
            "pass_1p2s": result["hold_s"] >= 1.2,
        })
    write_csv(scans / "weak_cell_threshold_sensitivity.csv", weak_threshold)

    floor_rows = []
    for floor in (6.5, 6.75, 7.0, 7.25, 7.5):
        result = analytic_hold_time(replace(BASE, boost_input_floor_v=floor))
        floor_rows.append({
            "boost_input_floor_v": floor, "hold_s": result["hold_s"],
            "stop_reason": result["stop_reason"], "pass_1p2s": result["hold_s"] >= 1.2,
            "below_7v_device_level_validation": floor < 7.0,
        })
    write_csv(scans / "boost_input_floor_scan.csv", floor_rows)

    critical = []
    critical_specs = [
        ("minimum_cell_capacity", "F/cell", lambda x: analytic(cell_caps_f=(x,) * 4), 5.0, 15.0, False),
        ("maximum_cell_dc_esr", "mOhm/cell", lambda x: analytic(cell_esrs_ohm=(x / 1000,) * 4), 50.0, 200.0, True),
        ("minimum_boost_efficiency", "%", lambda x: analytic(boost_efficiency=x / 100), 50.0, 95.0, False),
        ("maximum_input_path", "mOhm", lambda x: analytic(input_path_ohm=x / 1000), 0.0, 300.0, True),
        ("maximum_output_path_energy_only", "mOhm", lambda x: analytic(output_path_ohm=x / 1000), 145.0, 1500.0, True),
        ("minimum_initial_pack_ocv", "V", lambda x: analytic(initial_cells_v=(x / 4,) * 4), 8.0, 9.4, False),
        ("maximum_cmax_over_cmin_ratio", "ratio", lambda x: analytic_general((11.2/x, 11.2, 11.2, 11.2), (0.106,)*4, (2.25,)*4, BASE), 1.0, 2.0, True),
        ("maximum_esr_multiplier_vs_106mohm", "x", lambda x: analytic(cell_esrs_ohm=(0.106*x,)*4), 1.0, 2.0, True),
    ]
    for name, unit, fn, lo, hi, decreasing in critical_specs:
        value = bisection(fn, lo, hi, decreasing=decreasing)
        critical.append({
            "parameter": name, "critical_value": value, "unit": unit,
            "boundary": "hold_time = 1.200 s",
            "scope": "single-variable mathematical boundary; all other baseline inputs fixed",
        })
    write_csv(scans / "critical_parameter_table.csv", critical)

    load_rows = []
    for label, scenario in (
        ("historical_load_12v_1a", BASE),
        ("boost_12v_fixed_1a", replace(BASE, load_mode="boost_fixed_12v_1a")),
        ("boost_12v_constant_power_12w", replace(BASE, load_mode="boost_fixed_12v_constant_power")),
    ):
        result = simulate(scenario)
        point = output_operating_point(scenario)
        load_rows.append({
            "scenario": label, **point, "hold_s": result["hold_s"],
            "load_voltage_window": "not specified; cannot declare load-voltage pass",
        })
    write_csv(scans / "load_voltage_scenarios.csv", load_rows)

    transfer = []
    cp_point = output_operating_point(replace(BASE, load_mode="boost_fixed_12v_constant_power"))
    iout, vload = cp_point["load_current_a"], cp_point["load_voltage_v"]
    for cap_uf in (47, 100, 220, 470, 1000, 22560, 22842):
        for transfer_us in (5, 50, 11280):
            dv = iout * transfer_us * 1e-6 / (cap_uf * 1e-6)
            transfer.append({
                "assumed_load_side_capacitance_uF": cap_uf,
                "assumed_transfer_time_us": transfer_us,
                "starting_load_voltage_v": vload,
                "load_current_a": iout,
                "ideal_capacitive_droop_v": dv,
                "ending_load_voltage_v": vload - dv,
                "note": "capacitor is assumed to be physically at LOAD_12V; effective load-side capacitance is unverified",
            })
    write_csv(scans / "transfer_sensitivity.csv", transfer)


def write_waveforms(out: Path) -> None:
    waves = out / "waveforms"
    waves.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "baseline_pass.csv": BASE,
        "joint_failure_1p146229.csv": replace(
            BASE, name="joint_failure",
            cell_caps_f=(10.8,) * 4, cell_esrs_ohm=(0.110,) * 4,
            boost_efficiency=0.83, input_path_ohm=0.120,
        ),
        "alternate_1p144457.csv": replace(BASE, name="alternate", boost_efficiency=0.83, input_path_ohm=0.150),
        "weak_cell_cuv_1p135937.csv": replace(
            BASE, name="weak_cell",
            initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
        ),
        "joint_weak_cell_failure.csv": replace(
            BASE, name="joint_weak_cell",
            cell_caps_f=(10.8,) * 4, cell_esrs_ohm=(0.110,) * 4,
            initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
            boost_efficiency=0.83, input_path_ohm=0.120,
        ),
    }
    for filename, scenario in scenarios.items():
        result = simulate(replace(scenario, record_interval_s=0.005))
        rows = [flatten_waveform_row(row) for row in result["rows"]]
        write_csv(waves / filename, rows)


def generate_netlists(out: Path) -> None:
    netlists = out / "netlists"
    netlists.mkdir(parents=True, exist_ok=True)
    cases = {
        "baseline_1p374803.cir": (11.2, 0.106, 0.85, 0.100, (2.25, 2.25, 2.25, 2.25), 14.288235294117648, None),
        "joint_failure_1p146229.cir": (10.8, 0.110, 0.83, 0.120, (2.25, 2.25, 2.25, 2.25), 14.632530120481928, None),
        "alternate_1p144457.cir": (11.2, 0.106, 0.83, 0.150, (2.25, 2.25, 2.25, 2.25), 14.632530120481928, None),
        "weak_cell_cuv_1p135937.cir": (11.2, 0.106, 0.85, 0.100, (1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667), 14.288235294117648, 1.05),
    }
    for filename, (cap, esr, eta, rin, initial, pin, cuv) in cases.items():
        lines = [
            f"* 4S Eaton UPS averaged storage model: {filename}",
            "* BLOAD is an averaged constant-power draw at VIN_BOOST, not a TPS61088 switching model.",
            f"* Cell capacitance={cap:.9g} F; cell ESR={esr:.9g} ohm; eta={eta:.9g}; Rin={rin:.9g} ohm.",
            f"* Pinput={pin:.12g} W. Initial cell OCVs: " + ", ".join(f"{v:.9f}" for v in initial),
            f"C1 n1 0 {cap:.12g} IC={initial[0]:.12g}",
            f"R1 n1 c1 {esr:.12g}",
            f"C2 n2 c1 {cap:.12g} IC={initial[1]:.12g}",
            f"R2 n2 c2 {esr:.12g}",
            f"C3 n3 c2 {cap:.12g} IC={initial[2]:.12g}",
            f"R3 n3 c3 {esr:.12g}",
            f"C4 n4 c3 {cap:.12g} IC={initial[3]:.12g}",
            f"R4 n4 pack {esr:.12g}",
            f"RIN pack vin {rin:.12g}",
            f"BLOAD vin 0 I={{ {pin:.12g}/max(V(vin),0.1) }}",
            ".options method=gear reltol=1e-7 abstol=1e-10",
            ".save V(vin) V(pack) V(c1) V(c2) V(c3) V(n4) I(BLOAD)",
            ".tran 100u 2 0 100u uic",
            ".meas tran t_boost_floor when V(vin)=7 fall=1",
            ".meas tran v_boost_at_1p2 find V(vin) at=1.2",
            ".meas tran v_pack_at_1p2 find V(pack) at=1.2",
            ".meas tran i_input_at_1p2 find I(BLOAD) at=1.2",
        ]
        if cuv is not None:
            lines.append(f".meas tran t_cell1_cuv when V(c1)={cuv:.12g} fall=1")
        lines.append(".end")
        (netlists / filename).write_text("\n".join(lines) + "\n", encoding="ascii")


def write_manifest(root: Path) -> None:
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.csv":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest})
    write_csv(root / "SHA256SUMS.csv", rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    summary = make_summary()
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "run_environment.json").write_text(json.dumps({
        "python": sys.version,
        "platform": platform.platform(),
        "baseline_commit": "360508c08f23f63cdd74fba7e0c201b0907d3825",
        "model_dt_s": BASE.dt_s,
        "waveform_record_interval_s": 0.005,
    }, indent=2) + "\n", encoding="utf-8")
    generate_scans(out)
    write_waveforms(out)
    generate_netlists(out)
    write_manifest(out)
    print(f"Generated energy-budget study in {out}")
    print(f"baseline={summary['baseline']['hold_s']:.9f}s")
    print(f"joint_failure={summary['known_joint_failure']['hold_s']:.9f}s")
    print(f"alternate_1p144457={summary['alternate_1p144457']['hold_s']:.9f}s")
    print(f"weak_cell={summary['weak_cell_cuv']['threshold_crossing_s']:.9f}s")


if __name__ == "__main__":
    main()
