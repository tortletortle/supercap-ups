"""Ideal measured-terminal CC/CV policy with a latched tail and per-cell OVP."""
import argparse
import csv
from itertools import product
from math import exp
import sys

from run_charge_window import BALANCE_R, UVLO, hold

CELL_OVP = 2.449
BOOST_POWER = 12.145 / 0.85
REST_S = 60
STOP_A = 0.005


def run(ratio, esr, threshold, cv, step):
    caps = [11.2, *([11.2 * ratio] * 3)]
    cells = [0.0] * 4
    alpha = BALANCE_R / (BALANCE_R + esr)
    tail = False
    handoff = None
    peak = 0.0
    for tick in range(round(1500 / step)):
        limit = 0.05 if tail else 0.5
        cv_current = (cv / alpha - sum(cells)) / (len(cells) * esr)
        current = max(0.0, min(limit, cv_current))
        terminals = [alpha * (cell + current * esr) for cell in cells]
        peak = max(peak, max(terminals))
        if max(terminals) >= CELL_OVP:
            return "cell_ovp", handoff, tick * step, peak, sum(cells), None, None
        if not tail and sum(terminals) >= threshold:
            tail = True
            handoff = tick * step
            current = min(current, 0.05)
            terminals = [alpha * (cell + current * esr) for cell in cells]
        if current <= STOP_A:
            break
        cells = [cell + step * (current - terminal / BALANCE_R) / cap
                 for cell, terminal, cap in zip(cells, terminals, caps)]
    else:
        raise RuntimeError("Charge did not terminate within the model time window")
    # Exact relaxation with no external load, retaining only the four bleed resistors.
    rested = [cell * exp(-REST_S / ((BALANCE_R + esr) * cap))
              for cell, cap in zip(cells, caps)]
    seconds = hold(rested, caps, UVLO[1], 0.1, cell_esr=esr, power=BOOST_POWER)
    return "complete", handoff, tick * step, peak, sum(cells), sum(rested), seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=float, default=0.1)
    args = parser.parse_args()
    if not 0 < args.step <= 0.1:
        parser.error("--step must be in (0, 0.1] seconds")
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("capacity_ratio", "cell_esr_ohm", "measured_handoff_V", "CV_V",
                     "charge_result", "handoff_s", "stop_s", "peak_cell_V",
                     "stop_OCV_V", "rest_60s_OCV_V", "backup_s"))
    for ratio, esr, threshold, cv in product(
        (1.0, 1.08, 1.12), (0.053, 0.106), (8.85, 8.95, 9.05, 9.15), (9.058, 9.0921)
    ):
        outcome = run(ratio, esr, threshold, cv, args.step)
        writer.writerow((ratio, esr, threshold, cv, *(
            round(value, 6) if isinstance(value, float) else value for value in outcome
        )))


if __name__ == "__main__":
    main()
