# V1.4 LTspice audit matrix

Run python scripts/build_matrix.py from the repository root to generate 16 test decks.

- 4 frequency cases: VIN=7/9.4 V with RFSW=324/510/517 kΩ.
- 12 current-limit cases: VIN=7/9.4 V with RILIM=100/160/174/180/200/220 kΩ.

All generated decks use final-BOM passive values, MODE=0 (FPWM), and the V1.3 TI macro-model. They are unrun test inputs, not results. Run the .cir files in LTspice. Inspect V(sw) for ringing and confirm sw_t3001/sw_t3101 occur after t98.
