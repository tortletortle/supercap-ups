"""Analyze direct internal TPS61088 timing-node probes from LTspice RAW.

This is read-only post-processing. It does not edit a circuit or launch LTspice.
Requires numpy and the sibling analyze_first_case.py RAW reader.

Example:
  py -3 sim/tps61088_v1_4/scripts/analyze_fsw_internal.py --raw <probe.raw> --out <results-dir>
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from analyze_first_case import load_raw


RFSW_OHM = 324e3
CFSW_F = 23e-12
ROFF_OHM = 1e6
EDGE_V = 10.0
CAP_RESET_V = 0.5


def crossings(t, y, level, direction):
    if direction == "rise":
        k = np.flatnonzero((y[:-1] < level) & (y[1:] >= level))
    elif direction == "fall":
        k = np.flatnonzero((y[:-1] >= level) & (y[1:] < level))
    else:
        raise ValueError("direction must be rise or fall")
    dy = y[k + 1] - y[k]
    return t[k] + (level - y[k]) / dy * (t[k + 1] - t[k])


def sample(t, y, when):
    return float(np.interp(when, t, y))


def first_between(events, start, end):
    q = events[(events > start) & (events < end)]
    return float(q[0]) if len(q) else None


def summary(values):
    x = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if not len(x):
        return None
    return {
        "count": int(len(x)),
        "min": float(np.min(x)),
        "median": float(np.median(x)),
        "mean": float(np.mean(x)),
        "max": float(np.max(x)),
        "std": float(np.std(x)),
    }


def write_csv(path, rows):
    if not rows:
        raise ValueError("No complete switching cycles found in requested window")
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--start", type=float, default=0.024, help="analysis start time in seconds")
    p.add_argument("--end", type=float, default=0.026, help="analysis end time in seconds")
    args = p.parse_args()

    header, names, raw = load_raw(args.raw)
    idx = {n.strip().lower(): i for i, n in enumerate(names)}

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
        available = [n for n in names if ":" in n.lower()]
        raise ValueError(
            "Missing hierarchical RAW vectors: " + ", ".join(missing) +
            ". Check the LTspice .save hierarchy syntax and Save Subcircuit Node Voltages. "
            "Available hierarchical vectors: " + ", ".join(available[:80])
        )

    def vec(name):
        return np.asarray(raw[:, idx[name]], dtype=float)

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

    if not np.all(np.diff(t) >= 0):
        raise ValueError("RAW time vector is not monotonic")
    if args.end <= args.start:
        raise ValueError("--end must be greater than --start")

    sw_rise = crossings(t, sw, EDGE_V, "rise")
    sw_fall = crossings(t, sw, EDGE_V, "fall")
    cap_minus_pvin_rise = crossings(t, cap - pvin, 0.0, "rise")
    cap_reset = crossings(t, cap, CAP_RESET_V, "fall")
    gate_rise = crossings(t, gate, 0.5, "rise")
    comparator_rise = crossings(t, comparator_out, 0.5, "rise")
    toff_rise = crossings(t, toff, 0.5, "rise")
    vout_98 = crossings(t, vout, 11.76, "rise")

    rows = []
    for n, up in enumerate(sw_rise):
        if not (args.start <= up < args.end):
            continue
        next_up = float(sw_rise[n + 1]) if n + 1 < len(sw_rise) else args.end
        down = first_between(sw_fall, up, next_up)
        if down is None:
            continue
        cross = first_between(cap_minus_pvin_rise, up, down)
        if cross is None:
            continue
        reset = first_between(cap_reset, cross, down)
        comp_on = first_between(comparator_rise, cross, down)
        toff_on = first_between(toff_rise, comp_on if comp_on is not None else cross, down)
        gate_on = first_between(gate_rise, cross, down)

        q = (t >= up + 30e-9) & (t <= down - 30e-9)
        if np.count_nonzero(q) < 3:
            continue
        charge_current = -irfsw[q] - cap[q] / ROFF_OHM
        delta_cap = float(cap[q][-1] - cap[q][0])
        c_est = float(np.trapezoid(charge_current, t[q]) / delta_cap) if abs(delta_cap) > 1e-9 else None

        pre_cross = (t >= up) & (t <= cross)
        sw_avg = float(np.trapezoid(sw[pre_cross], t[pre_cross]) /
                        (t[pre_cross][-1] - t[pre_cross][0])) if np.count_nonzero(pre_cross) > 1 else None
        v0 = sample(t, cap, up)
        vth = sample(t, pvin, cross)
        v_inf = sw_avg * ROFF_OHM / (RFSW_OHM + ROFF_OHM) if sw_avg is not None else None
        ramp_pred = None
        if v_inf is not None and v_inf > vth > v0:
            r_eq = 1.0 / (1.0 / RFSW_OHM + 1.0 / ROFF_OHM)
            ramp_pred = float(-r_eq * CFSW_F * np.log((v_inf - vth) / (v_inf - v0)))

        rows.append({
            "cycle_start_s": up,
            "period_s": next_up - up,
            "sw_high_s": down - up,
            "pvin_cross_s": cross,
            "sw_rise_to_pvin_cross_s": cross - up,
            "cross_to_comparator_output_rise_s": comp_on - cross if comp_on is not None else None,
            "comparator_output_rise_to_u5_toff_0p5V_s": toff_on - comp_on if toff_on is not None and comp_on is not None else None,
            "cross_to_u5_toff_0p5V_s": toff_on - cross if toff_on is not None else None,
            "cross_to_gate_l_rise_s": gate_on - cross if gate_on is not None else None,
            "u5_toff_0p5V_to_gate_l_rise_s": gate_on - toff_on if gate_on is not None and toff_on is not None else None,
            "gate_l_rise_to_cap_reset_0p5V_s": reset - gate_on if reset is not None and gate_on is not None else None,
            "cross_to_cap_reset_0p5V_s": reset - cross if reset is not None else None,
            "cross_to_sw_fall_s": down - cross,
            "cap_reset_to_sw_fall_s": down - reset if reset is not None else None,
            "comparator_output_rise_to_sw_fall_s": down - comp_on if comp_on is not None else None,
            "pvin_at_cross_V": vth,
            "cap_at_sw_rise_V": v0,
            "sw_high_pre_cross_avg_V": sw_avg,
            "rc_ramp_prediction_s": ramp_pred,
            "rc_ramp_residual_s": ramp_pred - (cross - up) if ramp_pred is not None else None,
            "C_est_from_charge_F": c_est,
            "C_est_error_pct": 100 * (c_est / CFSW_F - 1) if c_est is not None else None,
            "cap_minus_fsw_at_cross_V": sample(t, cap - fsw, cross),
            "ifsw_plus_rfsw_current_at_cross": sample(t, ifsw + irfsw, cross),
            "u5_tsw_at_cross_s": sample(t, tsw, cross),
            "u5_tdelay_sw_at_cross_s": sample(t, tdelay, cross),
            "u5_toff_at_cross": sample(t, toff, cross),
            "u5_tend_at_cross": sample(t, tend, cross),
            "gate_l_at_cross": sample(t, gate, cross),
            "ssend_at_cross": sample(t, ssend, cross),
            "mode_ok_at_cross": sample(t, mode_ok, cross),
            "sel_toff_at_cross": sample(t, sel_toff, cross),
            "toff_sel_at_cross": sample(t, toff_sel, cross),
            "toff_sel_1_at_cross": sample(t, toff_sel_1, cross),
            "comparator_out_at_cross": sample(t, comparator_out, cross),
        })

    if not rows:
        raise ValueError("No cycles contained SW rise, direct U5_PVIN crossing and SW fall")

    late = (t >= args.start) & (t <= args.end)
    t6001 = float(sw_rise[6000]) if len(sw_rise) >= 6001 else None
    t6101 = float(sw_rise[6100]) if len(sw_rise) >= 6101 else None
    t98 = float(vout_98[0]) if len(vout_98) else None
    frequency = 100.0 / (t6101 - t6001) / 1e3 if t6001 is not None and t6101 is not None else None

    numeric_fields = [k for k in rows[0] if k != "cycle_start_s"]
    cycle_stats = {k: summary([r[k] for r in rows]) for k in numeric_fields}
    summary_data = {
        "raw_path": str(args.raw.resolve()),
        "raw_point_count": int(len(t)),
        "raw_variables": names,
        "analysis_window_s": [args.start, args.end],
        "complete_cycles": len(rows),
        "prescribed_edge_measurement": {
            "raw_10V_rise_count": int(len(sw_rise)),
            "t98_s": t98,
            "sw_t6001_s": t6001,
            "sw_t6101_s": t6101,
            "frequency_kHz": frequency,
            "timing_valid": bool(t98 is not None and t6001 is not None and t6101 is not None and t98 < t6001 < t6101 < t[-1]),
        },
        "direct_internal_consistency": {
            "max_abs_cap_minus_fsw_V": float(np.max(np.abs(cap[late] - fsw[late]))),
            "max_abs_ifsw_plus_rfsw_current": float(np.max(np.abs(ifsw[late] + irfsw[late]))),
            "mode_ok_min_max": [float(np.min(mode_ok[late])), float(np.max(mode_ok[late]))],
            "ssend_min_max": [float(np.min(ssend[late])), float(np.max(ssend[late]))],
        },
        "steady_output": {
            "vout_avg_V": float(np.trapezoid(vout[late], t[late]) / (t[late][-1] - t[late][0])),
            "vout_ripple_pp_V": float(np.ptp(vout[late])),
            "inductor_peak_A": float(np.max(il1[late])),
        },
        "cycle_statistics": cycle_stats,
        "interpretation_limits": [
            "This is a TI macro-model simulation, not a measurement of silicon internals.",
            "The 25 ns deck changes only maximum timestep; compare its cycle statistics with the 50 ns deck.",
            "The RC prediction assumes constant average SW voltage over the pre-threshold ramp.",
            "The charge-derived capacitance excludes 30 ns at both SW transitions and assumes the 1 Mohm off-state path is active.",
            "Do not call the FSW mechanism a unique root cause unless the direct-node and timestep results close the remaining residual.",
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "fsw_internal_cycles.csv", rows)
    (args.out / "fsw_internal_summary.json").write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
