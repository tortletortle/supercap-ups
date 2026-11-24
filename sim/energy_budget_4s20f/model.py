#!/usr/bin/env python3
"""4S Eaton HVH1230-2R7206-R UPS energy-budget model.

Averaged constant-power / lumped-ESR model with per-cell voltage states.
This is not a switching-converter, electrothermal, or hardware qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt
from typing import Any


@dataclass(frozen=True)
class Scenario:
    name: str
    cell_caps_f: tuple[float, float, float, float] = (11.2, 11.2, 11.2, 11.2)
    cell_esrs_ohm: tuple[float, float, float, float] = (0.106, 0.106, 0.106, 0.106)
    initial_cells_v: tuple[float, float, float, float] = (2.25, 2.25, 2.25, 2.25)
    boost_efficiency: float = 0.85
    input_path_ohm: float = 0.100
    output_path_ohm: float = 0.145
    # Historical reproduction: 12 V / 1 A at the load, so Boost must make 12.145 V.
    # Other modes expose the actual 12.0 V Boost-setpoint output-path droop.
    load_mode: str = "regulated_12v_1a"
    load_power_w: float = 12.0
    load_current_a: float = 1.0
    load_voltage_v: float = 12.0
    boost_setpoint_v: float = 12.0
    pack_uvlo_v: float = 7.110123
    boost_input_floor_v: float = 7.0
    cell_cuv_v: float = 1.05
    cell_hard_min_v: float = 1.0
    cell_uv_delay_s: float = 0.0
    max_time_s: float = 5.0
    dt_s: float = 1e-4
    record_interval_s: float = 1e-3


class PowerCollapseError(ArithmeticError):
    """No real low-current solution exists for the constant-power input."""


def validate_scenario(s: Scenario) -> None:
    if len(s.cell_caps_f) != 4 or len(s.cell_esrs_ohm) != 4 or len(s.initial_cells_v) != 4:
        raise ValueError("exactly four series cells are required")
    if any(c <= 0 for c in s.cell_caps_f) or any(r < 0 for r in s.cell_esrs_ohm):
        raise ValueError("cell capacitance must be positive and ESR non-negative")
    if not 0 < s.boost_efficiency <= 1:
        raise ValueError("boost_efficiency must be in (0, 1]")
    if min(s.input_path_ohm, s.output_path_ohm) < 0:
        raise ValueError("path resistances must be non-negative")
    if min(s.pack_uvlo_v, s.boost_input_floor_v, s.cell_cuv_v, s.cell_hard_min_v) < 0:
        raise ValueError("protection thresholds must be non-negative")
    if s.dt_s <= 0 or s.max_time_s <= 0 or s.record_interval_s <= 0:
        raise ValueError("time step, record interval and maximum time must be positive")
    if s.cell_uv_delay_s < 0:
        raise ValueError("cell_uv_delay_s must be non-negative")


def output_operating_point(s: Scenario) -> dict[str, float]:
    """Solve output-path/load operating point without hiding the load-voltage drop."""
    if s.load_mode == "regulated_12v_1a":
        iout = s.load_current_a
        vload = s.load_voltage_v
        vboost = vload + iout * s.output_path_ohm
        pload = vload * iout
        pboost = vboost * iout
    elif s.load_mode == "boost_fixed_12v_1a":
        vboost = s.boost_setpoint_v
        iout = s.load_current_a
        vload = vboost - iout * s.output_path_ohm
        pload = vload * iout
        pboost = vboost * iout
    elif s.load_mode == "boost_fixed_12v_constant_power":
        vboost = s.boost_setpoint_v
        pload = s.load_power_w
        disc = vboost * vboost - 4.0 * s.output_path_ohm * pload
        if disc <= 0:
            raise ValueError("no real operating point for the fixed-setpoint constant-power load")
        iout = (vboost - sqrt(disc)) / (2.0 * s.output_path_ohm) if s.output_path_ohm else pload / vboost
        vload = vboost - iout * s.output_path_ohm
        pboost = vboost * iout
    else:
        raise ValueError(f"unsupported load_mode: {s.load_mode}")
    return {
        "load_current_a": iout,
        "load_voltage_v": vload,
        "load_power_w": pload,
        "boost_output_voltage_v": vboost,
        "boost_output_power_w": pboost,
        "output_path_loss_w": iout * iout * s.output_path_ohm,
    }


def electrical_state(cell_ocv_v: tuple[float, ...], s: Scenario) -> dict[str, Any] | None:
    """Solve the instantaneous constant-power operating point."""
    out = output_operating_point(s)
    p_in = out["boost_output_power_w"] / s.boost_efficiency
    r_cell = sum(s.cell_esrs_ohm)
    r_total = r_cell + s.input_path_ohm
    voc = sum(cell_ocv_v)
    disc = voc * voc - 4.0 * r_total * p_in
    if disc <= 0:
        return None
    iin = 2.0 * p_in / (voc + sqrt(disc))
    vin = voc - iin * r_total
    pack_terminal = voc - iin * r_cell
    cell_terminal = tuple(v - iin * r for v, r in zip(cell_ocv_v, s.cell_esrs_ohm))
    return {
        "pack_ocv_v": voc,
        "pack_terminal_v": pack_terminal,
        "vin_boost_v": vin,
        "input_current_a": iin,
        "cell_terminal_v": cell_terminal,
        "min_cell_terminal_v": min(cell_terminal),
        "max_cell_terminal_v": max(cell_terminal),
        "load_voltage_v": out["load_voltage_v"],
        "load_current_a": out["load_current_a"],
        "load_power_w": out["load_power_w"],
        "boost_output_voltage_v": out["boost_output_voltage_v"],
        "boost_output_power_w": out["boost_output_power_w"],
        "input_power_w": p_in,
        "boost_loss_w": p_in - out["boost_output_power_w"],
        "cell_esr_loss_w": iin * iin * r_cell,
        "input_path_loss_w": iin * iin * s.input_path_ohm,
        "output_path_loss_w": out["output_path_loss_w"],
        "discriminant_v2": disc,
    }


def derivative(cell_ocv_v: tuple[float, ...], s: Scenario) -> tuple[float, ...]:
    st = electrical_state(cell_ocv_v, s)
    if st is None:
        raise PowerCollapseError("constant-power operating point collapsed")
    return tuple(-st["input_current_a"] / c for c in s.cell_caps_f)


def rk4_step(v: tuple[float, ...], h: float, s: Scenario) -> tuple[float, ...]:
    k1 = derivative(v, s)
    v2 = tuple(x + 0.5 * h * k for x, k in zip(v, k1))
    k2 = derivative(v2, s)
    v3 = tuple(x + 0.5 * h * k for x, k in zip(v, k2))
    k3 = derivative(v3, s)
    v4 = tuple(x + h * k for x, k in zip(v, k3))
    k4 = derivative(v4, s)
    return tuple(
        x + (h / 6.0) * (a + 2 * b + 2 * c + d)
        for x, a, b, c, d in zip(v, k1, k2, k3, k4)
    )


def event_metrics(st: dict[str, Any] | None, s: Scenario, ignore_cell_uv: bool = False) -> dict[str, float]:
    if st is None:
        return {"POWER_COLLAPSE": -1.0}
    metrics = {
        "PACK_UVLO": st["pack_terminal_v"] - s.pack_uvlo_v,
        "BOOST_INPUT_FLOOR": st["vin_boost_v"] - s.boost_input_floor_v,
        "CELL_HARD_MIN": st["min_cell_terminal_v"] - s.cell_hard_min_v,
    }
    if not ignore_cell_uv:
        metrics["CELL_UV"] = st["min_cell_terminal_v"] - s.cell_cuv_v
    return metrics


def first_event_crossing(
    v0: tuple[float, ...], h: float, s: Scenario, ignore_cell_uv: bool = False, iterations: int = 52
):
    """Locate the earliest event inside an RK4 step by bisection."""
    try:
        v1 = rk4_step(v0, h, s)
    except PowerCollapseError:
        # Find the first invalid point if the constant-power solution collapses inside this step.
        lo, hi = 0.0, 1.0
        for _ in range(iterations):
            mid = (lo + hi) / 2.0
            try:
                rk4_step(v0, h * mid, s)
                lo = mid
            except PowerCollapseError:
                hi = mid
        frac = hi
        try:
            vend = rk4_step(v0, h * lo, s)
        except PowerCollapseError:
            vend = v0
        return frac, "POWER_COLLAPSE", vend, None

    st1 = electrical_state(v1, s)
    m1 = event_metrics(st1, s, ignore_cell_uv)
    candidates = []
    for name, end_value in m1.items():
        if end_value > 0:
            continue
        lo, hi = 0.0, 1.0
        for _ in range(iterations):
            mid = (lo + hi) / 2.0
            vm = rk4_step(v0, h * mid, s) if mid > 0 else v0
            sm = electrical_state(vm, s)
            value = event_metrics(sm, s, ignore_cell_uv).get(name, 1.0)
            if value > 0:
                lo = mid
            else:
                hi = mid
        candidates.append((hi, name))
    if not candidates:
        return None
    frac, name = min(candidates, key=lambda item: item[0])
    vend = rk4_step(v0, h * frac, s) if frac > 0 else v0
    return frac, name, vend, electrical_state(vend, s)


def simulate(s: Scenario) -> dict[str, Any]:
    """Integrate per-cell OCVs, losses, and the first protection / input event."""
    validate_scenario(s)
    v = tuple(s.initial_cells_v)
    t = 0.0
    st = electrical_state(v, s)
    if st is None:
        return {"hold_s": 0.0, "stop_reason": "POWER_COLLAPSE", "rows": []}

    rows = [{"time_s": 0.0, **st}]
    energies = {"load": 0.0, "boost_loss": 0.0, "cell_esr": 0.0, "input_path": 0.0, "output_path": 0.0}
    max_i = st["input_current_a"]
    min_cell = st["min_cell_terminal_v"]
    min_load = st["load_voltage_v"]
    min_vin = st["vin_boost_v"]
    min_pack_terminal = st["pack_terminal_v"]
    next_record = s.record_interval_s
    stop_reason = "TIME_LIMIT"
    threshold_time = None
    isolation_time = None
    cell_uv_triggered = False
    deadline = None
    last_state = st

    initial_events = [k for k, value in event_metrics(st, s).items() if value <= 0]
    priority = ("CELL_HARD_MIN", "CELL_UV", "PACK_UVLO", "BOOST_INPUT_FLOOR")
    if initial_events:
        stop_reason = next((name for name in priority if name in initial_events), initial_events[0])
        threshold_time = 0.0 if stop_reason == "CELL_UV" else None
        isolation_time = 0.0
    else:
        while t < s.max_time_s - 1e-15:
            h = min(s.dt_s, s.max_time_s - t)
            if deadline is not None:
                h = min(h, max(0.0, deadline - t))
                if h <= 1e-15:
                    stop_reason = "CELL_UV_ISOLATION"
                    isolation_time = t
                    break

            crossing = first_event_crossing(v, h, s, ignore_cell_uv=cell_uv_triggered)
            if crossing is None:
                v_next = rk4_step(v, h, s)
                st_next = electrical_state(v_next, s)
                h_eff = h
                event_name = None
            else:
                frac, event_name, v_next, st_next = crossing
                h_eff = h * frac

            if st_next is not None:
                energies["load"] += 0.5 * (last_state["load_power_w"] + st_next["load_power_w"]) * h_eff
                energies["boost_loss"] += 0.5 * (last_state["boost_loss_w"] + st_next["boost_loss_w"]) * h_eff
                energies["cell_esr"] += 0.5 * (last_state["cell_esr_loss_w"] + st_next["cell_esr_loss_w"]) * h_eff
                energies["input_path"] += 0.5 * (last_state["input_path_loss_w"] + st_next["input_path_loss_w"]) * h_eff
                energies["output_path"] += 0.5 * (last_state["output_path_loss_w"] + st_next["output_path_loss_w"]) * h_eff
                max_i = max(max_i, last_state["input_current_a"], st_next["input_current_a"])
                min_cell = min(min_cell, last_state["min_cell_terminal_v"], st_next["min_cell_terminal_v"])
                min_load = min(min_load, last_state["load_voltage_v"], st_next["load_voltage_v"])
                min_vin = min(min_vin, last_state["vin_boost_v"], st_next["vin_boost_v"])
                min_pack_terminal = min(min_pack_terminal, last_state["pack_terminal_v"], st_next["pack_terminal_v"])

            t += h_eff
            v = v_next
            if st_next is None:
                stop_reason = "POWER_COLLAPSE"
                isolation_time = t
                break
            last_state = st_next

            if event_name:
                if event_name == "CELL_UV":
                    threshold_time = t
                    if s.cell_uv_delay_s > 0:
                        cell_uv_triggered = True
                        deadline = t + s.cell_uv_delay_s
                    else:
                        stop_reason = "CELL_UV"
                        isolation_time = t
                        break
                else:
                    stop_reason = event_name
                    isolation_time = t
                    break
            elif deadline is not None and t >= deadline - 1e-14:
                stop_reason = "CELL_UV_ISOLATION"
                isolation_time = t
                break

            if t + 1e-12 >= next_record:
                rows.append({"time_s": t, **last_state})
                next_record += s.record_interval_s
            if h_eff <= 1e-15:
                stop_reason = "NUMERICAL_STALL"
                isolation_time = t
                break

        if stop_reason == "TIME_LIMIT":
            isolation_time = t

    if not rows or rows[-1]["time_s"] < t - 1e-12:
        rows.append({"time_s": t, **last_state})

    e_initial = 0.5 * sum(c * v0 * v0 for c, v0 in zip(s.cell_caps_f, s.initial_cells_v))
    e_final = 0.5 * sum(c * vv * vv for c, vv in zip(s.cell_caps_f, v))
    residual = (e_initial - e_final) - (
        energies["load"] + energies["boost_loss"] + energies["cell_esr"] +
        energies["input_path"] + energies["output_path"]
    )
    return {
        "hold_s": t,
        "stop_reason": stop_reason,
        "threshold_crossing_time_s": threshold_time,
        "physical_isolation_time_s": isolation_time,
        "rows": rows,
        "end_cells_v": v,
        "max_input_current_a": max_i,
        "minimum_cell_terminal_v": min_cell,
        "minimum_load_voltage_v": min_load,
        "minimum_boost_input_v": min_vin,
        "minimum_pack_terminal_v": min_pack_terminal,
        "energies_j": energies,
        "capacitor_energy_removed_j": e_initial - e_final,
        "energy_balance_residual_j": residual,
        "cell_below_hard_min": min_cell < s.cell_hard_min_v,
        "end_state": last_state,
        "output_operating_point": output_operating_point(s),
    }


def analytic_hold_time(s: Scenario) -> dict[str, Any]:
    """Exact uniform-cell integral to the first pack-UVLO or Boost-input event.

    This closed form does not model a per-cell CUV event. Use simulate() for
    cell mismatch, unequal ESR, or initial-voltage skew.
    """
    validate_scenario(s)
    if max(s.cell_caps_f) - min(s.cell_caps_f) > 1e-12:
        raise ValueError("analytic_hold_time requires equal cell capacitances")
    if max(s.cell_esrs_ohm) - min(s.cell_esrs_ohm) > 1e-12:
        raise ValueError("analytic_hold_time requires equal cell ESR")
    if max(s.initial_cells_v) - min(s.initial_cells_v) > 1e-12:
        raise ValueError("analytic_hold_time requires equal initial cell voltages")

    out = output_operating_point(s)
    p_in = out["boost_output_power_w"] / s.boost_efficiency
    r_cell = sum(s.cell_esrs_ohm)
    r_total = r_cell + s.input_path_ohm
    c_eq = 1.0 / sum(1.0 / c for c in s.cell_caps_f)
    voc0 = sum(s.initial_cells_v)
    disc = voc0 * voc0 - 4.0 * r_total * p_in
    if disc <= 0:
        return {"hold_s": 0.0, "stop_reason": "POWER_COLLAPSE", "input_power_w": p_in}
    vin0 = (voc0 + sqrt(disc)) / 2.0
    uvlo_disc = s.pack_uvlo_v * s.pack_uvlo_v - 4.0 * s.input_path_ohm * p_in
    translated_uvlo = (s.pack_uvlo_v + sqrt(uvlo_disc)) / 2.0 if uvlo_disc > 0 else 0.0
    cutoff = max(s.boost_input_floor_v, translated_uvlo)
    hold = 0.0 if vin0 <= cutoff else (
        c_eq / p_in * (
            0.5 * (vin0 * vin0 - cutoff * cutoff) -
            r_total * p_in * log(vin0 / cutoff)
        )
    )
    stop = "BOOST_INPUT_FLOOR" if s.boost_input_floor_v >= translated_uvlo else "PACK_UVLO"
    return {
        "hold_s": hold,
        "stop_reason": stop,
        "input_power_w": p_in,
        "equivalent_capacitance_f": c_eq,
        "cell_esr_sum_ohm": r_cell,
        "total_series_resistance_ohm": r_total,
        "vin_boost_start_v": vin0,
        "translated_pack_uvlo_to_vin_v": translated_uvlo,
        "cutoff_vin_v": cutoff,
        "input_current_at_cutoff_a": p_in / cutoff,
    }


def analytic_general(
    cell_caps_f: tuple[float, ...], cell_esrs_ohm: tuple[float, ...],
    initial_cells_v: tuple[float, ...], s: Scenario
) -> float:
    """Exact series-capacitance result for unequal C when no cell-UV event occurs."""
    out = output_operating_point(s)
    p_in = out["boost_output_power_w"] / s.boost_efficiency
    r_cell = sum(cell_esrs_ohm)
    r_total = r_cell + s.input_path_ohm
    c_eq = 1.0 / sum(1.0 / c for c in cell_caps_f)
    voc0 = sum(initial_cells_v)
    disc = voc0 * voc0 - 4.0 * r_total * p_in
    if disc <= 0:
        return 0.0
    vin0 = (voc0 + sqrt(disc)) / 2.0
    uvlo_disc = s.pack_uvlo_v * s.pack_uvlo_v - 4.0 * s.input_path_ohm * p_in
    translated_uvlo = (s.pack_uvlo_v + sqrt(uvlo_disc)) / 2.0 if uvlo_disc > 0 else 0.0
    cutoff = max(s.boost_input_floor_v, translated_uvlo)
    return 0.0 if vin0 <= cutoff else c_eq / p_in * (
        0.5 * (vin0 * vin0 - cutoff * cutoff) - r_total * p_in * log(vin0 / cutoff)
    )
