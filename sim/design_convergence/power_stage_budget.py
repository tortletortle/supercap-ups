#!/usr/bin/env python3
"""EOL 4S supercapacitor UPS hold-time and protection-window budget.

No third-party dependencies. This is a constant-power, lumped-ESR screening
model; it is not a switching-converter or thermal qualification model.
"""
from __future__ import annotations

from math import log, sqrt

CELLS = 4
CELL_CAP_F = 11.2                 # 20 F * -20% initial tolerance * 70% EOL factor
CELL_DC_ESR_OHM = 0.106           # 2 * 53 mOhm stress assumption; measure on samples
INITIAL_PACK_OCV_V = 9.0
PACK_UVLO_EARLIEST_V = 7.110123
BOOST_EVIDENCE_FLOOR_V = 7.0
LOAD_V = 12.0
LOAD_A = 1.0
OUTPUT_PATH_OHM = 0.145           # TPS2121 + TPS25947 hot-path budget
TARGET_HOLD_S = 1.2
PACK_MAX_V = 9.4
CV_STATIC_MIN_V = 9.0580
CV_STATIC_MAX_V = 9.0921
PACK_OVP_STATIC_MIN_V = 9.2451
PACK_OVP_STATIC_MAX_V = 9.3049
CELL_OVP_STATIC_MAX_V = 2.551
CELL_RATED_MAX_V = 2.7


def hold_time(boost_efficiency: float, pack_path_ohm: float,
              initial_pack_ocv_v: float = INITIAL_PACK_OCV_V) -> dict[str, float]:
    """Return hold time and useful corner quantities for one operating corner."""
    if not 0 < boost_efficiency <= 1:
        raise ValueError("boost_efficiency must be in (0, 1]")
    if pack_path_ohm < 0:
        raise ValueError("pack_path_ohm must be non-negative")

    p_out = LOAD_V * LOAD_A + LOAD_A**2 * OUTPUT_PATH_OHM
    p_in = p_out / boost_efficiency
    r_total = CELLS * CELL_DC_ESR_OHM + pack_path_ohm
    c_pack = CELL_CAP_F / CELLS

    start_discriminant = initial_pack_ocv_v**2 - 4 * r_total * p_in
    if start_discriminant <= 0:
        return {"hold_s": 0.0, "p_in_w": p_in, "loaded_start_v": 0.0,
                "cutoff_v": BOOST_EVIDENCE_FLOOR_V, "cutoff_current_a": 0.0}
    loaded_start_v = (
        initial_pack_ocv_v + sqrt(start_discriminant)
    ) / 2

    # Pack UVLO is measured before the series discharge path. Translate it
    # to the Boost input node: Vpack = Vboost + Rpath * P / Vboost.
    uvlo_discriminant = PACK_UVLO_EARLIEST_V**2 - 4 * pack_path_ohm * p_in
    translated_uvlo_v = (
        (PACK_UVLO_EARLIEST_V + sqrt(uvlo_discriminant)) / 2
        if uvlo_discriminant > 0 else 0.0
    )
    cutoff_v = max(BOOST_EVIDENCE_FLOOR_V, translated_uvlo_v)
    if loaded_start_v <= cutoff_v:
        hold_s = 0.0
    else:
        hold_s = c_pack / p_in * (
            0.5 * (loaded_start_v**2 - cutoff_v**2)
            - r_total * p_in * log(loaded_start_v / cutoff_v)
        )

    cutoff_current_a = p_in / cutoff_v
    return {
        "hold_s": hold_s,
        "p_in_w": p_in,
        "loaded_start_v": loaded_start_v,
        "translated_uvlo_v": translated_uvlo_v,
        "cutoff_v": cutoff_v,
        "cutoff_current_a": cutoff_current_a,
        "pack_path_drop_v": cutoff_current_a * pack_path_ohm,
        "pack_path_loss_w": cutoff_current_a**2 * pack_path_ohm,
        "cell_esr_loss_w": cutoff_current_a**2 * CELL_DC_ESR_OHM,
    }


def max_path_for_hold(boost_efficiency: float, target_s: float) -> float:
    """Bisection estimate of the maximum extra pack-path resistance."""
    low, high = 0.0, 0.5
    if hold_time(boost_efficiency, low)["hold_s"] < target_s:
        return 0.0
    for _ in range(80):
        mid = (low + high) / 2
        if hold_time(boost_efficiency, mid)["hold_s"] >= target_s:
            low = mid
        else:
            high = mid
    return low


def main() -> None:
    print("EOL 4S / 12 W / 1.2 s screening budget")
    print(f"Cell model: {CELL_CAP_F:.2f} F, {CELL_DC_ESR_OHM * 1e3:.1f} mOhm per cell")
    print(f"Initial pack OCV: {INITIAL_PACK_OCV_V:.3f} V; hard pack maximum: {PACK_MAX_V:.3f} V")
    print(f"Output path: {OUTPUT_PATH_OHM * 1e3:.1f} mOhm; Boost evidence floor: {BOOST_EVIDENCE_FLOOR_V:.3f} V")
    print()
    print("efficiency,path_mOhm,hold_s,loaded_start_V,cutoff_V,cutoff_I_A")
    for efficiency in (0.85, 0.90):
        for path_mohm in (50, 100, 150, 200):
            row = hold_time(efficiency, path_mohm / 1000)
            print(f"{efficiency:.2f},{path_mohm},{row['hold_s']:.6f},"
                  f"{row['loaded_start_v']:.6f},{row['cutoff_v']:.6f},"
                  f"{row['cutoff_current_a']:.6f}")

    p85_100 = hold_time(0.85, 0.100)
    r_limit = max_path_for_hold(0.85, TARGET_HOLD_S)
    print()
    print(f"85% efficiency, 100 mOhm path margin: "
          f"{(p85_100['hold_s'] - TARGET_HOLD_S) * 1000:.1f} ms")
    print(f"85% efficiency model path limit for 1.2 s: {r_limit * 1000:.2f} mOhm")
    print(f"At 7 V Boost input: {p85_100['cutoff_current_a']:.3f} A")
    print(f"At that current: input-path drop={p85_100['pack_path_drop_v']:.3f} V, "
          f"input-path loss={p85_100['pack_path_loss_w']:.3f} W, "
          f"each cell ESR loss={p85_100['cell_esr_loss_w']:.3f} W")

    print()
    print(f"CV-to-earliest-pack-OVP static gap: "
          f"{(PACK_OVP_STATIC_MIN_V - CV_STATIC_MAX_V) * 1000:.1f} mV")
    print(f"Latest pack OVP to 9.4 V hard limit: "
          f"{(PACK_MAX_V - PACK_OVP_STATIC_MAX_V) * 1000:.1f} mV")
    print(f"Cell OVP high corner to 2.7 V rating: "
          f"{(CELL_RATED_MAX_V - CELL_OVP_STATIC_MAX_V) * 1000:.1f} mV")

    # Regression guards for the current documented candidate.
    assert p85_100["hold_s"] >= TARGET_HOLD_S
    assert hold_time(0.85, 0.150)["hold_s"] >= TARGET_HOLD_S
    assert hold_time(0.85, 0.200)["hold_s"] < TARGET_HOLD_S
    assert 150e-3 < r_limit < 160e-3
    assert CV_STATIC_MAX_V < PACK_OVP_STATIC_MIN_V
    assert PACK_OVP_STATIC_MAX_V < PACK_MAX_V
    assert CELL_OVP_STATIC_MAX_V < CELL_RATED_MAX_V


if __name__ == "__main__":
    main()
