"""Analytical sensitivity for V1.2 hold, using only the standard library."""
import argparse
import csv
import math
import sys

CAP_ESR_CASES = {
    "nominal": ([10.0] * 4, [0.075] * 4),
    "tol_-10%": ([9.0] * 4, [0.075] * 4),
    "stress_EOL": ([6.3] * 4, [0.1125] * 4),
    "single_weak_cell": ([6.3, 9.0, 9.0, 9.0], [0.1125, 0.075, 0.075, 0.075]),
}
EFFICIENCIES = (0.90, 0.92, 0.95)
TASK_S = 1.2
CELL_FLOOR_V = 1.0
PACK_THRESHOLDS = (7.0, 7.1, 7.2, 7.3, 7.4, 8.0)
START_STATES = {
    "balanced": [2.35] * 4,
    "illustrative_imbalance": [1.45, 2.65, 2.65, 2.65],
}


def hold_to_terminal(terminal_v, loaded_start_v, loss_rp, power, reciprocal_cap):
    integral = (loaded_start_v**2 - terminal_v**2) / 2
    integral -= loss_rp * math.log(loaded_start_v / terminal_v)
    return integral / (power * reciprocal_cap)


def evaluate(caps, esrs, eta, start_cells):
    pack_ocv = sum(start_cells)
    reciprocal_cap = sum(1 / cap for cap in caps)
    power = 12.0 / (0.99 * eta)
    loss_rp = sum(esrs) * power
    loaded_start = (pack_ocv + math.sqrt(pack_ocv**2 - 4 * loss_rp)) / 2

    def hold(terminal_v):
        return hold_to_terminal(terminal_v, loaded_start, loss_rp, power, reciprocal_cap)

    def cell_terminal(index, pack_v):
        discharged_coulombs = (pack_ocv - pack_v - loss_rp / pack_v) / reciprocal_cap
        return start_cells[index] - discharged_coulombs / caps[index] - power / pack_v * esrs[index]

    def crossing(function, target, lower, upper):
        if function(lower) >= target:
            return lower
        if function(upper) < target:
            raise ValueError("Threshold outside the simulated range")
        for _ in range(50):
            midpoint = (lower + upper) / 2
            if function(midpoint) < target:
                lower = midpoint
            else:
                upper = midpoint
        return (lower + upper) / 2

    # On this branch the pack terminal is monotonic with remaining charge.
    collapse_v = math.sqrt(loss_rp)
    pack_at_task = crossing(lambda v: -hold(v), -TASK_S, collapse_v, loaded_start)
    cell_trip_pack_v = max(
        crossing(lambda v: cell_terminal(i, v), CELL_FLOOR_V, collapse_v, loaded_start)
        for i in range(4)
    )
    min_cell_at_task = min(cell_terminal(i, pack_at_task) for i in range(4))
    for pack_threshold in PACK_THRESHOLDS:
        effective_cutoff = max(pack_threshold, cell_trip_pack_v)
        hold_s = hold(effective_cutoff)
        yield {
            "pack_threshold_V": pack_threshold,
            "pack_at_1p2s_if_uninterrupted_V": round(pack_at_task, 6),
            "min_cell_at_1p2s_if_uninterrupted_V": round(min_cell_at_task, 6),
            "cell_floor_crossing_pack_V": round(cell_trip_pack_v, 6),
            "first_cutoff": "cell" if cell_trip_pack_v > pack_threshold else "pack",
            "hold_s": round(hold_s, 6),
            "margin_s": round(hold_s - TASK_S, 6),
            "pass_1p2s": hold_s >= TASK_S,
        }


def charge_uvlo_rows():
    caps, esrs = CAP_ESR_CASES["stress_EOL"]
    reciprocal_cap = sum(1 / cap for cap in caps)
    power = 12.0 / (0.99 * 0.90)
    loss_rp = sum(esrs) * power
    max_charge_v = 9.4
    lowest_bare_cv = max_charge_v * 0.581 / 0.611
    bare_loaded_start = (lowest_bare_cv + math.sqrt(lowest_bare_cv**2 - 4 * loss_rp)) / 2
    for cutoff in PACK_THRESHOLDS:
        # Solve for loaded V at t=0, then add the initial ESR drop.
        low, high = cutoff, max_charge_v + 2
        for _ in range(50):
            loaded = (low + high) / 2
            if hold_to_terminal(cutoff, loaded, loss_rp, power, reciprocal_cap) < TASK_S:
                low = loaded
            else:
                high = loaded
        initial_ocv = high + loss_rp / high
        yield {
            "cutoff_V": cutoff,
            "min_initial_ocv_V": round(initial_ocv, 6),
            "headroom_to_9p4V_mV": round((max_charge_v - initial_ocv) * 1000, 3),
            "tps54302_bare_worst_cv_V": round(lowest_bare_cv, 6),
            "hold_at_bare_worst_cv_s": round(
                hold_to_terminal(cutoff, bare_loaded_start, loss_rp, power, reciprocal_cap), 6
            ),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charge-uvlo", action="store_true")
    args = parser.parse_args()
    if args.charge_uvlo:
        rows = list(charge_uvlo_rows())
    else:
        rows = [
            {"case": case, "initial_state": state, "boost_eta": eta, **result}
            for case, (caps, esrs) in CAP_ESR_CASES.items()
            for state, start_cells in START_STATES.items()
            for eta in EFFICIENCIES
            for result in evaluate(caps, esrs, eta, start_cells)
        ]
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
