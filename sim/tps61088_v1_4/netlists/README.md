# V1.4 LTspice audit matrix

The 16 LTspice decks are committed in this directory. To regenerate the CSVs and all decks from the source matrix, run this command from the repository root:

    py -3 sim/tps61088_v1_4/scripts/build_matrix.py

- 4 frequency cases: VIN=7/9.4 V with RFSW=324/510/517 kΩ.
- 12 current-limit cases: VIN=7/9.4 V with RILIM=100/160/174/180/200/220 kΩ.

All decks use the existing passive values, MODE=0 (FPWM), and the V1.3 TI macro-model. All four frequency decks have now run; the twelve current-limit decks remain pending. BOM selection is not frozen. See the [first-case report](../results/first_case/实验报告.md) and [round-two report](../results/frequency_round2/实验报告.md).

The generator defects observed in round one were fixed before round two: VIN=7 names use vin7, this README is preserved, and the current-limit percentage field is retained. The three regression tests pass. This round did not regenerate or edit any circuit, solver parameter, measurement threshold, or edge index.

Inspect V(sw) for ringing and confirm t98 < sw_t6001 < sw_t6101 < 26 ms. The 7 V / 510 kohm and 9.4 V / 517 kohm runs completed, but their prescribed frequency measurements failed because fewer than 6001 ten-volt rising edges occurred. Their independently extracted 24-26 ms frequencies are supplemental evidence, not fixed-index acceptance results. No indices or run lengths were changed to hide these failures.
