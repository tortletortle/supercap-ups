# V1.4 LTspice audit matrix

The 16 LTspice decks are committed in this directory. To regenerate the CSVs and all decks from the source matrix, run this command from the repository root:

    py -3 sim/tps61088_v1_4/scripts/build_matrix.py

- 4 frequency cases: VIN=7/9.4 V with RFSW=324/510/517 kΩ.
- 12 current-limit cases: VIN=7/9.4 V with RILIM=100/160/174/180/200/220 kΩ.

All decks use final-BOM passive values, MODE=0 (FPWM), and the V1.3 TI macro-model. They are unrun test inputs, not results. Run the .cir files in LTspice. Inspect V(sw) for ringing and confirm sw_t6001/sw_t6101 occur after t98.
