# V1.4 LTspice audit matrix

The 16 LTspice decks are committed in this directory. To regenerate the CSVs and all decks from the source matrix, run this command from the repository root:

    py -3 sim/tps61088_v1_4/scripts/build_matrix.py

- 4 frequency cases: VIN=7/9.4 V with RFSW=324/510/517 kΩ.
- 12 current-limit cases: VIN=7/9.4 V with RILIM=100/160/174/180/200/220 kΩ.

All decks use final-BOM passive values, MODE=0 (FPWM), and the V1.3 TI macro-model. Only freq_vin7_rfsw324k.cir has been run in the first acceptance round; the other 15 decks remain pending. See the [first-case report](../results/first_case/实验报告.md). Inspect V(sw) for ringing and confirm sw_t6001/sw_t6101 occur after t98.

The generator currently spells VIN=7 cases as vin7p0 rather than the committed vin7 names, rewrites this README, and drops minimum_headroom_pct from the current-limit CSV. Use an isolated copy before regeneration. The original 16 circuits and measurement commands remain unchanged in this round.
