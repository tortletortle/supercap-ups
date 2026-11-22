#!/usr/bin/env python3
"""Generate prebiased 12 V output-bus transfer tests for 2S UPS candidates."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
from compare_storage_architectures import DESIGNS, pack_equivalent  # noqa: E402

CAPACITY_FACTOR_BY_DESIGN = {
    design_id: design["capacity_tolerance_min"] * design["life_cap_factor"]
    for design_id, design in DESIGNS.items()
}
CANDIDATES = (
    "2S30F_KAM_HP_44",
    "2S30F_KAM_HP_40",
    "2S25F_KAM_LR",
)
ENABLE_DELAYS_US = (20, 50, 100)
PATH_RESISTANCE_OHM = 0.002
SIMULATION_END_MS = 40
MAX_STEP_NS = 50
STEADY_WINDOW_MS = "35-37"
MODEL_INCLUDE = "../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB"

TEMPLATE = """* Prebiased 12 V bus takeover test; main source removed at t=0
* Architecture: @ARCH@
* EOL capacitance/ESR, fully charged OCV @VOC@ V
* Backup EN begins after @DELAY_US@ us; 1 us EN ramp
* This is a local transfer/startup test, not a 1.2 s hold-up simulation.
.include ../../../../sim/tps61088_v1_3/model/TPS61088_LT.LIB
CSTORE PACK_OC 0 @CEQ@ IC=@VOC@
RESR PACK_OC PACK @RPACK@
RPATH PACK PACK_IN @RPATH@
VSENSE PACK_IN VIN 0
CIN VIN 0 35u IC=@VOC@
CINHF VIN 0 100n IC=@VOC@
L1 VIN LD 3.3u
RLD LD SW 0.026
CBOOT BOOT SW 100n
CVCC VCC 0 4.7u
CSS SS 0 47n IC=1.5
RCOMP COMP CM 21.5k
CCOMP CM 0 13n
CHF COMP 0 100p
RFSW FSW SW 324k
RILIM ILIM 0 100k
RUP VOUT FB 1.076meg
RDN FB 0 120k
COUT VOUT 0 47u Rser=0.003 IC=12
VLOAD VOUT LOAD 0
* Load remains connected throughout transfer; 1 A above 10 V.
BLOAD LOAD 0 I=min(max(V(LOAD)/10,0),1)
VEN EN 0 PWL(0 0 @DELAY_S@ 0 @DELAY_PLUS_S@ 3)
X1 0 BOOT COMP EN FB FSW ILIM 0 NC0 NC1 0 SS SW SW SW SW VCC VIN VOUT VOUT VOUT TPS61088_TRANS
.save V(PACK_OC) V(PACK) V(PACK_IN) V(VIN) V(VOUT) V(EN) V(COMP) V(SS) V(SW) I(VSENSE) I(L1) I(VLOAD)
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 40m 0 50n uic
.meas tran t_en WHEN V(EN)=1.2 RISE=1
.meas tran t98 WHEN V(VOUT)=11.76 RISE=1
.meas tran t98_delay PARAM t98-t_en
.meas tran vout_at_enable FIND V(VOUT) AT=@DELAY_S@
.meas tran vout_pre_enable_min MIN V(VOUT) from 0 to @DELAY_S@
.meas tran vout_first_5ms_min MIN V(VOUT) from 0 to 5m
.meas tran vout_global_min MIN V(VOUT) from 0 to 40m
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
.meas tran path_loss_w AVG (I(VSENSE)*I(VSENSE)*@RPATH@) from 35m to 37m
.meas tran eff PARAM 100*pout/pin
.meas tran eff_pack PARAM 100*pout/ppack
.end
"""


def _num(value: float) -> str:
    return f"{value:.12g}"


def case_name(architecture: str, delay_us: int) -> str:
    return f"transfer_{architecture.lower()}_{delay_us}us"


def render_deck(architecture: str, delay_us: int) -> tuple[str, dict]:
    if architecture not in CANDIDATES:
        raise ValueError(f"unsupported transfer architecture: {architecture}")
    if delay_us not in ENABLE_DELAYS_US:
        raise ValueError(f"unsupported backup enable delay: {delay_us} us")

    design = DESIGNS[architecture]
    cap_factor = CAPACITY_FACTOR_BY_DESIGN[architecture]
    esr_factor = design["life_esr_factor"]
    c_eq_f, r_pack_ohm = pack_equivalent(design, cap_factor, esr_factor)
    initial_ocv_v = design["n_series"] * design["cell_start_v"]
    delay_s = delay_us * 1e-6
    delay_plus_s = (delay_us + 1) * 1e-6
    substitutions = {
        "@ARCH@": architecture,
        "@VOC@": _num(initial_ocv_v),
        "@CEQ@": _num(c_eq_f),
        "@RPACK@": _num(r_pack_ohm),
        "@RPATH@": _num(PATH_RESISTANCE_OHM),
        "@DELAY_US@": str(delay_us),
        "@DELAY_S@": _num(delay_s),
        "@DELAY_PLUS_S@": _num(delay_plus_s),
    }
    deck = TEMPLATE
    for token, value in substitutions.items():
        deck = deck.replace(token, value)

    metadata = {
        "case": case_name(architecture, delay_us),
        "case_type": "prebiased_transfer",
        "architecture": architecture,
        "enable_delay_us": delay_us,
        "initial_pack_ocv_v": initial_ocv_v,
        "cap_factor": cap_factor,
        "esr_factor": esr_factor,
        "Ceq_F": c_eq_f,
        "Rpack_ohm": r_pack_ohm,
        "path_resistance_ohm": PATH_RESISTANCE_OHM,
    }
    return deck, metadata


def build_manifest_rows() -> list[dict]:
    rows = []
    order = 1
    for architecture in CANDIDATES:
        for delay_us in ENABLE_DELAYS_US:
            _, metadata = render_deck(architecture, delay_us)
            rows.append({
                "run_order": order,
                **metadata,
                "vout_initial_v": "12.0",
                "vout_target_v": "12.0",
                "iout_target_a": "1.0",
                "simulation_end_ms": str(SIMULATION_END_MS),
                "max_step_ns": str(MAX_STEP_NS),
                "steady_window_ms": STEADY_WINDOW_MS,
                "rfsw_kohm": "324",
                "rilim_kohm": "100",
                "mode": "GND_FPWM",
                "run_status": "not_run",
            })
            order += 1
    return rows


def write_matrix(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for architecture in CANDIDATES:
        for delay_us in ENABLE_DELAYS_US:
            deck, metadata = render_deck(architecture, delay_us)
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
        default=Path(__file__).with_name("transfer"),
        help="output directory (default: transfer beside this script)",
    )
    args = parser.parse_args()
    write_matrix(args.output_dir)
    print(
        f"Wrote {len(CANDIDATES) * len(ENABLE_DELAYS_US)} "
        f"prebiased output-transfer decks to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
