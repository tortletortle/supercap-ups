# LTC3350 candidate model

This directory contains a reproducible first-order feasibility model for an integrated 4S × 10 F supercapacitor UPS candidate.

## Run

~~~bash
python3 sim/ltc3350_reference/evaluate.py
python3 -m unittest discover -s sim/ltc3350_reference -p 'test_*.py' -v
~~~

## What is modeled

- VCAP and VOUT feedback-divider setpoints, including conservative reference, resistor-ratio, and feedback-leakage budgets.
- VSHUNT register quantization and first-order shunt-current / ballast-resistor power estimates, including the data-sheet 75% shunt-duty envelope.
- The separate ~10 mA switched-resistive cell balancer is not simulated; equalized initial cell voltage is an explicit assumption in the weak-cell discharge case.
- LTC3350 two-resistor input-current-limit equation for system-load priority.
- 4S EOL constant-power hold time with series ESR and a loaded-terminal cutoff.
- A separate equalized-start weak-cell discharge case.

## What is not modeled

This is not a switching simulation. It does not prove loop stability, MOSFET/inductor stress, current-limit transient behavior, thermal performance, I²C timing, switchover droop, or hardware cell-UV shutdown. The weak-cell case assumes the internal balancer has equalized the initial cell voltages; the active shunt's charging dynamics are represented only by a current budget.

The candidate values and assumptions are summarized in `hardware/kicad/LTC3350_REFERENCE_ARCHITECTURE.md`.
