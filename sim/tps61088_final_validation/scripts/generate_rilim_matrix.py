#!/usr/bin/env python3
"""Generate the 12-case TPS61088 VIN/RILIM matrix with current-limit probes."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
MODEL = HERE.parent / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB"
RILIM_KOHM = (100, 160, 174, 180, 200, 220)
VIN_CASES = ((7.0, "7"), (9.4, "9p4"))


def make_deck(vin: float, rilim_kohm: int, include_rel: str, max_step_ns: float) -> str:
    return f"""* TPS61088 final RILIM matrix: VIN={vin:g} V, RILIM={rilim_kohm} kohm
* Current project baseline: 4Sx20F power-stage integration.
* RFSW=324 kohm remains an experimental candidate; frequency closure is a prerequisite.
* MODE=0 (FPWM); L1 nominal 3.3 uH, DCR=26 mohm at 25 C; COUT=47 uF.
* Macro-model current limit is nominal/typical only; no temperature or silicon corners.
* 1 A baseline load, 3 A bounded 1 ms overload pulse (15-16 ms), then recovery.
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
RILIM ilim 0 {rilim_kohm}k
RUP vout fb 1.076meg
RDN fb 0 120k
COUT vout 0 47u Rser=0.003
VLOAD vout load 0
BLOAD load 0 I=if(V(load)<10,max(V(load)/10,0),if(time<15m,1.0,if(time<16m,3.0,1.0)))
X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss sw sw sw sw vcc vin vout vout vout TPS61088_TRANS
.save V(vin) V(vout) V(load) V(sw) V(en) V(comp) V(ss) V(X1:CLIMT) V(X1:ISENSE_A) I(V1) I(L1) I(VLOAD)
.options method=gear reltol=.003 trtol=7 gmin=1e-10 numdgt=7 threads=1 plotwinsize=0
.tran 0 26m 0 {max_step_ns:g}n
.meas tran t90 WHEN V(vout)=10.8 RISE=1
.meas tran t98 WHEN V(vout)=11.76 RISE=1
.meas tran sw_t6001 WHEN V(sw)=10 RISE=6001
.meas tran sw_t6101 WHEN V(sw)=10 RISE=6101
.meas tran f_sw_khz PARAM 0.1/(sw_t6101-sw_t6001)
.meas tran avg_vout AVG V(vout) FROM 24m TO 26m
.meas tran vout_min MIN V(vout) FROM 24m TO 26m
.meas tran ripple PP V(vout) FROM 24m TO 26m
.meas tran peak_i MAX I(L1) FROM 24m TO 26m
.meas tran peak_start MAX I(L1) FROM 0 TO 26m
.meas tran peak_i_steady MAX I(L1) FROM 24m TO 26m
.meas tran il_rms RMS I(L1) FROM 24m TO 26m
.meas tran peak_switch_sense MAX V(X1:ISENSE_A) FROM 0 TO 26m
.meas tran peak_switch_sense_steady MAX V(X1:ISENSE_A) FROM 24m TO 26m
.meas tran ilim_threshold AVG V(X1:CLIMT) FROM 24m TO 26m
.meas tran ilim_threshold_min MIN V(X1:CLIMT) FROM 24m TO 26m
.meas tran ilim_threshold_max MAX V(X1:CLIMT) FROM 24m TO 26m
.meas tran ilim_margin_steady PARAM ilim_threshold-peak_switch_sense_steady
.meas tran vout_min_overcurrent MIN V(vout) FROM 15m TO 16m
.meas tran peak_i_overcurrent MAX I(L1) FROM 15m TO 16m
.meas tran peak_switch_sense_overcurrent MAX V(X1:ISENSE_A) FROM 15m TO 16m
.meas tran ilim_threshold_overcurrent AVG V(X1:CLIMT) FROM 15m TO 16m
.meas tran ilim_margin_overcurrent PARAM ilim_threshold_overcurrent-peak_switch_sense_overcurrent
.meas tran iin_peak_overcurrent MAX (-I(V1)) FROM 15m TO 16m
.meas tran vout_after_overcurrent AVG V(vout) FROM 16m TO 17m
.meas tran iin_avg AVG (-I(V1)) FROM 24m TO 26m
.meas tran iout_avg AVG I(VLOAD) FROM 24m TO 26m
.meas tran pin_avg AVG (-V(vin)*I(V1)) FROM 24m TO 26m
.meas tran pout_avg AVG (V(vout)*I(VLOAD)) FROM 24m TO 26m
.meas tran eta_pct PARAM 100*pout_avg/pin_avg
.end
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=HERE / "netlists")
    parser.add_argument("--max-step-ns", type=float, default=25.0)
    args = parser.parse_args()
    if not MODEL.is_file():
        raise FileNotFoundError(f"TPS61088 macro-model missing: {MODEL}")
    if args.max_step_ns <= 0:
        raise ValueError("max-step-ns must be positive")
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    include_rel = os.path.relpath(MODEL, out_dir).replace("\\", "/")
    outputs = []
    for vin, label in VIN_CASES:
        for rilim in RILIM_KOHM:
            path = out_dir / f"ilim_vin{label}_rilim{rilim}k.cir"
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite existing deck: {path}")
            path.write_text(make_deck(vin, rilim, include_rel, args.max_step_ns), encoding="ascii", newline="\n")
            outputs.append(path)
    print(f"Generated {len(outputs)} RILIM decks in {out_dir}")
    for path in outputs:
        print(path.name)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
