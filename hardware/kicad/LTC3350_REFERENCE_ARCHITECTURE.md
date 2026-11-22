# LTC3350 integrated supercapacitor UPS — architecture evaluation

**Status:** alternative architecture study; not merged into the cost-sensitive discrete mainline.  
**Base branch:** power-stage-integration  
**Base commit:** ad015db2288c47f03f88ff1d29f4c2090b7e1663

## 1. Why this branch exists

The current discrete candidate uses TPS54302 for charging, TPS61088 for backup boost, four 2.2 kΩ passive cell bleeders, and a separate pack UVLO. Its KiCad 9.0.2 three-page schematic has ERC = 0 errors / 0 warnings, but the repository's own review still lists precision CV, single-cell OVP, discharge isolation, and system switchover as unresolved.

The LTC3350 is a purpose-built supercapacitor backup controller. It combines a synchronous buck charger that reverses as a boost converter, input/output ideal-diode control, internal cell balancers, per-cell shunt OVP, and an I²C/SMBus ADC. It supports one to four series capacitors, 4.5 V–35 V input, and up to 5 V per capacitor.

This branch evaluates it as a **reference architecture**, not as an approved replacement. Its unit price is high relative to a low-cost student design.

## 2. Evidence from the vendor reference designs

ADI's LTC3350 data sheet includes:
- An application circuit with four series 10 F supercapacitors and a 10 V / 1 A backup output.
- A separate 12 V / 48 W backup application.
- A programmable VCAP target, programmable shunt voltage, current sensing, and active balancing.

The DC1937B evaluation design is another useful layout and power-stage reference. These examples demonstrate the controller's individual capabilities; they do **not** prove the combined 4S × 10 F, 12 V / 1 A design proposed here. That combined design still requires a complete schematic, switching simulation, layout review, and bench tests.

References:
- [LTC3350 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc3350.pdf)
- [DC1937B evaluation-board schematic](https://www.analog.com/media/en/technical-documentation/eval-board-schematic/DC1937B-3-SCH.PDF)
- [DC1937B evaluation-board product page](https://www.analog.com/en/resources/evaluation-hardware-and-software/evaluation-boards-kits/dc1937b.html)

## 3. Proposed power architecture

~~~mermaid
flowchart LR
    VIN[12 V input] --> IDEALIN[Input ideal-diode path]
    IDEALIN --> VOUT[12 V system rail]
    VIN --> LTC[LTC3350 synchronous buck / boost controller]
    LTC <--> FETS[External MOSFETs and inductor]
    FETS <--> CAP[4S × 10 F supercapacitor bank]
    CAP --> FETS
    LTC --> IDEALOUT[Backup ideal-diode path]
    IDEALOUT --> VOUT
    LTC <-->|I²C / SMBus| MCU[CH32V003 monitor]
    LTC -->|PFO / CAPGD / SMBALERT| MCU
~~~

Normal operation: the input path supplies the system rail while the LTC3350 charges the capacitor stack. On input failure, the same switching power stage reverses into boost operation and supplies the backup rail. The ideal-diode paths prevent the two sources from back-feeding one another.

## 4. Candidate setpoints and first-pass values

These values are calculation candidates, not a frozen BOM.

| Function | Candidate | Calculation / reason |
|---|---:|---|
| Input | 12 V nominal | The ADI four-cap application accepts 11 V–35 V; confirm the actual adapter minimum and surge envelope. |
| Backup output | 12.0 V / 1 A | 12 W load. Use 90.0 kΩ top / 10.0 kΩ bottom as a first-pass OUTFB divider for a 1.2 V feedback reference. |
| Capacitor stack target | 10.0 V | Four cells average 2.5 V. Use 86.6 kΩ top / 11.8 kΩ bottom as the first-pass CAPFB divider: 1.2 × (1 + 86.6 / 11.8) = 10.0068 V. |
| VCAP worst-case window | 9.782 V–10.231 V | Conservative additive budget: ±2.0% reference, ±0.2% divider ratio, plus 50 nA CAPFB leakage through 86.6 kΩ. |
| Cell shunt threshold | 2.60 V | Candidate programmable VSHUNT value. With 183.5 µV/LSB, the rounded code is 0x3759; verify register field/reserved bits before firmware use. |
| Shunt ballast | 2.7 Ω per ballast path | The vendor reference uses 2.7 Ω ballast resistors. At 2.60 V, the first-order shunt-current estimate is 0.481 A nominal and 0.459 A with +5% resistance. |
| Ballast dissipation | ≥2 W parts | The data-sheet dissipation estimate is about 0.47 W nominal per active shunt path; use the vendor reference footprint/rating and verify pulse/thermal derating. |
| Charge current sense | R_SNSC = 8 mΩ | Data-sheet peak-current estimate: 58 mV / 8 mΩ = 7.25 A. This is a starting point for 12 W backup; check ripple and saturation. |
| Input-current sense | R_SNSI1 = 16 mΩ, R_SNSI2 = 75 mΩ | With the data-sheet two-resistor equation, charger input-current limit is about 0.352 A with no system load and 0.176 A at a 1 A system load. |
| Adapter current | ≥1.5 A recommended | At a 1 A load, the first-pass input budget is about 1.176 A before adapter tolerance and transient margin. |

### Charge-current budget

Using 12 V input, 10.0068 V VCAP, and 90% buck efficiency:

- No system load: approximately 0.352 A charger input current, or 0.380 A into the capacitor stack.
- 1 A system load: approximately 0.176 A charger input current, or 0.190 A into the capacitor stack.
- The charger current is intentionally reduced when the system load consumes input-current budget. If the adapter is limited to 1 A, charging should be allowed to pause at full load rather than violate the input limit.

The maximum modeled stack charge current at 100% conversion efficiency is approximately 0.422 A. That is below the 0.459 A shunt-current estimate at the +5% ballast-resistor corner. The LTC3350 may further reduce charge current while a shunt is active; charge time therefore needs to be measured.

### Cell balancing and overvoltage

The LTC3350's internal active balancers remove the need for four continuously conducting 2.2 kΩ bleed resistors. Its per-cell shunt regulators provide a hardware path to hold a high cell near the programmed shunt threshold while the other cells continue charging. The external 2.7 Ω parts are shunt ballast resistors, not the old low-current passive balancing network.

The controller's shunt-current capability is finite and duty-limited. It is not permission to choose an arbitrary charge current: the charge-current limit must remain below the effective shunt capability, and the thermal behavior must be checked when multiple cells shunt simultaneously.

## 5. Hold-time model

The existing project EOL assumptions are retained:

- Four cells, each 6.3 F and 112.5 mΩ.
- Equivalent series capacitance: 1.575 F.
- Pack ESR: 0.450 Ω.
- Output load: 12 W.
- Output path efficiency: 99%.
- Backup conversion efficiency: 80% conservative case.
- Loaded pack cutoff: 7.102 V, the upper corner from the current UVLO tolerance analysis.

The first-order constant-power model gives:

| Initial pack voltage | Backup efficiency | Calculated hold time |
|---:|---:|---:|
| 9.782 V (worst-low VCAP corner) | 80% | 1.444 s |
| 9.782 V | 85% | 1.589 s |
| 9.782 V | 90% | 1.734 s |
| 10.007 V (nominal divider target) | 80% | 1.657 s |

At 80% backup efficiency, the model requires 9.518 V initial pack voltage for 1.2 s. The calculated worst-low VCAP corner is 264 mV above that threshold.

A separate equalized-start weak-cell discharge case uses 6.3 F + 3 × 9 F, ESR 112.5 mΩ + 3 × 75 mΩ, and equal initial cell voltages. At the worst-low 9.782 V pack start, the group reaches 7.102 V after about 2.149 s; the weakest loaded cell is about 1.573 V at that instant. This result depends on the LTC3350 having equalized the initial cell voltages. It is a behavioral model, not a measured cell-protection result.

Reproduce the calculations and tests with:

~~~bash
python3 sim/ltc3350_reference/evaluate.py
python3 -m unittest discover -s sim/ltc3350_reference -p 'test_*.py' -v
~~~

## 6. What this architecture does not solve automatically

1. **12 V / 1 A combined validation.** The vendor's 4 × 10 F / 10 V / 1 A and 12 V / 48 W examples are separate designs. The proposed combination needs a fresh power-stage design.
2. **12 V input overvoltage.** The LTC3350's high input OVLO threshold is not a precise 12 V adapter protector. Retain a separately specified TVS/eFuse/OVP stage based on the actual adapter limits.
3. **Single-cell undervoltage.** The ADC can report cell voltages and raise programmable alarms, but software polling must not be treated as an independent hardware UV cutoff. Retain the group UVLO and separately decide whether a hard per-cell discharge cutoff is required.
4. **Switching loop and thermal design.** Verify MOSFET voltage/current ratings, inductor saturation, sense-resistor Kelvin routing, shunt ballast pulse heating, QFN exposed-pad layout, compensation, and 12 V load-step behavior.
5. **Startup and I²C configuration.** Verify default VCAP/VSHUNT behavior, program the selected shunt threshold before enabling the intended charge profile, and define safe behavior if the MCU is held in reset or the I²C bus is unavailable.
6. **Power-path transitions.** Measure input removal/recovery, output droop/overshoot, reverse current, and source-priority behavior at 1 A.
7. **Cost.** Current single-unit distributor listings are roughly US$10.36 at LCSC and ¥121.49 at DigiKey for the IC alone. This is a high-reliability reference option, not the low-cost BOM winner.

## 7. Decision

Keep the existing TPS54302 + TPS61088 design as the cost-sensitive mainline. Keep this LTC3350 branch separate as an integrated reference architecture. The next engineering gate is to create a KiCad schematic from the ADI application circuit, set VCAP ≈ 10 V and VOUT = 12 V, run switching/thermal analysis, and compare the complete BOM against the discrete design. Do not merge this branch or order the IC until that comparison is complete.
