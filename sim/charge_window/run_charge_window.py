"""Static CV/UVLO budget and zero-start charge mismatch study."""
import argparse
import csv
import math
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protection_budget"))
from evaluate import hold_to_terminal

POWER = 12 / (0.90 * 0.99)
ESR = 0.1125
UVLO = (6.839892, 7.110123)
CELL_FLOOR = 1.0
CURRENT = 0.5
BALANCE_R = 2200.0
PACK_MAX = 9.4


def bisect_rising(function, target, lo, hi):
    for _ in range(60):
        mid = (lo + hi) / 2
        if function(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hold(start_cells, caps, cutoff, path_r, *, cell_esr=ESR, power=POWER):
    inv_c = sum(1 / c for c in caps)
    ocv = sum(start_cells)
    rp = (len(caps) * cell_esr + path_r) * power
    # TPS3700 senses the pack before the series path. Translate that
    # threshold to Boost input voltage for the constant-power solution.
    cutoff = (cutoff + math.sqrt(cutoff**2 - 4 * path_r * power)) / 2
    # Credit only the TPS61088 operating range covered by prior evidence.
    cutoff = max(7.0, cutoff)
    loaded = (ocv + math.sqrt(ocv**2 - 4 * rp)) / 2
    if loaded <= cutoff:
        return 0.0

    def min_cell(pack):
        charge = (ocv - pack - rp / pack) / inv_c
        return min(v - charge / c - power / pack * cell_esr for v, c in zip(start_cells, caps))

    if min_cell(loaded) <= CELL_FLOOR:
        return 0.0
    if min_cell(cutoff) <= CELL_FLOOR:
        cutoff = bisect_rising(min_cell, CELL_FLOOR, cutoff, loaded)
    return hold_to_terminal(cutoff, loaded, rp, power, inv_c)


def cv_rows():
    caps = [6.3] * 4
    bare_min = 0.581 * (1 + 14.2 * 0.999 / 1.001)
    for cutoff in UVLO:
        for path_r in (0.0, 0.020, 0.035, 0.050, 0.100):
            required = bisect_rising(lambda v: hold([v/4]*4, caps, cutoff, path_r), 1.2, 8.0, 10.2)
            for setpoint in (bare_min, 9.25, 9.2825, 9.30, 9.3175, 9.35, 9.40):
                yield (
                    cutoff, path_r, setpoint, hold([setpoint/4]*4, caps, cutoff, path_r),
                    required, (PACK_MAX-required)/2,
                )


def charge(caps, ocv_target, ovp, *, cell_esr=ESR, current=CURRENT, start_cells=None):
    if start_cells is None:
        start_cells = [0] * len(caps)

    # Ideal CC test: exact RC solution for each cell, with Rbal across
    # (ESR + C). Pre-charge and discharge use capacitor internal voltage.
    def cell_voltages(seconds):
        return [
            initial + (current * BALANCE_R - initial)
            * -math.expm1(-seconds / (cap * (BALANCE_R + cell_esr)))
            for cap, initial in zip(caps, start_cells)
        ]

    def terminals(seconds):
        return [
            (v + current * cell_esr) * BALANCE_R / (BALANCE_R + cell_esr)
            for v in cell_voltages(seconds)
        ]

    equilibrium_v = current * BALANCE_R
    if not 0 < ocv_target < len(caps) * equilibrium_v:
        raise ValueError("Target must be below the steady-state pack voltage")
    # At this bound even the slowest cell reaches its equal share of the target.
    upper_time = -max(caps) * (BALANCE_R + cell_esr) * math.log1p(
        -ocv_target / (len(caps) * equilibrium_v)
    )
    t_target = bisect_rising(lambda t: sum(cell_voltages(t)), ocv_target, 0, upper_time)
    tripped = max(terminals(t_target)) > ovp
    stopped = bisect_rising(lambda t: max(terminals(t)), ovp, 0, t_target) if tripped else t_target
    return cell_voltages(stopped), max(terminals(stopped)), tripped


def match_rows():
    weak_cap = 6.3
    for ocv_target in (9.264, 9.30, 9.35, 9.40):
        for ovp in (2.50, 2.60):
            # For any cells in [Cmin, Cmax], worst corner for a cell's
            # share is one Cmin with the other three at Cmax.
            limit = bisect_rising(
                lambda ratio: charge([weak_cap, *([weak_cap * ratio] * 3)], ocv_target, ovp)[2],
                True, 1.0, 2.0,
            )
            for ratio in (1.0, 1.05, 1.10, 1.20, 13/9):
                caps = [weak_cap, *([weak_cap * ratio] * 3)]
                cells, peak, trip = charge(caps, ocv_target, ovp)
                yield (
                    ocv_target, ovp, limit, ratio, sum(cells), min(cells), peak, trip,
                    hold(cells, caps, UVLO[1], 0.0), hold(cells, caps, UVLO[1], 0.05),
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", choices=("cv", "match"))
    args = parser.parse_args()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    if args.study == "cv":
        writer.writerow(("fall_V", "additional_path_R_ohm", "initial_OCV_V", "hold_s",
                         "min_initial_OCV_V", "max_symmetric_CV_error_V"))
        rows = cv_rows()
    else:
        writer.writerow(("target_OCV_V", "nominal_cell_OVP_V", "max_Cmax_to_Cmin_ratio",
                         "actual_Cmax_to_Cmin_ratio", "available_initial_OCV_V", "lowest_cell_OCV_V",
                         "max_charge_cell_terminal_V", "early_cell_trip", "hold_no_extra_R_s",
                         "hold_with_50mohm_extra_R_s"))
        rows = match_rows()
    for row in rows:
        writer.writerow([round(value, 6) if isinstance(value, float) else value for value in row])


if __name__ == "__main__":
    main()
