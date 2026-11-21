#!/usr/bin/env python3
"""Build the V1.4 TPS61088 calculation CSVs and LTspice audit matrix.

The netlist README is deliberately user-maintained and is never generated or
overwritten by this script. Use --root to build into an isolated directory.
"""
import argparse
import csv
from pathlib import Path

CFREQ = 23e-12
TDELAY = 89e-9
VOUT = 12.0
VIN_POINTS = (7.0, 7.5, 8.0, 8.5, 9.0, 9.4)
RILIM_POINTS = (100, 160, 174, 180, 200, 220)
FREQ_CASES = ((7.0, 324), (7.0, 510), (9.4, 324), (9.4, 517))
ILIM_VINS = (7.0, 9.4)
V1_3_STARTUP_PEAK_A = 2.90306045263
OBS = (
    (324, 7.0, .00935581946186, .00950739245064, .0112016221142, "logs/bom_first/bom_7.log"),
    (324, 8.5, .00938894109488, .00952754372400, .0112052446606, "logs/bom_retry/bom_8p5.log"),
    (324, 9.0, .00942015809624, .00959431805305, .0112124299582, "logs/bom_retry/bom_9.log"),
    (324, 9.4, .00947636512241, .00980783428042, .0112101715836, "logs/bom_retry/bom_9p4.log"),
    (267, 9.4, .00951944333000, .00985085241275, .0112650710516, "logs/parameter_scan/fs267_9p4.log"),
    (412, 9.4, .00952275680028, .00985417821610, .0112654895873, "logs/parameter_scan/fs412_9p4.log"),
)


def rfreq(f_hz, vin):
    return 4 * (1 / f_hz - TDELAY * VOUT / vin) / CFREQ


def fsw(r_ohm, vin):
    return 1 / (r_ohm * CFREQ / 4 + TDELAY * VOUT / vin)


def ilim_fpwm(r_ohm):
    return 1_190_000 / r_ohm - 1.6


def vin_label(vin):
    """Match committed names: 7.0 -> '7', 9.4 -> '9p4'."""
    value = float(vin)
    if value.is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", "p")


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def deck(name, vin, rfsw_k, rlim_k):
    return f"""* V1.4 audit case: {name}
* TI TPS61088 macro-model. MODE=0 is forced PWM per TI datasheet.
* This deck is a test input only; no simulation result is implied.
.include ../../tps61088_v1_3/model/TPS61088_LT.LIB
V1 source 0 {vin:g}
RS source vin 0.002
VEN en 0 PWL(0 0 100u 0 101u 3)
CIN vin 0 35u
L1 vin sw 3.3u Rser=0.026
CBOOT boot sw 100n
CVCC vcc 0 4.7u
CSS ss 0 47n
RCOMP comp cm 21.5k
CCOMP cm 0 13n
CHF comp 0 100p
RFSW fsw sw {rfsw_k}k
RILIM ilim 0 {rlim_k}k
RUP vout fb 1.076meg
RDN fb 0 120k
COUT vout 0 47u Rser=0.003
VLOAD vout load 0
BLOAD load 0 I=min(max(V(load)/10,0),1)
X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss sw sw sw sw vcc vin vout vout vout TPS61088_TRANS
.save V(vin) V(vout) V(sw) V(en) V(comp) V(ss) I(V1) I(L1) I(VLOAD)
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 26m 0 50n
.meas tran t90 WHEN V(vout)=10.8 RISE=1
.meas tran t98 WHEN V(vout)=11.76 RISE=1
* Late edge counts are intended to fall after soft-start; inspect V(sw) for ringing.
.meas tran sw_t6001 WHEN V(sw)=10 RISE=6001
.meas tran sw_t6101 WHEN V(sw)=10 RISE=6101
.meas tran f_sw_khz PARAM 0.1/(sw_t6101-sw_t6001)
.meas tran avg_vout AVG V(vout) FROM 24m TO 26m
.meas tran ripple PP V(vout) FROM 24m TO 26m
.meas tran peak_i MAX I(L1) FROM 24m TO 26m
.meas tran peak_start MAX I(L1) FROM 0 TO 26m
.meas tran iin_avg AVG (-I(V1)) FROM 24m TO 26m
.meas tran iout_avg AVG I(VLOAD) FROM 24m TO 26m
.meas tran pin_avg AVG (-V(vin)*I(V1)) FROM 24m TO 26m
.meas tran pout_avg AVG (V(vout)*I(VLOAD)) FROM 24m TO 26m
.meas tran eta_pct PARAM 100*pout_avg/pin_avg
.end
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    root = p.parse_args().root.resolve()
    data, nets = root / "data", root / "netlists"
    data.mkdir(parents=True, exist_ok=True)
    nets.mkdir(parents=True, exist_ok=True)

    write_csv(data / "ti_frequency_setpoints.csv", [
        {"vin_V": f"{v:.1f}", "rfsw_for_500kHz_ohm": f"{rfreq(500e3, v):.2f}",
         "frequency_with_324k_ohm_kHz": f"{fsw(324e3, v)/1e3:.3f}",
         "rfsw_for_324kHz_ohm": f"{rfreq(324e3, v):.2f}"}
        for v in VIN_POINTS
    ])

    ilim_rows = []
    for r in RILIM_POINTS:
        typical = ilim_fpwm(r * 1e3)
        worst_case = typical - 1.3
        headroom = worst_case - V1_3_STARTUP_PEAK_A
        ilim_rows.append({
            "rilim_kohm": r,
            "ilim_typical_FPWM_A": f"{typical:.4f}",
            "ilim_worst_case_screen_A": f"{worst_case:.4f}",
            "V1_3_startup_peak_A": f"{V1_3_STARTUP_PEAK_A:.4f}",
            "minimum_headroom_A": f"{headroom:.4f}",
            "minimum_headroom_pct": f"{100 * headroom / V1_3_STARTUP_PEAK_A:.2f}",
            "screen_only_not_a_release_decision": "true",
        })
    write_csv(data / "ti_ilim_screen.csv", ilim_rows)

    write_csv(data / "v1_3_startup_edge_observations.csv", [
        {"rfsw_kohm": r, "vin_V": v, "sw_t1_s": f"{t1:.12f}",
         "sw_t101_s": f"{t101:.12f}", "t98_s": f"{t98:.12f}",
         "early_interval_kHz": f"{100/(t101-t1)/1e3:.3f}",
         "both_edges_before_t98": str(t101 < t98).lower(),
         "source_log": src, "interpretation": "startup_only_not_steady_state"}
        for r, v, t1, t101, t98, src in OBS
    ])

    count = 0
    for vin, rfsw_k in FREQ_CASES:
        name = f"freq_vin{vin_label(vin)}_rfsw{rfsw_k}k"
        (nets / f"{name}.cir").write_text(deck(name, vin, rfsw_k, 100), encoding="ascii")
        count += 1
    for vin in ILIM_VINS:
        for rlim_k in RILIM_POINTS:
            name = f"ilim_vin{vin_label(vin)}_rilim{rlim_k}k"
            (nets / f"{name}.cir").write_text(deck(name, vin, 324, rlim_k), encoding="ascii")
            count += 1

    # README.md is intentionally not generated: it contains reviewed, human-
    # maintained instructions and audit status. This script only owns CSVs
    # and the 16 deterministic .cir test inputs.
    print(f"Generated {count} LTspice decks in {nets}")


if __name__ == "__main__":
    main()
