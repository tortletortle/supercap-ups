#!/usr/bin/env python3
"""Generate diagnostic TPS61088 load-step, overload, output-short, and VIN-scan decks.

Twelve VIN-scan cases plus twelve dynamic stress cases are generated for
RILIM=160/174 kohm. Deck generation is not simulation.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_OUT = HERE / "diagnostics"
MODEL = HERE.parent / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB"


def vin_label(vin: float) -> str:
    return str(int(vin)) if float(vin).is_integer() else f"{vin:g}".replace(".", "p")


def make_deck(vin: float, rilim_k: int, kind: str, include_rel: str) -> str:
    fault = ""
    save_fault = ""
    if kind == "loadstep":
        load = (
            "BLOAD load 0 I=if(V(load)<10,max(V(load)/10,0),"
            "if(time<15m,0.5,if(time<17m,1.0,0.5)))"
        )
        measures = """
.meas tran vload_min_step MIN V(load) FROM 15m TO 17m
.meas tran vout_min_step MIN V(vout) FROM 15m TO 17m
.meas tran il_peak_step MAX I(L1) FROM 15m TO 17m
.meas tran iin_peak_step MAX (-I(V1)) FROM 15m TO 17m
.meas tran vload_recover WHEN V(load)=11.76 RISE=1 FROM 17m TO 26m
"""
    elif kind == "overcurrent":
        # 1 A baseline -> 3 A bounded overload for 1 ms -> 1 A recovery.
        load = (
            "BLOAD load 0 I=if(V(load)<10,max(V(load)/10,0),"
            "if(time<15m,1.0,if(time<16m,3.0,1.0)))"
        )
        measures = """
.meas tran vout_min_overcurrent MIN V(vout) FROM 15m TO 16m
.meas tran peak_i_overcurrent MAX I(L1) FROM 15m TO 16m
.meas tran iin_peak_overcurrent MAX (-I(V1)) FROM 15m TO 16m
.meas tran peak_switch_sense_overcurrent MAX V(X1:ISENSE_A) FROM 15m TO 16m
.meas tran ilim_threshold_overcurrent AVG V(X1:CLIMT) FROM 15m TO 16m
.meas tran ilim_margin_overcurrent PARAM ilim_threshold_overcurrent-peak_switch_sense_overcurrent
.meas tran vout_after_overcurrent AVG V(vout) FROM 16m TO 17m
"""
    elif kind == "vinscan":
        load = "BLOAD load 0 I=min(max(V(load)/10,0),1)"
        measures = ""
    elif kind == "short":
        load = "BLOAD load 0 I=min(max(V(load)/10,0),1)"
        fault = """
* 1 ms, 0.1-ohm output short from 15 ms to 16 ms.
* This includes output-capacitor discharge; it is not a current-limited electronic load.
VSHORT short_ctrl 0 PULSE(0 5 15m 10n 10n 1m 10m)
S_SHORT vout short_node short_ctrl 0 SW_SHORT
R_SHORT short_node 0 0.1
.model SW_SHORT SW(Ron=0.01 Roff=1e9 Vt=2.5 Vh=0.1)
"""
        save_fault = " I(S_SHORT)"
        measures = """
.meas tran vout_min_short MIN V(vout) FROM 15m TO 16m
.meas tran il_peak_short MAX I(L1) FROM 15m TO 16m
.meas tran iin_peak_short MAX (-I(V1)) FROM 15m TO 16m
.meas tran peak_switch_sense_short MAX V(X1:ISENSE_A) FROM 15m TO 16m
.meas tran ilim_threshold_short AVG V(X1:CLIMT) FROM 15m TO 16m
.meas tran vout_recover WHEN V(vout)=11.76 RISE=1 FROM 16m TO 26m
"""
    else:
        raise ValueError(f"unsupported dynamic case: {kind}")

    return f"""* Diagnostic TPS61088 {kind}: VIN={vin:g} V, RILIM={rilim_k} kohm
* Uses the integration-branch TI TPS61088 macro-model; MODE=0 (FPWM).
* L1=3.3 uH nominal / 26 mohm DCR at 25 C; COUT=47 uF / 3 mohm.
* Diagnostic input only. No simulation pass or BOM approval is implied.
.include {include_rel}
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
RFSW fsw sw 324k
RILIM ilim 0 {rilim_k}k
RUP vout fb 1.076meg
RDN fb 0 120k
COUT vout 0 47u Rser=0.003
VLOAD vout load 0
{load}
{fault}
X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss sw sw sw sw vcc vin vout vout vout TPS61088_TRANS
.save V(vin) V(vout) V(load) V(sw) V(en) V(comp) V(ss) V(X1:CLIMT) V(X1:ISENSE_A) I(V1) I(L1) I(VLOAD){save_fault}
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 26m 0 25n
.meas tran t90 WHEN V(vout)=10.8 RISE=1
.meas tran t98 WHEN V(vout)=11.76 RISE=1
.meas tran sw_t6001 WHEN V(sw)=10 RISE=6001
.meas tran sw_t6101 WHEN V(sw)=10 RISE=6101
.meas tran f_sw_khz PARAM 0.1/(sw_t6101-sw_t6001)
.meas tran avg_vout AVG V(vout) FROM 24m TO 26m
.meas tran vout_min MIN V(vout) FROM 24m TO 26m
.meas tran ripple PP V(vout) FROM 24m TO 26m
.meas tran peak_start MAX I(L1) FROM 0 TO 26m
.meas tran peak_i MAX I(L1) FROM 24m TO 26m
.meas tran il_rms RMS I(L1) FROM 24m TO 26m
.meas tran peak_switch_sense MAX V(X1:ISENSE_A) FROM 0 TO 26m
.meas tran peak_switch_sense_steady MAX V(X1:ISENSE_A) FROM 24m TO 26m
.meas tran ilim_threshold AVG V(X1:CLIMT) FROM 24m TO 26m
.meas tran ilim_margin_steady PARAM ilim_threshold-peak_switch_sense_steady
.meas tran iin_avg AVG (-I(V1)) FROM 24m TO 26m
.meas tran iout_avg AVG I(VLOAD) FROM 24m TO 26m
.meas tran pin_avg AVG (-V(vin)*I(V1)) FROM 24m TO 26m
.meas tran pout_avg AVG (V(vout)*I(VLOAD)) FROM 24m TO 26m
.meas tran eta_pct PARAM 100*pout_avg/pin_avg
{measures}
.end
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not MODEL.is_file():
        raise FileNotFoundError(f"TI macro-model not found: {MODEL}")
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    include_rel = os.path.relpath(MODEL, out_dir).replace("\\", "/")
    created = []
    for vin in (7.0, 7.5, 8.0, 8.5, 9.0, 9.4):
        for rilim_k in (160, 174):
            name = f"dynamic_vin{vin_label(vin)}_rilim{rilim_k}k_vinscan.cir"
            path = out_dir / name
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite existing deck: {path}")
            path.write_text(make_deck(vin, rilim_k, "vinscan", include_rel), encoding="ascii", newline="\n")
            created.append(path)
    for vin in (7.0, 9.4):
        for rilim_k in (160, 174):
            for kind in ("loadstep", "overcurrent", "short"):
                name = f"dynamic_vin{vin_label(vin)}_rilim{rilim_k}k_{kind}.cir"
                path = out_dir / name
                if path.exists():
                    raise FileExistsError(f"Refusing to overwrite existing deck: {path}")
                path.write_text(make_deck(vin, rilim_k, kind, include_rel), encoding="ascii", newline="\n")
                created.append(path)
    print(f"Generated {len(created)} diagnostic decks in {out_dir} (12 VIN-scan + 12 dynamic stress cases)")
    for path in created:
        print(path.name)
    print("These decks have not been run; preserve all LTspice RAW/log outputs separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
