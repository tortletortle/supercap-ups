# BQ76905 CELL_PERMIT timing model

This folder contains an independent Python engineering model for the 4S BQ76905 undervoltage-permit path.

## Run

```bash
python3 sim/cell_permit/model.py --out-dir sim/cell_permit
python3 -m unittest discover -s sim/cell_permit -p 'test_*.py' -v
```

## Artifacts

- `model.py`: ADSCAN timing, RC/gate estimates, COW pulse timing, fail-closed permit logic.
- `test_model.py`: 19 unit/logic tests.
- `parameters.json`: baseline, candidate settings and evidence boundaries.
- `register_config.csv`: proposed BQ76905 register values.
- `scan_scenarios.csv`: legacy, fast, medium-fast, slow and LOOP_SLOW scenarios.
- `timing_budget.csv`: fast candidate time budget.
- `fault_matrix.csv`: fault injection matrix.
- `waveform_fast_candidate.csv`: modeled weak-cell UV waveform under fast scan.
- `waveform_half_loop_failure.csv`: modeled >5ms case with half-speed scan.
- `waveform_mediumfast_failure.csv`: modeled >5ms case with medium-fast scan.
- `gate_turnoff_rc.cir`: simplified P-MOS gate RC deck; not a BQ76905 or vendor MOSFET model.

## Evidence boundary

The model is not a TI BQ76905 behavioral model and not hardware evidence. The branch CI workflow installs ngspice and runs only the simplified gate RC deck; this is not a Si7149DP vendor transient model or a BQ76905 simulation. ADC conversion times are typical values; the oscillator drift adjustment is characterization-derived, not a production guaranteed ADSCAN maximum. ALERT propagation has no published maximum used here. The P-MOS gate model is an equivalent-C estimate based on Qg, not a vendor transient simulation. The COW current is typical-only and the open-wire estimate is not a maximum.

The 5ms result of the fast candidate is an engineering estimate (about 4.265ms), **not a hard pass**. Do not use it to approve PCB release or claim a guaranteed 5ms cutoff.
