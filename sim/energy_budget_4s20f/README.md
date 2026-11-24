# 4S × 20F Eaton UPS energy budget

**Branch:** `energy-budget-4s20f-reconciliation`  
**Common baseline:** `360508c08f23f63cdd74fba7e0c201b0907d3825`  
**Storage candidate:** Eaton `HVH1230-2R7206-R`  
**Scope:** storage energy, per-cell discharge, Boost input boundary, load-side voltage and transfer sensitivity. No charger, eFuse, mux, Boost power-stage, or cell-protection implementation changes.

## Reproduction

From the repository root:

```bash
python3 -m unittest discover -s sim/energy_budget_4s20f -p 'test_model.py' -v
python3 sim/energy_budget_4s20f/run_study.py --out sim/energy_budget_4s20f/results
python3 sim/energy_budget_4s20f/run_spice.py \
  --ngspice ngspice \
  --decks sim/energy_budget_4s20f/results/netlists \
  --out sim/energy_budget_4s20f/spice_artifacts
```

The model uses only the Python standard library. The SPICE decks are averaged constant-power storage models; they do not include the TPS61088 switching macro-model or a physical protection switch. The weak-cell deck measures the first CUV crossing; the Python model separately stops at CUV and supports an explicit post-threshold isolation-delay sensitivity.

## Historical reproduction

| Case | Cell C | Cell ESR | Boost efficiency | Input path | Hold time | Result |
|---|---:|---:|---:|---:|---:|---|
| Baseline | 11.2 F | 106 mΩ | 85% | 100 mΩ | **1.374802577 s** | Passes 1.2 s in this model |
| Joint degradation | 10.8 F | 110 mΩ | 83% | 120 mΩ | **1.146228787 s** | Fails by 53.771 ms |
| Separate 1.144457 row | 11.2 F | 106 mΩ | 83% | 150 mΩ | **1.144456832 s** | Different parameter combination |

All three use 9.0 V rested pack OCV, 145 mΩ output path, 12 W / 12 V / 1 A at the load, and a 7.0 V Boost-input floor. The separate 1.144457 s result is not a second reproduction of the 10.8 F / 110 mΩ / 120 mΩ case.

The historical output power budget is:
- Boost output: 12 W + (1 A)² × 145 mΩ = 12.145 W.
- Boost input at 85% assumed efficiency: 14.288235 W.
- Series capacitance: 2.8 F.
- Cell ESR sum + input path: 524 mΩ.

## Per-cell protection result

A 9.0 V pack can still contain a weak cell. For the initial-voltage stress case 1.45 V + 3 × 2.516667 V, the weakest cell reaches the provisional 1.05 V CUV at **1.135936729 s**, while Boost VIN is still about 7.202 V and PACK_4S is still about 7.400 V. CUV therefore preempts the 7.0 V Boost floor.

Combining that weak-cell initial condition with 10.8 F / 110 mΩ, 83% Boost efficiency and 120 mΩ input path reduces the modeled interval to **0.977392332 s**. A 4.06 ms post-CUV isolation delay is included only as a sensitivity case; it is not a guaranteed or measured maximum.

## Load-side voltage is a separate gate

The historical 1.374803 s reproduction assumes 12.0 V / 1.0 A at LOAD_12V. With 145 mΩ output path, that requires a **12.145 V Boost output setpoint**.

If the implemented Boost setpoint is 12.0 V instead:
- At fixed 1 A, LOAD_12V is 11.855 V and the load receives 11.855 W.
- At a 12 W constant-power load, the solution is about 11.853204 V / 1.012384 A. It receives 12 W, but the load-voltage acceptance is unknown.

The load's minimum/maximum voltage and allowed interruption time have not been specified, so no load-voltage pass is claimed.

## Transfer sensitivity

The model keeps the storage energy clock separate from the load-backup clock. The storage clock begins when the rested capacitor pack starts supplying the Boost. The actual load clock must begin when LOAD_12V first receives valid backup power after MUX transfer.

Assuming 12 W constant-power load and 11.8532 V initial load voltage, a 50 µs transfer with 47 µF physically at LOAD_12V gives about 1.077 V ideal capacitive droop. The 47 µF Boost output capacitor is not proven to be effective load-side hold-up capacitance. A cold-start delay of 11.28 ms is a macro-model observation, not a guaranteed maximum; bridging it with only 0.5 V droop at about 1.012 A would require roughly 22.8 mF at the load.

## Critical single-variable boundaries

The generated `scans/critical_parameter_table.csv` reports mathematical 1.2 s boundaries with every other baseline input fixed. Expected checkpoints are approximately:
- Minimum cell capacitance: 9.77595 F.
- Maximum cell DC ESR: 119.743 mΩ.
- Minimum Boost efficiency: 80.121%.
- Maximum input path: 154.973 mΩ.
- Maximum output path (energy-only): 884.582 mΩ.
- Minimum initial pack OCV: 8.88863 V.
- Maximum balanced-cell Cmax/Cmin ratio: 1.58268.

These are not recommended design targets or production guarantees. In particular, the output-path energy-only boundary does not include the load's voltage window.

## Component and evidence boundaries

Eaton ELX1538 lists the HVH1230-2R7206-R as 20 F, ±20%, 2.7 V, with 53 mΩ maximum DC ESR at +25 °C, 35 mΩ maximum 1 kHz ESR, 1.92 A continuous current at 15 °C rise and 13 A pulse current for the specified 1 s test. The 11.2 F cell value is 20 F × 0.8 × 0.7. The 106 mΩ value is 2 × 53 mΩ used as a stress assumption; Eaton's life table specifies AC ESR change and does not provide a guaranteed EOL DC ESR(T) curve. Standard operation is -40 to +70 °C; +85 °C operation requires linear voltage derating to 2.5 V/cell.

TI lists TPS61088 input range as 2.7–12 V. The project's 7.0 V Boost floor is a conservative qualification/evidence boundary, **not** the IC's datasheet UVLO minimum. The repository TPS61088 macro-model's reported 98.889–99.364% efficiency is from short 18 ms windows; it is not continuous 1.2 s or hardware efficiency. The 85% assumption is retained as a conservative scenario and is scanned rather than treated as a verified efficiency.

Sources:
- Eaton ELX1538: https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-hvh-supercapacitors-cylindrical-cells-high-density-data-sheet-elx1538-en.pdf
- TI TPS61088 datasheet: https://www.ti.com/lit/ds/symlink/tps61088.pdf

## Release status

- Python analytical/RK4 behavior model: implemented; regression tests in `test_model.py`.
- Generated scan tables and CSV waveforms: produced by `run_study.py`.
- ngspice cross-check: generated decks and runner are provided; SPICE pass is claimed only after CI/local ngspice completes.
- Continuous switching-level 1.2 s simulation: not demonstrated.
- Bench runtime, cell ESR(T), thermal rise, physical CUV-to-isolation delay, load-voltage window and load-side hold-up: not tested.
