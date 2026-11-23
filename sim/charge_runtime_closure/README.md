# P0 charge-voltage / hold-up closure

**Status:** analytical reconciliation only. This report does not approve a charger redesign, freeze component values, or claim switching/hardware validation.

## Executive result

The current 4S HCC design has a material charge-voltage versus backup-runtime conflict.

The corrected EOL pack model uses:

| Parameter | Value | Basis |
|---|---:|---|
| Cell nominal capacitance | 10 F | HCC HCAP-C 2R7 106 |
| Minimum initial capacity factor | 0.90 | -10% tolerance |
| EOL capacity retention | 0.70 | 30% capacity fade |
| EOL cell capacitance | 6.3 F | 10 × 0.90 × 0.70 |
| Initial cell DC ESR | 65 mΩ | HCC manufacturer specification, 0.2 A |
| EOL ESR multiplier | 2.0 | HCC life limit |
| EOL cell DC ESR | 130 mΩ | 65 × 2 |
| 4S equivalent capacitance | 1.575 F | 6.3 / 4 |
| 4S pack DC ESR | 520 mΩ | 130 × 4 |
| Loaded pack cutoff | 7.0 V | Existing project candidate |
| Output load | 12 W | 12 V / 1 A |
| Path efficiency | 99% | Fixed model assumption |
| Boost efficiency | 90%, 92%, 94% | Sensitivity assumptions |
| Required hold time | 1.2 s | Project target |

The 112.5 mΩ/cell EOL ESR still present in legacy sim/sweep.py and sim/protection_budget/evaluate.py is not the corrected HCC manufacturer-derived EOL value. This branch leaves those legacy scripts untouched and provides an isolated corrected closure model; they must not be treated as interchangeable.

## Recomputed runtime

The exact constant-power/series-ESR model gives:

| Assumed initial pack OCV | 90% Boost | 92% Boost | 94% Boost |
|---:|---:|---:|---:|
| 8.815 V | 0.711 s | 0.748 s | 0.784 s |
| 9.059 V | 0.942 s | 0.984 s | 1.026 s |
| 9.305 V | 1.182 s | 1.230 s | 1.278 s |
| 9.400 V | 1.276 s | 1.327 s | 1.377 s |

These are hypothetical initial **pack open-circuit voltages**, not measurements. The three 8.815/9.059/9.305 V points correspond approximately to the documented static TPS54302 Buck-output corners. The Buck output is upstream of D101 and the charge-current shunt. Therefore treating the Buck output as the pack OCV assumes zero series drop and is an optimistic upper bound; actual pack voltage must be measured at the capacitor terminals after charge current has tapered and the pack has rested.

At the documented nominal Buck output of about 9.059 V, even that optimistic assumption yields only about **0.984 s at 92% Boost efficiency**. At the low Buck-output corner, the optimistic upper bound is about **0.748 s**. The existing charge design therefore cannot guarantee the 1.2 s target.

## Independent cell OVP versus capacity mismatch

The HCC capacitor data sheet's initial capacity tolerance is -10% / +30%. If one cell is at the low-capacity end and the other three are at the high-capacity end, the EOL capacities after applying the same 30% life-capacity fade are 6.3 F and 9.1 F. In a series string, each cell receives the same charge. The lowest-capacitance cell therefore reaches its voltage limit first.

For the illustrative 6.3 F + 3 × 9.1 F EOL string:

| First-trip cell voltage | Pack OCV when that cell first reaches the threshold | Pack equivalent capacitance | 92% model result |
|---:|---:|---:|---|
| 2.5 V | 7.692 V | 2.0475 F | Loaded pack starts at about 6.664 V, already below the 7.0 V cutoff; no valid backup interval |
| 2.7 V | 8.308 V | 2.0475 F | About 0.368 s before the loaded pack reaches 7.0 V |

At the 9.276 V pack OCV required for 1.2 s at 92% assumed Boost efficiency, this weak cell would reach about **3.015 V** in the same ideal series-charge mismatch model. At 9.4 V it would reach about **3.055 V**. Both exceed the 2.7 V rated cell voltage, let alone the manufacturer's lower recommended series-use voltage.

The existing 2.2 kΩ resistor bleeder draws only about 1.136 mA at 2.5 V, which is 0.227% of the 0.5 A charge-current target. It cannot dynamically compensate for this capacity mismatch. To bypass approximately 0.5 A at 2.5 V would require a shunt path capable of about 1.25 W dissipation, before thermal margin, or a different active energy-balancing approach.

This creates a second, independent feasibility gate: a per-cell OVP that simply stops the charger is safe but may stop at a pack voltage too low to meet backup runtime; omitting OVP risks overvolting the weak cell. The 4S baseline therefore needs a quantified cell-matching procurement specification or a real dynamic balancing circuit with adequate current and thermal capability. The 2.2 kΩ bleed resistors alone do not close this gap. These are tolerance-corner calculations, not measurements of a purchased four-cell set.

## Required pack charge voltage

The minimum initial pack OCV needed to reach 1.2 s is:

| Boost efficiency assumption | Required initial pack OCV | Headroom to 9.4 V |
|---:|---:|---:|
| 90% | 9.323 V | 76.5 mV |
| 92% | 9.276 V | 124.2 mV |
| 94% | 9.230 V | 170.0 mV |

The 9.4 V ceiling leaves little tolerance margin, especially at 90% efficiency. This result is conditional on the constant-efficiency model and does not include switching ripple, cell mismatch, temperature, leakage, balancing current, output-bus switchover, or transient UVLO behavior.

The TPS54302 divider currently uses 142 kΩ / 10 kΩ, 0.1%. With the documented 0.581–0.611 V VFB range, its calculated Buck-output static corners are approximately 8.815 V / 9.059 V / 9.305 V. These are Buck output values, not capacitor-terminal values.

Even if the divider were rescaled so that its worst-high static corner were exactly 9.4 V, the same VFB and resistor-tolerance ratio gives a worst-low corner of approximately 8.905 V. That is far below the 9.276 V requirement at 92% efficiency. Merely changing the divider ratio cannot close the tolerance gap while retaining a 9.4 V maximum.

## Engineering implication

The current TPS54302 fixed-divider arrangement is not a robust way to guarantee both:

1. a capacitor-pack charge ceiling no higher than 9.4 V; and
2. at least 1.2 s EOL backup runtime.

A candidate architecture for the next design review is:

- Sense PACK_4S on the capacitor side of D101 using a Kelvin pair referenced to pack negative, rather than regulating only the Buck-side node.
- Retain a separately analyzed CC loop, and check its interaction with the pack-side CV loop and the existing FB-injection compensation.
- Use a precision reference / external error-amplifier path for CV accuracy, with a separately independent hardware total-pack OVP.
- Add independent per-cell OVP hardware. Pack-total voltage alone cannot guarantee that every series cell remains below its allowable voltage.
- Preserve default-off behavior when the control supply is absent, the MCU resets, a cell-sense lead opens, or the protection chain is not healthy.

This is a design direction, not a frozen circuit. The existing OPA4197 + TLV1704 + REF5025 per-cell monitor proposal in sim/cell_balancing/README.md is still only a candidate and has not been drawn into the schematic or validated.

## Required next verification

1. Reconcile the old 112.5 mΩ/cell scripts and reports with the corrected 130 mΩ/cell HCC EOL value; preserve legacy results with an explicit label rather than silently overwriting evidence.
2. Decide the cell-matching procurement specification or design a dynamic balancing path with enough current and thermal capability. Do not treat the 2.2 kΩ bleed resistors as dynamic balancing.
3. Develop a pack-side CV sensing candidate, including feedback-pin off-state isolation/backfeed analysis, then re-run ERC and compare the exported netlist against the intended topology.
4. Recalculate reference, divider, amplifier offset/bias, temperature, and OVP tolerances. Demonstrate a non-overlapping feasible window between the minimum CV needed for runtime and the maximum allowed per-cell/pack voltage.
5. Simulate CC-to-CV transition, loop stability, startup, prebiased-pack connection, input removal, reverse current, and hardware OVP response.
6. Run a coupled EOL test with the measured TPS61088 efficiency/current-limit map. A fixed 92% efficiency is a sensitivity point, not a validated converter curve.
7. On hardware, measure all four cell voltages, pack OCV after charge taper/rest, pack terminal voltage under load, 12 V output minimum, and actual backup duration.

## Reproduction

From this directory:

~~~bash
python -m unittest -v
python model.py
~~~

The model uses only the Python standard library. The unit tests include corrected pack equivalents, exact runtime checkpoints, feedback-divider corners, cell-capacity mismatch, passive-bleeder current, monotonicity, and voltage-limit feasibility.

## Sources and evidence boundaries

- HCC HCAP-C 2R7 106 manufacturer datasheet: https://uploadcdn.oneyac.com/attachments/files/brand_pdf/hcccap/HCAP-C%202R7%20106.pdf
- TI TPS54302 datasheet: https://www.ti.com/lit/ds/symlink/tps54302.pdf
- Existing charger design review: hardware/kicad/CHARGER_DESIGN.md
- Existing corrected architecture model: research/architecture_reconciliation/compare_storage_architectures.py on the separate architecture-reconciliation-2s-vs-4s research branch.

No claim in this report is a measured capacitor-bank or converter result.
