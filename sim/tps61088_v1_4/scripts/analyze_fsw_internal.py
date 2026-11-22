"""Analyze direct internal TPS61088 timing-node probes from LTspice RAW.

Read-only post-processing: this module never edits a circuit or launches LTspice.
Requires NumPy. RAW parsing is isolated in ltspice_raw.py so this analyzer does
not inherit the plotting dependency from analyze_first_case.py.

Example:
  py -3 sim/tps61088_v1_4/scripts/analyze_fsw_internal.py --raw <probe.raw> --out <results-dir> --max-step-ns 50
  py -3 sim/tps61088_v1_4/scripts/analyze_fsw_internal.py --raw <probe25.raw> --out <results25-dir> --max-step-ns 25 --compare-with <results50-dir>/fsw_internal_summary.json
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from ltspice_raw import load_raw


DEFAULT_RFSW_OHM = 324e3
DEFAULT_CFSW_F = 23e-12
DEFAULT_ROFF_OHM = 1e6
DEFAULT_SW_EDGE_V = 10.0
DEFAULT_SW_REARM_V = 2.0
DEFAULT_LOGIC_EDGE_V = 0.5
DEFAULT_CAP_RESET_V = 0.5
EDGE_GUARD_S = 30e-9

CYCLE_FIELDS = (
    "cycle_start_s", "next_cycle_start_s", "period_s", "sw_high_s",
    "cycle_status", "cycle_valid", "event_order_valid", "invalid_reason",
    "raw_10v_rises_in_period", "raw_10v_falls_in_period",
    "pvin_cross_count", "comparator_output_rise_count",
    "u5_toff_0p5V_rise_count", "gate_l_rise_count",
    "cap_reset_0p5V_fall_count", "sw_fall_10V_count",
    "pvin_cross_s", "sw_rise_to_pvin_cross_s",
    "comparator_output_rise_s", "cross_to_comparator_output_rise_s",
    "comparator_output_rise_bracket_width_s",
    "u5_toff_0p5V_rise_s", "comparator_output_rise_to_u5_toff_0p5V_s",
    "cross_to_u5_toff_0p5V_s", "gate_l_rise_s", "cross_to_gate_l_rise_s",
    "u5_toff_0p5V_to_gate_l_rise_s", "cap_reset_0p5V_fall_s",
    "gate_l_rise_to_cap_reset_0p5V_s", "cross_to_cap_reset_0p5V_s",
    "sw_fall_10V_s", "cross_to_sw_fall_s", "cap_reset_to_sw_fall_s",
    "comparator_output_rise_to_sw_fall_s",
    "rc_ode_predicted_cross_s", "rc_ode_predicted_ramp_s",
    "rc_ode_prediction_residual_s",
    "C_est_from_internal_ifsw_F", "C_est_from_external_rfsw_F",
    "charge_window_gate_low_fraction",
    "pvin_at_cross_V", "cap_at_sw_rise_V", "sw_at_cross_V",
    "cap_minus_fsw_at_cross_V", "ifsw_plus_rfsw_current_at_cross_A",
    "u5_tsw_at_cross", "u5_tdelay_sw_at_cross", "u5_toff_at_cross",
    "u5_tend_at_cross", "gate_l_at_cross", "ssend_at_cross",
    "mode_ok_at_cross", "u5_sel_toff_at_cross", "u5_toff_sel_at_cross",
    "u5_toff_sel_1_at_cross", "comparator_out_at_cross",
)


def trapezoid(y, x):
    """NumPy 1.x/2.x compatible trapezoidal integration."""
    fn = getattr(np, "trapezoid", None)
    if fn is None:
        fn = np.trapz
    return float(fn(y, x))


def crossings_with_brackets(t, y, level, direction):
    """Return interpolated crossings and their source-sample bracket widths.

    A wide bracket is especially important for near-discontinuous comparator
    outputs: linear interpolation of a 0-to-1 transition across one max-step
    interval is not a precise physical propagation-delay measurement.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("t and y must be equal-length one-dimensional arrays")
    if len(t) < 2:
        empty = np.asarray([], dtype=float)
        return empty, empty
    if direction == "rise":
        mask = (y[:-1] < level) & (y[1:] >= level)
    elif direction == "fall":
        mask = (y[:-1] >= level) & (y[1:] < level)
    else:
        raise ValueError("direction must be 'rise' or 'fall'")
    k = np.flatnonzero(mask)
    if not len(k):
        empty = np.asarray([], dtype=float)
        return empty, empty
    dy = y[k + 1] - y[k]
    dt = t[k + 1] - t[k]
    valid = np.isfinite(dy) & np.isfinite(dt) & (dy != 0) & (dt > 0)
    k, dy, dt = k[valid], dy[valid], dt[valid]
    if not len(k):
        empty = np.asarray([], dtype=float)
        return empty, empty
    event_times = t[k] + (level - y[k]) / dy * dt
    return event_times, dt


def crossings(t, y, level, direction):
    """Linearly interpolated threshold crossings."""
    return crossings_with_brackets(t, y, level, direction)[0]


def pair_cycle_events(cycle_start, cycle_limit, input_cross,
                      comparator_rises, toff_rises, gate_rises,
                      cap_reset_falls, sw_falls):
    """Pair timing events using the comparator INPUT crossing as time zero.

    The TI macro-model's ideal comparator source switches on
    V(U5_N01584) > V(U5_PVIN). Its output node U5_N16903113 is then shaped by
    a 1-ohm / 1-nF RC, whose fast transition can be under-sampled by a 25/50-ns
    RAW grid. Therefore its linearly interpolated 0.5-V crossing is diagnostic
    only and must not gate or invalidate the smooth downstream U5_TOFF event.
    """
    comparator = first_between(comparator_rises, cycle_start, cycle_limit)
    toff = (
        first_between(toff_rises, input_cross, cycle_limit)
        if input_cross is not None else None
    )
    gate = (
        first_between(gate_rises, input_cross, cycle_limit)
        if input_cross is not None else None
    )
    sw_fall = first_between(sw_falls, cycle_start, cycle_limit)
    reset_start = gate if gate is not None else (
        input_cross if input_cross is not None else cycle_start
    )
    reset = first_between(cap_reset_falls, reset_start, cycle_limit)

    ordered = [input_cross, toff, gate, reset, sw_fall]
    event_order_valid = (
        all(value is not None for value in ordered)
        and all(ordered[i] <= ordered[i + 1] + 1e-15
                for i in range(len(ordered) - 1))
    )
    return {
        "comparator": comparator,
        "toff": toff,
        "gate": gate,
        "reset": reset,
        "sw_fall": sw_fall,
        "event_order_valid": bool(event_order_valid),
    }

def hysteretic_rising_crossings(t, y, high, rearm):
    """Accept a high-threshold rise only after the signal has first fallen below rearm.

    Returns (accepted_edge_times, rejected_raw_rise_count). This suppresses
    multiple 10-V crossings caused by ringing without changing the original
    raw RISE=6001/6101 measurement, which is computed separately.
    """
    if rearm >= high:
        raise ValueError("rearm threshold must be below the rising threshold")
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    raw_rises = crossings(t, y, high, "rise")
    accepted = []
    armed = bool(y[0] < rearm)
    for i in range(len(y) - 1):
        if not armed:
            if y[i] >= rearm and y[i + 1] < rearm:
                armed = True
            continue
        if y[i] < high and y[i + 1] >= high:
            dy = y[i + 1] - y[i]
            dt = t[i + 1] - t[i]
            if dy != 0 and dt > 0:
                accepted.append(float(t[i] + (high - y[i]) / dy * dt))
                armed = False
    accepted = np.asarray(accepted, dtype=float)
    return accepted, max(0, int(len(raw_rises) - len(accepted)))


def sample(t, y, when):
    if when < t[0] or when > t[-1]:
        raise ValueError(f"sample time {when} is outside RAW time range")
    return float(np.interp(when, t, y))


def first_between(events, start, end):
    """First event in the half-open interval [start, end)."""
    i = int(np.searchsorted(events, start, side="left"))
    return float(events[i]) if i < len(events) and events[i] < end else None


def count_between(events, start, end):
    """Count events in the half-open interval [start, end)."""
    left = int(np.searchsorted(events, start, side="left"))
    right = int(np.searchsorted(events, end, side="left"))
    return right - left


EVENT_COUNT_FIELDS = {
    "pvin_cross": "pvin_cross_count",
    "comparator_output_rise": "comparator_output_rise_count",
    "u5_toff_0p5V_rise": "u5_toff_0p5V_rise_count",
    "gate_l_rise": "gate_l_rise_count",
    "cap_reset_0p5V_fall": "cap_reset_0p5V_fall_count",
    "sw_fall_10V": "sw_fall_10V_count",
}


def event_multiplicity_summary(rows):
    """Count missing and repeated events over complete SW periods only."""
    complete_period_rows = [
        row for row in rows if row["next_cycle_start_s"] is not None
    ]
    return {
        name: {
            "missing_cycles": sum(row[field] == 0 for row in complete_period_rows),
            "multiple_cycles": sum(row[field] > 1 for row in complete_period_rows),
        }
        for name, field in EVENT_COUNT_FIELDS.items()
    }


def summary(values):
    x = np.asarray(
        [v for v in values if v is not None and np.isfinite(v)], dtype=float
    )
    if not len(x):
        return None
    return {
        "count": int(len(x)),
        "min": float(np.min(x)),
        "p05": float(np.percentile(x, 5)),
        "median": float(np.median(x)),
        "mean": float(np.mean(x)),
        "p95": float(np.percentile(x, 95)),
        "max": float(np.max(x)),
        "std": float(np.std(x)),
    }


def integrate_rc_piecewise_linear(t, sw, cap_initial, start, end,
                                  rfsw_ohm, roff_ohm, c_f):
    """Integrate C*dV/dt=(VSW-V)/RFSW - V/ROFF exactly per linear SW segment.

    SW is treated as piecewise linear between stored RAW samples. The exact
    first-order state update avoids replacing the measured SW waveform with a
    single average voltage.
    """
    if not (0 < rfsw_ohm and 0 < roff_ohm and 0 < c_f):
        raise ValueError("RFSW, ROFF and C must be positive")
    if end <= start:
        raise ValueError("end must be greater than start")
    if start < t[0] or end > t[-1]:
        raise ValueError("RC integration window is outside RAW time range")

    inside = t[(t > start) & (t < end)]
    tt = np.unique(np.concatenate(([start], inside, [end])))
    v_sw = np.interp(tt, t, sw)
    v_cap = np.empty(len(tt), dtype=float)
    v_cap[0] = float(cap_initial)

    r_eq = 1.0 / (1.0 / rfsw_ohm + 1.0 / roff_ohm)
    tau = r_eq * c_f
    gain = r_eq / rfsw_ohm

    for i in range(len(tt) - 1):
        dt = float(tt[i + 1] - tt[i])
        if dt <= 0:
            raise ValueError("RC integration time grid must be strictly increasing")
        slope = float((v_sw[i + 1] - v_sw[i]) / dt)
        one_minus_exp = float(-np.expm1(-dt / tau))
        exp_term = 1.0 - one_minus_exp
        v_cap[i + 1] = (
            v_cap[i] * exp_term
            + gain * (
                v_sw[i] * one_minus_exp
                + slope * (dt - tau * one_minus_exp)
            )
        )
    return tt, v_cap


def predict_rc_crossing(t, sw, pvin, cap, start, end,
                        rfsw_ohm, roff_ohm, c_f):
    """Predict the FSW/PVIN crossing using measured SW(t) and the RC ODE."""
    cap0 = sample(t, cap, start)
    tt, predicted_cap = integrate_rc_piecewise_linear(
        t, sw, cap0, start, end, rfsw_ohm, roff_ohm, c_f
    )
    predicted_difference = predicted_cap - np.interp(tt, t, pvin)
    events = crossings(tt, predicted_difference, 0.0, "rise")
    return float(events[0]) if len(events) else None


def estimate_capacitance(t, cap, current, gate, mask, roff_ohm):
    """Estimate C from net charge only when the 1-Mohm reset path is OFF."""
    count = int(np.count_nonzero(mask))
    if count < 3:
        return None, 0.0
    gate_low = gate[mask] < 0.2
    low_fraction = float(np.mean(gate_low))
    if not np.all(gate_low):
        return None, low_fraction
    voltage_delta = float(cap[mask][-1] - cap[mask][0])
    if voltage_delta <= 0:
        return None, low_fraction
    net_current = current[mask] - cap[mask] / roff_ohm
    charge = trapezoid(net_current, t[mask])
    return float(charge / voltage_delta), low_fraction


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CYCLE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def compare_summaries(current, baseline):
    """Compare distributions, never adaptive-grid samples point by point."""
    fields = (
        "period_s", "sw_high_s", "sw_rise_to_pvin_cross_s",
        "cross_to_comparator_output_rise_s",
        "comparator_output_rise_bracket_width_s",
        "comparator_output_rise_to_u5_toff_0p5V_s",
        "cross_to_u5_toff_0p5V_s", "cross_to_gate_l_rise_s",
        "u5_toff_0p5V_to_gate_l_rise_s",
        "gate_l_rise_to_cap_reset_0p5V_s", "cross_to_sw_fall_s",
        "cap_reset_to_sw_fall_s", "rc_ode_prediction_residual_s",
        "C_est_from_internal_ifsw_F", "C_est_from_external_rfsw_F",
    )
    deltas = {}
    cur_stats = current.get("cycle_statistics", {})
    base_stats = baseline.get("cycle_statistics", {})
    for field in fields:
        a, b = cur_stats.get(field), base_stats.get(field)
        if not a or not b:
            deltas[field] = None
            continue
        scale = 1e9 if field.endswith("_s") else (1e12 if field.endswith("_F") else 1.0)
        unit = "ns" if field.endswith("_s") else ("pF" if field.endswith("_F") else "")
        deltas[field] = {
            "unit": unit,
            "current_median": a["median"] * scale,
            "baseline_median": b["median"] * scale,
            "median_delta": (a["median"] - b["median"]) * scale,
            "current_p95": a["p95"] * scale,
            "baseline_p95": b["p95"] * scale,
        }
    cur_freq = current.get("prescribed_edge_measurement", {}).get("frequency_kHz")
    base_freq = baseline.get("prescribed_edge_measurement", {}).get("frequency_kHz")
    return {
        "baseline_summary": baseline.get("raw_path"),
        "current_summary": current.get("raw_path"),
        "baseline_run_parameters": baseline.get("run_parameters"),
        "current_run_parameters": current.get("run_parameters"),
        "same_electrical_parameters": (
            baseline.get("run_parameters", {}).get("rfsw_ohm")
            == current.get("run_parameters", {}).get("rfsw_ohm")
            and baseline.get("run_parameters", {}).get("cfsw_f")
            == current.get("run_parameters", {}).get("cfsw_f")
            and baseline.get("run_parameters", {}).get("roff_ohm")
            == current.get("run_parameters", {}).get("roff_ohm")
        ),
        "baseline_valid_cycles": baseline.get("cycle_accounting", {}).get("complete_valid_cycles"),
        "current_valid_cycles": current.get("cycle_accounting", {}).get("complete_valid_cycles"),
        "frequency_delta_khz": (
            float(cur_freq - base_freq)
            if cur_freq is not None and base_freq is not None else None
        ),
        "distribution_deltas": deltas,
        "interpretation": (
            "Distribution-level comparison only. Different adaptive RAW time grids "
            "must not be compared sample by sample."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0.024,
                        help="analysis start time in seconds")
    parser.add_argument("--end", type=float, default=0.026,
                        help="analysis end time in seconds")
    parser.add_argument("--rfsw-ohm", type=float, default=DEFAULT_RFSW_OHM)
    parser.add_argument("--cfsw-f", type=float, default=DEFAULT_CFSW_F)
    parser.add_argument("--roff-ohm", type=float, default=DEFAULT_ROFF_OHM)
    parser.add_argument("--sw-edge-v", type=float, default=DEFAULT_SW_EDGE_V)
    parser.add_argument("--sw-rearm-v", type=float, default=DEFAULT_SW_REARM_V)
    parser.add_argument("--vout-target-v", type=float, default=12.0)
    parser.add_argument("--max-step-ns", type=float, default=None,
                        help="recorded deck maximum step; does not alter the RAW")
    parser.add_argument("--solver-label", default="Gear")
    parser.add_argument("--compare-with", type=Path, default=None,
                        help="compare distributions against another fsw_internal_summary.json")
    args = parser.parse_args()

    if args.end <= args.start:
        parser.error("--end must be greater than --start")
    if args.rfsw_ohm <= 0 or args.cfsw_f <= 0 or args.roff_ohm <= 0:
        parser.error("RFSW, CFSW and ROFF must be positive")
    if args.sw_rearm_v >= args.sw_edge_v:
        parser.error("--sw-rearm-v must be below --sw-edge-v")

    header, names, raw = load_raw(args.raw)
    if raw.ndim != 2 or raw.shape[1] != len(names):
        raise ValueError("RAW matrix dimensions do not match the variable table")
    idx = {}
    for i, name in enumerate(names):
        key = name.strip().lower()
        if key in idx:
            raise ValueError(f"Duplicate RAW variable name after normalization: {name}")
        idx[key] = i

    required = [
        "time", "v(sw)", "v(fsw)", "i(rfsw)", "v(vout)", "i(l1)",
        "v(x1:u5_pvin)", "v(x1:u5_n01584)", "v(x1:u5_ifsw)",
        "v(x1:u5_tsw)", "v(x1:u5_tdelay_sw)", "v(x1:u5_toff)",
        "v(x1:u5_tend)", "v(x1:gate_l)", "v(x1:ssend)",
        "v(x1:mode_ok)", "v(x1:u5_sel_toff)", "v(x1:u5_toff_sel)",
        "v(x1:u5_toff_sel_1)", "v(x1:u5_n16903113)",
    ]
    missing = [name for name in required if name not in idx]
    if missing:
        available = [name for name in names if ":" in name.lower()]
        raise ValueError(
            "Missing hierarchical RAW vectors: " + ", ".join(missing)
            + ". Check LTspice .save hierarchy syntax and Save Subcircuit Node Voltages. "
            + "Available hierarchical vectors: " + ", ".join(available[:80])
        )

    def vec(name):
        # np.interp otherwise copies the entire strided RAW column on each
        # per-cycle lookup. One exact copy preserves samples and avoids this.
        return np.array(raw[:, idx[name]], dtype=float, copy=True)

    t = vec("time")
    sw = vec("v(sw)")
    fsw = vec("v(fsw)")
    irfsw = vec("i(rfsw)")
    vout = vec("v(vout)")
    il1 = vec("i(l1)")
    pvin = vec("v(x1:u5_pvin)")
    cap = vec("v(x1:u5_n01584)")
    ifsw = vec("v(x1:u5_ifsw)")
    tsw = vec("v(x1:u5_tsw)")
    tdelay = vec("v(x1:u5_tdelay_sw)")
    toff = vec("v(x1:u5_toff)")
    tend = vec("v(x1:u5_tend)")
    gate = vec("v(x1:gate_l)")
    ssend = vec("v(x1:ssend)")
    mode_ok = vec("v(x1:mode_ok)")
    sel_toff = vec("v(x1:u5_sel_toff)")
    toff_sel = vec("v(x1:u5_toff_sel)")
    toff_sel_1 = vec("v(x1:u5_toff_sel_1)")
    comparator_out = vec("v(x1:u5_n16903113)")

    if len(t) < 3 or not np.all(np.isfinite(t)):
        raise ValueError("RAW time vector is empty or contains nonfinite values")
    if np.any(np.diff(t) < 0):
        raise ValueError("RAW time vector is not monotonic")
    if args.start < t[0] or args.end > t[-1]:
        raise ValueError(
            f"analysis window [{args.start}, {args.end}] lies outside "
            f"RAW time range [{t[0]}, {t[-1]}]"
        )
    late = (t >= args.start) & (t <= args.end)
    if np.count_nonzero(late) < 2:
        raise ValueError("Fewer than two RAW samples in the requested analysis window")

    raw_sw_rise = crossings(t, sw, args.sw_edge_v, "rise")
    raw_sw_fall = crossings(t, sw, args.sw_edge_v, "fall")
    sw_rise, rejected_retriggers = hysteretic_rising_crossings(
        t, sw, args.sw_edge_v, args.sw_rearm_v
    )
    cap_minus_pvin_rise = crossings(t, cap - pvin, 0.0, "rise")
    cap_reset_fall = crossings(t, cap, DEFAULT_CAP_RESET_V, "fall")
    gate_rise = crossings(t, gate, DEFAULT_LOGIC_EDGE_V, "rise")
    comparator_rise, comparator_rise_brackets = crossings_with_brackets(
        t, comparator_out, DEFAULT_LOGIC_EDGE_V, "rise"
    )
    toff_rise = crossings(t, toff, DEFAULT_LOGIC_EDGE_V, "rise")
    vout_98 = crossings(t, vout, 0.98 * args.vout_target_v, "rise")

    rows = []
    candidate_indices = np.flatnonzero(
        (sw_rise >= args.start) & (sw_rise < args.end)
    )
    for accepted_index in candidate_indices:
        up = float(sw_rise[accepted_index])
        next_up = (
            float(sw_rise[accepted_index + 1])
            if accepted_index + 1 < len(sw_rise) else None
        )
        cycle_limit = next_up if next_up is not None else args.end

        raw_rise_lo = int(np.searchsorted(raw_sw_rise, up, side="left"))
        raw_rise_hi = int(np.searchsorted(raw_sw_rise, cycle_limit, side="left"))
        raw_fall_lo = int(np.searchsorted(raw_sw_fall, up, side="left"))
        raw_fall_hi = int(np.searchsorted(raw_sw_fall, cycle_limit, side="left"))
        raw_rises_in_period = raw_rise_hi - raw_rise_lo
        raw_falls_in_period = raw_fall_hi - raw_fall_lo

        event_counts = {
            "pvin_cross_count": count_between(cap_minus_pvin_rise, up, cycle_limit),
            "comparator_output_rise_count": count_between(comparator_rise, up, cycle_limit),
            "u5_toff_0p5V_rise_count": count_between(toff_rise, up, cycle_limit),
            "gate_l_rise_count": count_between(gate_rise, up, cycle_limit),
            "cap_reset_0p5V_fall_count": count_between(cap_reset_fall, up, cycle_limit),
            "sw_fall_10V_count": raw_falls_in_period,
        }

        cross = first_between(cap_minus_pvin_rise, up, cycle_limit)
        paired = pair_cycle_events(
            up, cycle_limit, cross, comparator_rise, toff_rise,
            gate_rise, cap_reset_fall, raw_sw_fall
        )
        comp_on = paired["comparator"]
        toff_on = paired["toff"]
        gate_on = paired["gate"]
        reset = paired["reset"]
        down = paired["sw_fall"]
        comp_bracket_width = None
        if comp_on is not None:
            comp_index = int(np.searchsorted(comparator_rise, comp_on, side="left"))
            if comp_index < len(comparator_rise_brackets):
                comp_bracket_width = float(comparator_rise_brackets[comp_index])

        predicted_cross = None
        # The 1-Mohm path is valid only while GATE_L is low. Stop the RC
        # prediction at the observed gate turn-on, not after the capacitor reset.
        rc_end = gate_on if gate_on is not None else down
        if rc_end is not None and rc_end > up:
            predicted_cross = predict_rc_crossing(
                t, sw, pvin, cap, up, rc_end,
                args.rfsw_ohm, args.roff_ohm, args.cfsw_f,
            )

        charge_mask = np.zeros(len(t), dtype=bool)
        if down is not None and down - up > 2 * EDGE_GUARD_S:
            charge_mask = (
                (t >= up + EDGE_GUARD_S) & (t <= down - EDGE_GUARD_S)
            )
        c_internal, gate_low_fraction = estimate_capacitance(
            t, cap, ifsw, gate, charge_mask, args.roff_ohm
        )
        c_external, _ = estimate_capacitance(
            t, cap, -irfsw, gate, charge_mask, args.roff_ohm
        )

        missing_events = [
            name for name, value in (
                ("next_sw_rise", next_up), ("sw_fall_10V", down),
                ("pvin_cross", cross), ("u5_toff_0p5V_rise", toff_on),
                ("gate_l_rise", gate_on), ("cap_reset_0p5V_fall", reset),
            ) if value is None
        ]
        # The comparator output's interpolated 0.5-V crossing is diagnostic only.
        # Its same-bracket ordering versus the smooth input crossing is not used
        # as a cycle-validity gate.
        event_order_valid = paired["event_order_valid"]
        if not event_order_valid and not missing_events:
            missing_events.append("event_order_violation")
        if raw_rises_in_period != 1:
            missing_events.append("multiple_raw_10V_rises")
        if raw_falls_in_period != 1:
            missing_events.append("multiple_or_missing_raw_10V_falls")
        for event_name, event_count in event_counts.items():
            if event_count > 1:
                missing_events.append(f"multiple_{event_name}")

        if next_up is None:
            cycle_status = "right_censored_at_raw_end"
        elif not missing_events:
            cycle_status = "complete"
        else:
            cycle_status = "invalid"
        cycle_valid = cycle_status == "complete" and event_order_valid
        invalid_reason = ";".join(missing_events)

        period = next_up - up if next_up is not None else None
        sw_high = down - up if down is not None else None
        cross_to_comp = comp_on - cross if comp_on is not None and cross is not None else None
        comp_to_toff = toff_on - comp_on if toff_on is not None and comp_on is not None else None
        cross_to_toff = toff_on - cross if toff_on is not None and cross is not None else None
        cross_to_gate = gate_on - cross if gate_on is not None and cross is not None else None
        toff_to_gate = gate_on - toff_on if gate_on is not None and toff_on is not None else None
        gate_to_reset = reset - gate_on if reset is not None and gate_on is not None else None
        cross_to_reset = reset - cross if reset is not None and cross is not None else None
        cross_to_down = down - cross if down is not None and cross is not None else None
        reset_to_down = down - reset if down is not None and reset is not None else None
        comp_to_down = down - comp_on if down is not None and comp_on is not None else None
        rc_residual = predicted_cross - cross if predicted_cross is not None and cross is not None else None

        if cross is not None:
            pvin_at_cross = sample(t, pvin, cross)
            cap_at_cross = sample(t, cap, cross)
            sw_at_cross = sample(t, sw, cross)
            cap_minus_fsw = sample(t, cap - fsw, cross)
            current_sensor_error = sample(t, ifsw + irfsw, cross)
            values_at_cross = {
                "u5_tsw_at_cross": sample(t, tsw, cross),
                "u5_tdelay_sw_at_cross": sample(t, tdelay, cross),
                "u5_toff_at_cross": sample(t, toff, cross),
                "u5_tend_at_cross": sample(t, tend, cross),
                "gate_l_at_cross": sample(t, gate, cross),
                "ssend_at_cross": sample(t, ssend, cross),
                "mode_ok_at_cross": sample(t, mode_ok, cross),
                "u5_sel_toff_at_cross": sample(t, sel_toff, cross),
                "u5_toff_sel_at_cross": sample(t, toff_sel, cross),
                "u5_toff_sel_1_at_cross": sample(t, toff_sel_1, cross),
                "comparator_out_at_cross": sample(t, comparator_out, cross),
            }
        else:
            pvin_at_cross = cap_at_cross = sw_at_cross = None
            cap_minus_fsw = current_sensor_error = None
            values_at_cross = {
                key: None for key in (
                    "u5_tsw_at_cross", "u5_tdelay_sw_at_cross",
                    "u5_toff_at_cross", "u5_tend_at_cross",
                    "gate_l_at_cross", "ssend_at_cross", "mode_ok_at_cross",
                    "u5_sel_toff_at_cross", "u5_toff_sel_at_cross",
                    "u5_toff_sel_1_at_cross", "comparator_out_at_cross",
                )
            }

        rows.append({
            "cycle_start_s": up,
            "next_cycle_start_s": next_up,
            "period_s": period,
            "sw_high_s": sw_high,
            "cycle_status": cycle_status,
            "cycle_valid": bool(cycle_valid),
            "event_order_valid": bool(event_order_valid),
            "invalid_reason": invalid_reason,
            "raw_10v_rises_in_period": int(raw_rises_in_period),
            "raw_10v_falls_in_period": int(raw_falls_in_period),
            **{key: int(value) for key, value in event_counts.items()},
            "pvin_cross_s": cross,
            "sw_rise_to_pvin_cross_s": cross - up if cross is not None else None,
            "comparator_output_rise_s": comp_on,
            "cross_to_comparator_output_rise_s": cross_to_comp,
            "comparator_output_rise_bracket_width_s": comp_bracket_width,
            "u5_toff_0p5V_rise_s": toff_on,
            "comparator_output_rise_to_u5_toff_0p5V_s": comp_to_toff,
            "cross_to_u5_toff_0p5V_s": cross_to_toff,
            "gate_l_rise_s": gate_on,
            "cross_to_gate_l_rise_s": cross_to_gate,
            "u5_toff_0p5V_to_gate_l_rise_s": toff_to_gate,
            "cap_reset_0p5V_fall_s": reset,
            "gate_l_rise_to_cap_reset_0p5V_s": gate_to_reset,
            "cross_to_cap_reset_0p5V_s": cross_to_reset,
            "sw_fall_10V_s": down,
            "cross_to_sw_fall_s": cross_to_down,
            "cap_reset_to_sw_fall_s": reset_to_down,
            "comparator_output_rise_to_sw_fall_s": comp_to_down,
            "rc_ode_predicted_cross_s": predicted_cross,
            "rc_ode_predicted_ramp_s": predicted_cross - up if predicted_cross is not None else None,
            "rc_ode_prediction_residual_s": rc_residual,
            "C_est_from_internal_ifsw_F": c_internal,
            "C_est_from_external_rfsw_F": c_external,
            "charge_window_gate_low_fraction": gate_low_fraction,
            "pvin_at_cross_V": pvin_at_cross,
            "cap_at_sw_rise_V": sample(t, cap, up),
            "sw_at_cross_V": sw_at_cross,
            "cap_minus_fsw_at_cross_V": cap_minus_fsw,
            "ifsw_plus_rfsw_current_at_cross_A": current_sensor_error,
            **values_at_cross,
        })

    valid_rows = [row for row in rows if row["cycle_valid"]]
    numeric_fields = [
        field for field in CYCLE_FIELDS
        if field.endswith("_s") or field.endswith("_F")
    ]
    cycle_statistics = {
        field: summary([row[field] for row in valid_rows])
        for field in numeric_fields
    }
    all_cycle_statistics = {
        field: summary([row[field] for row in rows])
        for field in numeric_fields
    }

    t6001 = float(raw_sw_rise[6000]) if len(raw_sw_rise) >= 6001 else None
    t6101 = float(raw_sw_rise[6100]) if len(raw_sw_rise) >= 6101 else None
    t98 = float(vout_98[0]) if len(vout_98) else None
    frequency = (
        100.0 / (t6101 - t6001) / 1e3
        if t6001 is not None and t6101 is not None and t6101 > t6001
        else None
    )

    invalid_rows = [
        {
            "cycle_start_s": row["cycle_start_s"],
            "cycle_status": row["cycle_status"],
            "invalid_reason": row["invalid_reason"],
        }
        for row in rows if not row["cycle_valid"]
    ]
    event_keys = (
        "pvin_cross_s", "comparator_output_rise_s", "u5_toff_0p5V_rise_s",
        "gate_l_rise_s", "cap_reset_0p5V_fall_s", "sw_fall_10V_s",
    )
    event_completeness = {
        key: sum(row[key] is not None for row in rows) for key in event_keys
    }
    event_multiplicity = event_multiplicity_summary(rows)

    summary_data = {
        "raw_path": str(args.raw.resolve()),
        "raw_point_count": int(len(t)),
        "raw_variables": names,
        "analysis_window_s": [args.start, args.end],
        "run_parameters": {
            "rfsw_ohm": args.rfsw_ohm,
            "cfsw_f": args.cfsw_f,
            "roff_ohm": args.roff_ohm,
            "sw_edge_v": args.sw_edge_v,
            "sw_rearm_v": args.sw_rearm_v,
            "solver_label": args.solver_label,
            "max_step_ns": args.max_step_ns,
        },
        "analysis_status": (
            "complete" if rows and len(valid_rows) == len(rows)
            else ("warning" if rows else "no_cycles")
        ),
        "cycle_accounting": {
            "candidate_cycles": len(rows),
            "complete_valid_cycles": len(valid_rows),
            "right_censored_cycles": sum(
                row["cycle_status"] == "right_censored_at_raw_end" for row in rows
            ),
            "invalid_cycles": sum(row["cycle_status"] == "invalid" for row in rows),
        },
        "invalid_cycle_details": invalid_rows,
        "event_completeness": event_completeness,
        "event_multiplicity": event_multiplicity,
        "prescribed_edge_measurement": {
            "raw_10V_rise_count": int(len(raw_sw_rise)),
            "hysteretic_accepted_rise_count": int(len(sw_rise)),
            "raw_retrigger_count_suppressed_by_rearm": int(rejected_retriggers),
            "raw_10V_rise_count_in_window": int(np.count_nonzero(
                (raw_sw_rise >= args.start) & (raw_sw_rise < args.end)
            )),
            "hysteretic_rise_count_in_window": int(len(candidate_indices)),
            "t98_s": t98,
            "sw_t6001_s": t6001,
            "sw_t6101_s": t6101,
            "frequency_kHz": frequency,
            "timing_valid": bool(
                t98 is not None and t6001 is not None and t6101 is not None
                and t98 < t6001 < t6101 < t[-1]
            ),
        },
        "direct_internal_consistency": {
            "max_abs_cap_minus_fsw_V": float(np.max(np.abs((cap - fsw)[late]))),
            "max_abs_ifsw_plus_rfsw_current_A": float(np.max(np.abs((ifsw + irfsw)[late]))),
            "max_abs_u5_tend_minus_u5_toff": float(np.max(np.abs((tend - toff)[late]))),
            "max_abs_u5_tend_minus_u5_tdelay_sw": float(np.max(np.abs((tend - tdelay)[late]))),
            "mode_ok_min_max": [float(np.min(mode_ok[late])), float(np.max(mode_ok[late]))],
            "u5_toff_sel_min_max": [float(np.min(toff_sel[late])), float(np.max(toff_sel[late]))],
            "u5_sel_toff_min_max": [float(np.min(sel_toff[late])), float(np.max(sel_toff[late]))],
            "gate_l_min_max": [float(np.min(gate[late])), float(np.max(gate[late]))],
            "ssend_min_max": [float(np.min(ssend[late])), float(np.max(ssend[late]))],
        },
        "steady_output": {
            "vout_avg_V": trapezoid(vout[late], t[late]) / (t[late][-1] - t[late][0]),
            "vout_ripple_pp_V": float(np.ptp(vout[late])),
            "inductor_peak_A": float(np.max(il1[late])),
        },
        "cycle_statistics": cycle_statistics,
        "all_candidate_cycle_statistics": all_cycle_statistics,
        "interpretation_limits": [
            "This is a TI macro-model simulation, not a measurement of silicon internals.",
            "Raw 10-V crossings are retained for the original RISE=6001/6101 measurement; hysteretic edges are used only to suppress ringing-induced duplicate cycles.",
            "Cycles with missing, duplicated, or out-of-order input-cross, U5_TOFF, GATE_L, reset, or SW events are reported and excluded from valid-cycle statistics rather than silently discarded.",
            "The comparator output 0.5-V crossing is diagnostic only: the TI macro-model's ideal comparator source switches at U5_N01584 > U5_PVIN, while the output node is shaped by a 1-ohm/1-nF RC that is under-resolved by 25/50-ns sampling. Its interpolated edge is not used to reject a cycle.",
            "The primary comparator-to-delay interval is measured from the smooth U5_N01584-U5_PVIN input crossing to the smooth U5_TOFF 0.5-V crossing; this includes the comparator output RC and the U5_TOFF RC.",
            "The RC ODE uses measured SW(t) as a piecewise-linear input and assumes the 1-Mohm reset path is OFF during the charging interval.",
            "Charge-derived capacitance is reported only when GATE_L stays low throughout the guarded integration window.",
            "U5_IFSW is compared against -I(RFSW); its numeric interpretation as amperes depends on the unity-gain current-sense source in the macro-model.",
            "Compare 50-ns and 25-ns runs by event distributions, not sample-by-sample RAW values, because adaptive time grids differ.",
            "Do not call the FSW mechanism a unique root cause unless direct-node timing, RC charge balance, and solver sensitivity close the residual.",
        ],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "fsw_internal_cycles.csv", rows)
    (args.out / "fsw_internal_summary.json").write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if args.compare_with is not None:
        baseline = json.loads(args.compare_with.read_text(encoding="utf-8"))
        comparison = compare_summaries(summary_data, baseline)
        (args.out / "fsw_internal_comparison.json").write_text(
            json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(summary_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
