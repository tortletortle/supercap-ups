DC V1.2 simulation preparation — 2026-11-20
Run: python sweep.py (Python 3, standard library only).
The CSV outputs are actual results of a numerical model; not IC-level SPICE or bench evidence.
S01_hold_behavioral.cir is a preliminary LTspice text netlist, NOT independently run. Open the .cir and Run in LTspice; evaluate only before first 7 V crossing. For stress use Ccell=6.3 and Rcell=0.1125. For V(full), balance assumption each capacitor starts at 2.35 V.
ESR 75 mOhm DC is an assumed value, not the supplier's 50 mOhm at 1 kHz. Stress: 0.9*0.7 capacity, 1.5x ESR; not manufacturer-guaranteed ageing.
CPL model: P=12/(eta_boost*eta_path); Vterm=Voc-I*R; I=2*P/(Voc+sqrt(Voc^2-4*R*P)); dVi/dt=-I/Ci. Charge energy is restored to same internal state by ideal 0.5A CC / 9.4V CV taper; integrates ESR loss in charge coordinate, excludes auxiliary load, standby, balancing, real CV termination, transient and control losses. Stop at 7V pack terminal or 1V cell terminal (provisional only). No measurement of converter ripple or current limit. Cycle efficiency based on 1.2s task, or truncated if task fails. Do not count partial task as a pass.
Next: download official TPS61088 and TPS54302 PSpice models; confirm model compatibility in actual simulator. Model Buck cold-start at 0V, current-feedback and reverse blocking. Model Boost 7..9.4V full load; test switching/compensation/ripple. Then add priority MOS path, short-circuit latch, independent cell OVP, balancing, auxiliary supply. Use true switching waveforms and energy integrals; do not confuse this behavioral netlist with chip-level evidence.

Follow-up: S01 and a 12-case behavioral sweep have since been run in LTspice and ngspice. See hold_validation/dc_v1_2_hold_report.md for results and rerun instructions.
