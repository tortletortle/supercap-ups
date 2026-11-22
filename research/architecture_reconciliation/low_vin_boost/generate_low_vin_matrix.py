#!/usr/bin/env python3
"""Generate fixed-input TPS61088 low-VIN decks for the 2S storage candidate.

The decks are inputs for a local LTspice run. This script does not run LTspice.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

INPUT_POINTS_V = (3.2, 3.6, 4.0, 4.4, 4.8)
MODEL_INCLUDE = "../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB"

TEMPLATE = """* Architecture review low-VIN case: VIN=@VIN@ V, 12 V / 1 A
* Fixed BOM baseline; MODE=0 (FPWM), RFSW=324k, RILIM=100k.
.include ../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB
V1 source 0 @VIN@
RS source vin 0.002
VEN en 0 PWL(0 0 100u 0 101u 3)
CIN vin 0 35u
L1 vin sw 3.3u Rser=.026
CBOOT boot sw 100n
CVCC vcc 0 4.7u
CSS ss 0 47n
RCOMP comp cm 21.5k
CCOMP cm 0 13n
CHF comp 0 100p
RFSW fsw sw 324k
RILIM ilim 0 100k
RUP vout fb 1.076meg
RDN fb 0 120k
COUT vout 0 47u Rser=.003
VLOAD vout load 0
BLOAD load 0 I=min(max(V(load)/10,0),1)
X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss sw sw sw sw vcc vin vout vout vout TPS61088_TRANS
.save V(vin) V(vout) V(sw) V(en) V(comp) V(ss) I(V1) I(L1) I(VLOAD)
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 40m 0 50n
.meas tran vin_avg AVG V(vin) from 35m to 37m
.meas tran avg_vout AVG V(vout) from 35m to 37m
.meas tran vmin MIN V(vout) from 35m to 37m
.meas tran vmax MAX V(vout) from 35m to 37m
.meas tran ripple PP V(vout) from 35m to 37m
.meas tran peak_i MAX I(L1) from 35m to 37m
.meas tran peak_start MAX I(L1) from 0 to 35m
.meas tran iin_avg AVG (-I(V1)) from 35m to 37m
.meas tran iout_avg AVG I(VLOAD) from 35m to 37m
.meas tran pin AVG (-V(vin)*I(V1)) from 35m to 37m
.meas tran pout AVG (V(vout)*I(VLOAD)) from 35m to 37m
.meas tran eff PARAM 100*pout/pin
.meas tran t_en WHEN V(en)=1.2 RISE=1
.meas tran t98 WHEN V(vout)=11.76 RISE=1
.meas tran t98_delay PARAM t98-t_en
.meas tran sw_t6001 WHEN V(sw)=10 RISE=6001
.meas tran sw_t6101 WHEN V(sw)=10 RISE=6101
.meas tran f_sw_khz PARAM 100/(sw_t6101-sw_t6001)/1000
.end
"""


def format_vin(vin: float) -> str:
    return f"{vin:.1f}".replace(".", "p")


def render_deck(vin: float) -> str:
    if vin not in INPUT_POINTS_V:
        raise ValueError(f"unsupported VIN test point: {vin}")
    return TEMPLATE.replace("@VIN@", f"{vin:.1f}")


def build_manifest_rows() -> list[dict]:
    rows = []
    for order, vin in enumerate(INPUT_POINTS_V, start=1):
        rows.append({
            "run_order": order,
            "case": f"tps61088_vin_{format_vin(vin)}v",
            "vin_source_v": f"{vin:.1f}",
            "vout_target_v": "12.0",
            "iout_target_a": "1.0",
            "simulation_end_ms": "40",
            "max_step_ns": "50",
            "steady_window_ms": "35-37",
            "rfsw_kohm": "324",
            "rilim_kohm": "100",
            "mode": "GND_FPWM",
            "run_status": "not_run",
        })
    return rows


def write_matrix(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for vin in INPUT_POINTS_V:
        name = f"tps61088_vin_{format_vin(vin)}v.cir"
        (output_dir / name).write_text(render_deck(vin), encoding="utf-8")

    rows = build_manifest_rows()
    with (output_dir / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("netlists"),
        help="output directory (default: netlists beside this script)",
    )
    args = parser.parse_args()
    write_matrix(args.output_dir)
    print(f"Wrote {len(INPUT_POINTS_V)} low-VIN decks to {args.output_dir}")


if __name__ == "__main__":
    main()
