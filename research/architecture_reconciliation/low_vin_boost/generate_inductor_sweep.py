#!/usr/bin/env python3
"""Generate a worst-case-tolerance inductor comparison for critical 2S VIN points."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

INPUT_POINTS_V = (2.8, 3.6)
RFSW_KOHM = 324
RILIM_KOHM = 100
MODE = "GND_FPWM"
SIMULATION_END_MS = 40
MAX_STEP_NS = 50
STEADY_WINDOW_MS = "35-37"
MODEL_INCLUDE = "../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB"
PROGRAMMED_ILIM_TYPICAL_A = 10.3

# Use the lower Irms figures from the two conflicting CENKER CKST0603
# source tables until the manufacturer confirms the applicable revision.
INDUCTORS = (
    {
        "key": "3p3uH",
        "mpn": "CKST0603-3.3uH/M",
        "nominal_uH": 3.3,
        "min_uH": 2.64,
        "dcr_max_mohm": 26.0,
        "isat_typical_a": 9.5,
        "irms_typical_a": 6.0,
    },
    {
        "key": "2p2uH",
        "mpn": "CKST0603-2.2uH/M",
        "nominal_uH": 2.2,
        "min_uH": 1.76,
        "dcr_max_mohm": 17.5,
        "isat_typical_a": 10.0,
        "irms_typical_a": 8.0,
    },
    {
        "key": "1p5uH",
        "mpn": "CKST0603-1.5uH/M",
        "nominal_uH": 1.5,
        "min_uH": 1.20,
        "dcr_max_mohm": 12.1,
        "isat_typical_a": 12.5,
        "irms_typical_a": 11.0,
    },
)

TEMPLATE = """* Inductor candidate stress sweep: @MPN@, VIN=@VIN@ V, 12 V / 1 A
* Worst-case tolerance corner: L minimum after -20%, DCR maximum.
* Isat/Irms metadata are manufacturer typical references, not guaranteed limits.
* MODE=GND_FPWM, RILIM=100k; TI datasheet minimum FPWM limit is 9.0 A.
.include ../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB
V1 source 0 @VIN@
RS source vin 0.002
VEN en 0 PWL(0 0 100u 0 101u 3)
CIN vin 0 35u
L1 vin sw @LMIN@u Rser=@DCRMAX@
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
.meas tran il_avg AVG I(L1) from 35m to 37m
.meas tran il_rms RMS I(L1) from 35m to 37m
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


def _num(value: float) -> str:
    return f"{value:.12g}"


def format_vin(vin: float) -> str:
    return f"{vin:.1f}".replace(".", "p")


def case_name(inductor: dict, vin: float) -> str:
    return f"inductor_{inductor['key']}_vin_{format_vin(vin)}v"


def render_deck(inductor: dict, vin: float) -> tuple[str, dict]:
    if inductor not in INDUCTORS:
        raise ValueError("unsupported inductor candidate")
    if vin not in INPUT_POINTS_V:
        raise ValueError(f"unsupported VIN test point: {vin}")

    substitutions = {
        "@MPN@": inductor["mpn"],
        "@VIN@": _num(vin),
        "@LMIN@": _num(inductor["min_uH"]),
        "@DCRMAX@": _num(inductor["dcr_max_mohm"] / 1000.0),
    }
    deck = TEMPLATE
    for token, value in substitutions.items():
        deck = deck.replace(token, value)

    metadata = {
        "case": case_name(inductor, vin),
        "case_type": "inductor_stress",
        "vin_source_v": _num(vin),
        "vout_target_v": "12.0",
        "iout_target_a": "1.0",
        "simulation_end_ms": str(SIMULATION_END_MS),
        "max_step_ns": str(MAX_STEP_NS),
        "steady_window_ms": STEADY_WINDOW_MS,
        "rfsw_kohm": str(RFSW_KOHM),
        "rilim_kohm": str(RILIM_KOHM),
        "mode": MODE,
        "inductor_mpn": inductor["mpn"],
        "inductance_nominal_uH": _num(inductor["nominal_uH"]),
        "inductance_min_uH": _num(inductor["min_uH"]),
        "dcr_max_mohm": _num(inductor["dcr_max_mohm"]),
        "isat_typical_a": _num(inductor["isat_typical_a"]),
        "irms_typical_a": _num(inductor["irms_typical_a"]),
        "isat_above_programmed_ilim_typical": str(
            inductor["isat_typical_a"] > PROGRAMMED_ILIM_TYPICAL_A
        ).lower(),
        "programmed_ilim_typical_a": _num(PROGRAMMED_ILIM_TYPICAL_A),
        "run_status": "not_run",
    }
    return deck, metadata


def build_manifest_rows() -> list[dict]:
    rows = []
    order = 1
    for inductor in INDUCTORS:
        for vin in INPUT_POINTS_V:
            _, metadata = render_deck(inductor, vin)
            rows.append({"run_order": order, **metadata})
            order += 1
    return rows


def write_matrix(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for inductor in INDUCTORS:
        for vin in INPUT_POINTS_V:
            deck, metadata = render_deck(inductor, vin)
            (output_dir / f"{metadata['case']}.cir").write_text(
                deck, encoding="utf-8"
            )

    rows = build_manifest_rows()
    with (output_dir / "manifest.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0].keys()), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("inductor_sweep"),
        help="output directory (default: inductor_sweep beside this script)",
    )
    args = parser.parse_args()
    write_matrix(args.output_dir)
    print(f"Wrote {len(INDUCTORS) * len(INPUT_POINTS_V)} inductor stress decks to {args.output_dir}")


if __name__ == "__main__":
    main()
