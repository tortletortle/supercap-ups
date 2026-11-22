"""Reproduce the 4S passive-bleed sizing and fast-charge counterexample."""
from itertools import product
from math import expm1, log

PACK_TARGET = 9.4
CELL_REFERENCE = 2.7
C_NOMINAL = 10.0
R_NOMINAL = 2200.0
R_TOLERANCE = 0.01
LEAKAGE_25C_AT_72H = 30e-6


def steady_cells(pack_voltage, resistors, leakages):
    """Series branch current is common. Capacitances are open at steady state."""
    current = (pack_voltage + sum(r * i for r, i in zip(resistors, leakages))) / sum(resistors)
    return [r * (current - leakage) for r, leakage in zip(resistors, leakages)]


def constant_current_cells(seconds, amperes, capacitors):
    """Initially empty cells with equal bleed resistors and no ESR or native leakage."""
    return [-amperes * R_NOMINAL * expm1(-seconds / (R_NOMINAL * c)) for c in capacitors]


def bisect_time(threshold, metric):
    low, high = 0.0, 1.0
    while metric(high) < threshold:
        high *= 2
    for _ in range(60):
        middle = (low + high) / 2
        if metric(middle) < threshold:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def main():
    limits = (R_NOMINAL * (1 - R_TOLERANCE), R_NOMINAL * (1 + R_TOLERANCE))
    nominal_cell = PACK_TARGET / 4
    steady = [
        voltage
        for r in product(limits, repeat=4)
        for leakage in product((0.0, LEAKAGE_25C_AT_72H), repeat=4)
        for voltage in steady_cells(PACK_TARGET, r, leakage)
    ]
    print(f"Steady cell voltage @9.4V, 256 corners: {min(steady):.4f} to {max(steady):.4f} V")
    print(f"Nominal resistor chain: {1000 * nominal_cell / R_NOMINAL:.3f} mA, "
          f"{4000 * nominal_cell**2 / R_NOMINAL:.2f} mW from pack")
    print(f"Nominal RC time constant: {R_NOMINAL * C_NOMINAL / 3600:.2f} h, "
          f"9.4V to 7V via bleeders alone: {R_NOMINAL * C_NOMINAL * log(9.4 / 7) / 3600:.2f} h")
    for capacitors in ((9, 13, 13, 13), (6.3, 9, 9, 9)):
        for current in (0.05, 0.2, 0.5, 1.0):
            def cells(seconds):
                return constant_current_cells(seconds, current, capacitors)

            stop = bisect_time(PACK_TARGET, lambda seconds: sum(cells(seconds)))
            cell_limit = bisect_time(CELL_REFERENCE, lambda seconds: max(cells(seconds)))
            print(f"C={capacitors}, I={current:.2f} A: "
                  f"weak cell at 9.4V = {max(cells(stop)):.4f} V; "
                  f"pack at first 2.7V cell = {sum(cells(cell_limit)):.4f} V")


if __name__ == "__main__":
    main()
