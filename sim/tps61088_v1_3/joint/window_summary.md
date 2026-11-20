# TPS61088 LTspice short-window evidence

All values below come from LTspice 26.1.1 using work/lt_probe/TPS61088_LT.LIB, a syntax-adapted copy of the TI TPS61088 PSpice macro-model. The windows are 18 ms switching runs with statistics from 15 ms to 17 ms. The 4S cases are prebiased to V1.2-estimated capacitor states; they are not continuous 1.0 s or 1.2 s switching runs.

| Case | Vsrc/Vin (V) | Vout avg (V) | Vout min/max (V) | Ripple (mVpp) | IL peak (A) | Iin avg (A) | Pin (W) | Pout (W) | Eta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fixed_7v | 7.000 | 11.93881 | 11.91531 / 11.95388 | 38.57 | 2.81022 | 1.72252 | 12.05766 | 11.93881 | 99.014% |
| nominal_1p2s prebias | 8.11892 | 11.93847 | 11.91698 / 11.95224 | 35.26 | 2.49356 | 1.48170 | 12.02965 | 11.93847 | 99.242% |
| eol_1p2s prebias | 7.28822 | 11.93876 | 11.91618 / 11.95275 | 36.57 | 2.73868 | 1.65331 | 12.04957 | 11.93876 | 99.080% |
| fixed_9p4v | 9.400 | 11.93853 | 11.91213 / 11.95300 | 40.87 | 2.09588 | 1.27723 | 12.00599 | 11.93853 | 99.438% |

The first behavior-load run in ../lt_joint_behavior_load/nominal_1p2s.log used the wrong input-power sign and is retained as an invalid measurement record; its waveform is not used in this table. The v2 logs include corrected input-power direction and explicit source/input voltage measurements.

The model emits repeated N=0.0001 diode-emission warnings. The numbers above are macro-model switching-window evidence only: they exclude PCB parasitics, thermal drift, inductor saturation, capacitor voltage-dependent capacitance, and production tolerance distributions.
