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
