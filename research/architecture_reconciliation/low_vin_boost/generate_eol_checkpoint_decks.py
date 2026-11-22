#!/usr/bin/env python3
"""Generate EOL 2S supercapacitor-coupled TPS61088 checkpoint decks."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
from compare_storage_architectures import DESIGNS, sample_checkpoint_states  # noqa: E402

BOOST_EFFICIENCY = 0.92
PATH_EFFICIENCY = 0.99
CHECKPOINT_S = 1.2
SIMULATION_END_MS = 40
MAX_STEP_NS = 50
STEADY_WINDOW_MS = "35-37"
RFSW_KOHM = 324
RILIM_KOHM = 100
MODEL_INCLUDE = "../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB"

CANDIDATES = (
    ("2S30F_KAM_HP_40", "eol_2s30f_hp40_1p2s_92pct"),
    ("2S25F_KAM_LR", "eol_2s25f_lr_1p2s_92pct"),
)

TEMPLATE = """* EOL 2S pack-coupled TPS61088 local startup window
* Architecture: @ARCH@
* Behavioral-model checkpoint: t=@CHECKPOINT@ s, eta_boost=92%, eta_path=99%
* Expected pack OCV=@VOC@ V; expected loaded pack terminal=@VTERM@ V
* Expected input current=@IIN@ A; these are prebias estimates, not LTspice results.
* RFSW=324k is retained for BOM comparability; actual FSW remains under audit.
.include ../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB
CSTORE PACK_OC 0 @CEQ@ IC=@VOC@
RESR PACK_OC PACK @RPACK@
RPATH PACK PACK_IN 0.002
VSENSE PACK_IN VIN 0
CIN VIN 0 35u
CINHF VIN 0 100n
L1 VIN LD 3.3u
RLD LD SW 0.026
CBOOT BOOT SW 100n
CVCC VCC 0 4.7u
CSS SS 0 47n
RCOMP COMP CM 21.5k
CCOMP CM 0 13n
CHF COMP 0 100p
RFSW FSW SW 324k
RILIM ILIM 0 100k
RUP VOUT FB 1.076meg
RDN FB 0 120k
COUT VOUT 0 47u Rser=0.003
VLOAD VOUT LOAD 0
BLOAD LOAD 0 I=if(V(EN)>1.5,min(max(V(LOAD)/10,0),1),0)
VEN EN 0 PWL(0 0 100u 0 101u 3)
X1 0 BOOT COMP EN FB FSW ILIM 0 NC0 NC1 0 SS SW SW SW SW VCC VIN VOUT VOUT VOUT TPS61088_TRANS
.save V(PACK_OC) V(PACK) V(PACK_IN) V(VIN) V(VOUT) V(EN) V(COMP) V(SS) V(SW) I(VSENSE) I(L1) I(VLOAD)
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 40m 0 50n uic
.meas tran t_en WHEN V(EN)=1.2 RISE=1
.meas tran t98 WHEN V(VOUT)=11.76 RISE=1
.meas tran t98_delay PARAM t98-t_en
.meas tran sw_t6001 WHEN V(SW)=10 RISE=6001
.meas tran sw_t6101 WHEN V(SW)=10 RISE=6101
.meas tran f_sw_khz PARAM 100/(sw_t6101-sw_t6001)/1000
.meas tran pack_ocv_avg AVG V(PACK_OC) from 35m to 37m
.meas tran pack_terminal_avg AVG V(PACK) from 35m to 37m
.meas tran pack_input_avg AVG V(PACK_IN) from 35m to 37m
.meas tran vin_avg AVG V(VIN) from 35m to 37m
.meas tran avg_vout AVG V(VOUT) from 35m to 37m
.meas tran vmin MIN V(VOUT) from 35m to 37m
.meas tran vmax MAX V(VOUT) from 35m to 37m
.meas tran ripple PP V(VOUT) from 35m to 37m
.meas tran peak_i MAX I(L1) from 35m to 37m
.meas tran peak_start MAX I(L1) from 0 to 35m
.meas tran iin_avg AVG I(VSENSE) from 35m to 37m
.meas tran iout_avg AVG I(VLOAD) from 35m to 37m
.meas tran pin AVG (V(VIN)*I(VSENSE)) from 35m to 37m
.meas tran ppack AVG (V(PACK)*I(VSENSE)) from 35m to 37m
.meas tran pout AVG (V(VOUT)*I(VLOAD)) from 35m to 37m
.meas tran pack_esr_loss_w AVG (I(VSENSE)*I(VSENSE)*@RPACK@) from 35m to 37m
.meas tran path_loss_w AVG (I(VSENSE)*I(VSENSE)*0.002) from 35m to 37m
.meas tran eff PARAM 100*pout/pin
.meas tran eff_pack PARAM 100*pout/ppack
.end
"""


def _num(value: float) -> str:
    return f"{value:.12g}"


def render_deck(architecture: str) -> tuple[str, dict]:
    if architecture not in {item[0] for item in CANDIDATES}:
        raise ValueError(f"unsupported EOL checkpoint architecture: {architecture}")
    design = DESIGNS[architecture]
    state = sample_checkpoint_states(
        design,
        design["capacity_tolerance_min"] * design["life_cap_factor"],
        design["life_esr_factor"],
        BOOST_EFFICIENCY,
        [CHECKPOINT_S],
    )[0]
    case = dict(
        architecture=architecture,
        case=next(name for arch, name in CANDIDATES if arch == architecture),
        checkpoint_s=CHECKPOINT_S,
        expected_pack_ocv_v=state["v_oc_v"],
        expected_pack_terminal_v=state["v_terminal_v"],
        expected_input_current_a=state["input_current_a"],
        Ceq_F=state["c_eq_f"],
        Rpack_ohm=state["r_pack_ohm"],
        boost_efficiency=BOOST_EFFICIENCY,
        path_efficiency=PATH_EFFICIENCY,
    )
    substitutions = {
        "@ARCH@": architecture,
        "@CHECKPOINT@": _num(CHECKPOINT_S),
        "@VOC@": _num(state["v_oc_v"]),
        "@VTERM@": _num(state["v_terminal_v"]),
        "@IIN@": _num(state["input_current_a"]),
        "@CEQ@": _num(state["c_eq_f"]),
        "@RPACK@": _num(state["r_pack_ohm"]),
    }
    deck = TEMPLATE
    for token, value in substitutions.items():
        deck = deck.replace(token, value)
    return deck, case


def build_manifest_rows() -> list[dict]:
    rows = []
    for order, (architecture, _) in enumerate(CANDIDATES, start=1):
        _, case = render_deck(architecture)
        rows.append({
            "run_order": order,
            **case,
            "vin_source_v": "",
            "vout_target_v": "12.0",
            "iout_target_a": "1.0",
            "simulation_end_ms": str(SIMULATION_END_MS),
            "max_step_ns": str(MAX_STEP_NS),
            "steady_window_ms": STEADY_WINDOW_MS,
            "rfsw_kohm": str(RFSW_KOHM),
            "rilim_kohm": str(RILIM_KOHM),
            "mode": "GND_FPWM",
            "run_status": "not_run",
        })
    return rows


def write_matrix(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for architecture, case_name in CANDIDATES:
        deck, _ = render_deck(architecture)
        (output_dir / f"{case_name}.cir").write_text(deck, encoding="utf-8")

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
        default=Path(__file__).with_name("checkpoints"),
        help="output directory (default: checkpoints beside this script)",
    )
    args = parser.parse_args()
    write_matrix(args.output_dir)
    print(f"Wrote {len(CANDIDATES)} pack-coupled EOL checkpoint decks to {args.output_dir}")


if __name__ == "__main__":
    main()
