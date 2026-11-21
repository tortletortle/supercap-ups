# V1.4 FSW timing-path diagnostic

This is a diagnostic-only duplicate of the first accepted electrical test point:

- VIN = 7 V
- VOUT target = 12 V
- Load = 1 A
- RFSW = 324 kΩ
- RILIM = 100 kΩ
- Gear, reltol=0.003, trtol=7, gmin=1e-10, one thread
- 26 ms transient, 50 ns maximum step

The power-stage components, circuit values, operating conditions, solver settings and original 6001/6101 frequency measurement are unchanged. The only additions are saved vectors and measurements for V(FSW) and I(RFSW). Do not replace the original baseline deck with this diagnostic copy.

## Completed round-two observation (2026-11-21)

This probe has now completed in LTspice 26.1.1 / Normal / Gear, exit 0. Original prescribed frequency: 442.336492 kHz. Every common RAW vector, including time, is exactly equal to the first-round baseline at every stored double. V(FSW) averages 0.551986903 V and ranges from -0.098102 mV to 1.893605775 V; I(RFSW) averages -19.756621 uA with the positive direction FSW to SW.

See the [Chinese timing analysis](../results/frequency_round2/FSW定时路径分析.md), [experiment report](../results/frequency_round2/实验报告.md), and [original log](../results/frequency_round2/freq_vin7_rfsw324k_fsw_probe/ltspice_original.log). The voltage is a charging/reset ramp, not a constant DC offset. The 23 pF ramp and reset-switch off resistance are relevant diagnostic paths. The dynamic VSW/current expression below must not be treated as a complete frequency equation: in FPWM the selected timing logic also depends on the ramp comparator, filtered threshold, delay, and switching duty. Internal logic nodes were not saved in this run, so reconstruction remains conditional. No model-defect conclusion is established.

## Why this probe exists

The current TI macro-model contains these timing-path expressions:

- U5_TSW = (23 pF × V(SW) / V(U5_IFSW)) / 4
- U5_IFSW is sensed by a zero-volt current-sensing source in the model's FSW pin branch.

The first baseline run measured 442.336492 kHz, while the TPS61088 Rev. D equation gives 496.137217 kHz at this point. Rearranging the datasheet equation with the measured frequency gives an equivalent timing resistance of approximately 366.635 kΩ, about 13.159% above the external 324 kΩ resistor.

This equivalent value is a derived diagnostic quantity, not a measured physical resistance and not proof of a model defect. One hypothesis is that the model's internal FSW current/timing-node voltage causes V(SW)/I(FSW) to differ from the nominal external RFSW value.

## Measurements to inspect

The diagnostic deck saves every original first-case vector plus V(FSW) and I(RFSW), and adds:

- average V(SW) over 24–26 ms;
- average, minimum and maximum V(FSW) over 24–26 ms;
- average and peak-to-peak I(RFSW) over 24–26 ms.

Inspect the raw time series, not only averages. In particular:

1. Check whether V(FSW) is near zero or has a nonzero switching-dependent bias.
2. Compare the sign and magnitude of I(RFSW) with (V(FSW)-V(SW))/324 kΩ.
3. Inspect V(SW)/|I(RFSW)| only at valid intervals where current is nonzero; do not average a ratio across switching transitions.
4. Determine whether the model's internal timer current is exactly the external resistor current and whether the observed ratio can explain the frequency offset.
5. Confirm that adding saved signals did not alter the baseline measurements beyond numerical repeatability.

## Run

From this directory on the Windows LTspice machine:

    & 'C:\Users\<user>\AppData\Local\Programs\ADI\LTspice\LTspice.exe' -b 'freq_vin7_rfsw324k_fsw_probe.cir'

The executable path is environment-specific. Preserve the original baseline log and RAW. Keep this diagnostic result in a separate folder and do not mix it with the 16-case matrix acceptance count.

## Direct internal-node probe (prepared; not yet simulated)

The first timing analysis reconstructed U5_PVIN from external SW and a small internal divider network. That reconstruction is useful but conditional. The next experiment saves the actual internal nodes through LTspice hierarchical .save references; it does not add components or alter the macro-model.

Prepared decks:

- freq_vin7_rfsw324k_internal_probe_50ns.cir: original Gear / 50 ns maximum step.
- freq_vin7_rfsw324k_internal_probe_25ns.cir: identical electrical deck and Gear settings, changing only maximum step to 25 ns.

Both retain the original VIN=7 V, RFSW=324 kΩ, RILIM=100 kΩ, MODE=0, 26 ms transient, original 10 V threshold and RISE=6001/6101 measurements. The only netlist change is explicit saving of hierarchical nodes:

- X1:U5_PVIN and X1:U5_N01584: actual comparator threshold and timing-capacitor voltage.
- X1:U5_IFSW: internal FSW current-sense signal.
- X1:U5_TSW, X1:U5_TDELAY_SW, X1:U5_TOFF, X1:U5_TEND: timing-path state and delay quantities.
- X1:GATE_L, X1:SSEND, X1:MODE_OK, X1:U5_SEL_TOFF, X1:U5_TOFF_SEL, X1:U5_TOFF_SEL_1, X1:U5_N16903113: switching control and comparator/selection state.

LTspice documents hierarchical .save references using colon notation (for example, V(x23:node) or wildcard V(x23:*)). If the run does not emit the requested vectors, check **Simulate → Settings → Save Defaults → Save Subcircuit Node Voltages** and rerun. Do not add voltage sources or alter the LIB to expose nodes unless this read-only route fails.

### Run on the Windows LTspice machine

From the diagnostics directory, run each deck separately and retain its own .log and .raw:

    & 'C:\Users\<user>\AppData\Local\Programs\ADI\LTspice\LTspice.exe' -b 'freq_vin7_rfsw324k_internal_probe_50ns.cir'
    & 'C:\Users\<user>\AppData\Local\Programs\ADI\LTspice\LTspice.exe' -b 'freq_vin7_rfsw324k_internal_probe_25ns.cir'

Then run the read-only analyzer from the repository root:

    py -3 sim/tps61088_v1_4/scripts/analyze_fsw_internal.py --raw <path-to-50ns.raw> --out sim/tps61088_v1_4/results/fsw_internal_probe_50ns
    py -3 sim/tps61088_v1_4/scripts/analyze_fsw_internal.py --raw <path-to-25ns.raw> --out sim/tps61088_v1_4/results/fsw_internal_probe_25ns

The analyzer emits per-cycle timing CSV and a JSON summary. Keep the large RAW files local; archive their SHA-256, LTspice logs, and generated summaries in the repository.

### What this experiment is intended to discriminate

1. **Threshold reconstruction error:** compare directly saved X1:U5_PVIN with the earlier reconstructed 1.7377 V threshold.
2. **RC ramp model:** compare actual X1:U5_N01584 against the 23 pF / 1 MΩ differential equation using measured I(RFSW).
3. **Current-sense equivalence:** compare X1:U5_IFSW against -I(RFSW); do not assume their equivalence before checking the data.
4. **Logic and propagation delay:** separate comparator crossing, GATE_L transition, capacitor reset, and SW falling edge using directly saved nodes.
5. **Numerical sensitivity:** compare the 50 ns and 25 ns Gear results. Compare distributions and event intervals, not sample-by-sample RAW values, because adaptive time grids differ.

The 50 ns run should reproduce the original 442.336492 kHz result within numerical repeatability. The 25 ns run is a sensitivity check, not an expected exact target. Do not call the mechanism a unique root cause unless the directly observed node sequence and timestep comparison account for the remaining timing residual.

No new LTspice run has been performed for these prepared decks yet. The 12-case RILIM matrix remains blocked pending this timing review and the updated current-limit screen.

## New timing-budget hypothesis from existing data (not a new simulation)

The current 883-cycle analysis gives a useful prioritization:

- The 23 pF / 1 MΩ FSW charging-ramp prediction differs from the reconstructed actual ramp by only about 0.100 ns on average.
- The reconstructed PVIN-threshold crossing to SW falling interval is 110.469 ns.
- In the macro-model, R_U5_R9 = 90/0.693 Ω ≈ 129.870 Ω and C_U5_C7 = 1 nF. Their nominal RC half-step crossing is about 90.019 ns.
- The 110.469 ns post-threshold interval exceeds the datasheet's 89 ns delay term by 21.469 ns. Multiplying by VOUT/VIN = 12/7 gives 36.804 ns of equivalent period contribution.
- The simplified leaky-ramp period model leaves 38.172 ns unexplained; after this delay adjustment, only 1.368 ns remains.

This numerical alignment makes the comparator-to-U5_TOFF-to-GATE_L-to-SW path the highest-priority hypothesis for the residual. It is not yet causal proof: the 89 ns datasheet parameter and reconstructed PVIN-to-SW edge interval may not share exactly the same timing boundary.

The RAW analyzer now separates the direct events: PVIN crossing, comparator-output rise, U5_TOFF 0.5 V crossing, GATE_L rise, timing-capacitor reset, and SW falling. It also reports the direct U5_TDELAY_SW and U5_TEND values. Use these event intervals to determine whether the nominal 90 ns U5_TOFF RC and the remaining logic/driver propagation explain the observed 110.469 ns.

Do not continue tuning the 23 pF / 1 MΩ ramp to explain this residual unless the direct-node data contradict the current charge-balance result.

