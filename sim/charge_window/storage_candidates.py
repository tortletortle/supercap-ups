"""Compare storage options using the same loaded UVLO and boost floor."""
import argparse
import csv
import sys

from run_charge_window import UVLO, bisect_rising, charge, hold

INITIAL_PACK_VOLTAGES = (8.8, 9.0, 9.2825)
LOAD_A = 1.0
LOAD_V = 12.0
OUT_PATH_OHM = 0.145
TARGET_SECONDS = 1.2

# DC ESR multipliers are sensitivity assumptions. Eaton specifies lifetime AC ESR.
OPTIONS = (
    ("10F_baseline", 6.30, 0.1125, 0.1125),
    ("HVH_12F", 12 * 0.8 * 0.7, 0.060, 0.120),
    ("HVH_15F", 15 * 0.8 * 0.7, 0.068, 0.136),
    ("HVH_20F", 20 * 0.8 * 0.7, 0.053, 0.106),
)


def results():
    for initial_pack_v in INITIAL_PACK_VOLTAGES:
        start_cells = [initial_pack_v / 4] * 4
        yield from compare_at_voltage(initial_pack_v, start_cells)


def compare_at_voltage(initial_pack_v, start_cells):
    for name, cell_f, initial_esr, stress_esr in OPTIONS:
        for label, esr in (("initial_esr", initial_esr), ("stress_esr", stress_esr)):
            for path_r in (0.020, 0.050, 0.100):
                for efficiency in (0.85, 0.90):
                    power = (LOAD_V * LOAD_A + LOAD_A**2 * OUT_PATH_OHM) / efficiency
                    seconds = hold(
                        start_cells, [cell_f] * 4, UVLO[1], path_r,
                        cell_esr=esr, power=power,
                    )
                    required_f = cell_f * TARGET_SECONDS / seconds if seconds else None
                    yield (
                        name, label, round(cell_f, 6), esr, path_r, efficiency, initial_pack_v,
                        round(seconds, 6), round(required_f, 6) if required_f is not None else "",
                    )


def charge_matching_results(pack_target):
    cell_f = 11.2
    cell_esr = 0.106
    power = (LOAD_V * LOAD_A + LOAD_A**2 * OUT_PATH_OHM) / 0.85
    ovp_min = 2.449
    for current in (0.05, 0.5):
        def charge_at_ratio(ratio):
            caps = [cell_f, *([cell_f * ratio] * 3)]
            return charge(caps, pack_target, ovp_min, cell_esr=cell_esr, current=current)

        max_ratio = bisect_rising(lambda ratio: charge_at_ratio(ratio)[2], True, 1, 1.5)
        for ratio in (1, 1.08, 1.10, 1.12, 1.5):
            caps = [cell_f, *([cell_f * ratio] * 3)]
            cells, _, tripped = charge_at_ratio(ratio)
            seconds = hold(cells, caps, UVLO[1], 0.1, cell_esr=cell_esr, power=power)
            yield (current, round(max_ratio, 6), ratio, round(sum(cells), 6),
                   tripped, round(seconds, 6))


def taper_results():
    cell_esr = 0.106
    ovp_min = 2.449
    for ratio in (1.0, 1.08, 1.12):
        caps = [11.2, *([11.2 * ratio] * 3)]
        for handoff_ocv in (8.8, 8.9, 9.0, 9.1):
            cells, fast_peak, fast_trip = charge(
                caps, handoff_ocv, ovp_min, cell_esr=cell_esr, current=0.5,
            )
            if fast_trip:
                yield ratio, handoff_ocv, round(fast_peak, 6), True, "", "", ""
                continue
            final_cells, tail_peak, tail_trip = charge(
                caps, 9.092, ovp_min, cell_esr=cell_esr, current=0.05, start_cells=cells,
            )
            yield (ratio, handoff_ocv, round(fast_peak, 6), False,
                   round(sum(final_cells), 6), round(tail_peak, 6), tail_trip)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--matching", action="store_true")
    mode.add_argument("--taper", action="store_true")
    parser.add_argument("--target", type=float, default=9.0, help="Charge matching target OCV")
    args = parser.parse_args()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    if args.taper:
        writer.writerow(("capacity_ratio", "fast_handoff_OCV_V", "fast_peak_cell_V",
                         "fast_OVP", "tail_final_OCV_V", "tail_peak_cell_V", "tail_OVP"))
        writer.writerows(taper_results())
        return
    if args.matching:
        writer.writerow(("charge_A", "max_capacity_ratio_to_reach_target", "capacity_ratio",
                         "achieved_pack_OCV_V", "early_OVP", "hold_s"))
        writer.writerows(charge_matching_results(args.target))
        return
    writer.writerow(("candidate", "esr_case", "cell_F", "cell_DC_ESR_ohm", "pack_path_ohm",
                     "boost_efficiency", "initial_pack_V", "hold_s", "min_cell_F_for_1p2s"))
    writer.writerows(results())


if __name__ == "__main__":
    main()
