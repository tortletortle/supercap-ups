#!/usr/bin/env python3
"""EOL hold-time sensitivity to assumed Boost efficiency for current 4Sx20F mainline.

This is a system energy-budget sensitivity, not a TPS61088 device-level
efficiency measurement. Values are aligned to power-stage-integration:
4x11.2 F, 106 mOhm/cell, 9.0 V initial pack OCV, 100/150 mOhm external
input path, 145 mOhm output path, 12 V/1 A load, and a 7.0 V Boost evidence
floor. It intentionally does not reuse the V1.4 4Sx10F/130 mOhm-cell case.
"""
from __future__ import annotations

import argparse
import csv
from math import log, sqrt
from pathlib import Path

CELLS = 4
CELL_CAP_F = 11.2
CELL_ESR_OHM = 0.106
INITIAL_PACK_OCV_V = 9.0
PACK_UVLO_EARLIEST_V = 7.110123
BOOST_EVIDENCE_FLOOR_V = 7.0
LOAD_V = 12.0
LOAD_A = 1.0
OUTPUT_PATH_OHM = 0.145
TARGET_HOLD_S = 1.2
INPUT_PATHS_OHM = (0.100, 0.150)


def hold_time(boost_efficiency: float, input_path_ohm: float) -> dict[str, float]:
    if not 0 < boost_efficiency <= 1:
        raise ValueError("boost_efficiency must be in (0, 1]")
    if input_path_ohm < 0:
        raise ValueError("input_path_ohm must be non-negative")

    p_out = LOAD_V * LOAD_A + LOAD_A**2 * OUTPUT_PATH_OHM
    p_in = p_out / boost_efficiency
    r_total = CELLS * CELL_ESR_OHM + input_path_ohm
    c_pack = CELL_CAP_F / CELLS

    start_disc = INITIAL_PACK_OCV_V**2 - 4 * r_total * p_in
    if start_disc <= 0:
        return {"hold_s": 0.0, "p_in_w": p_in, "loaded_start_v": 0.0,
                "cutoff_v": BOOST_EVIDENCE_FLOOR_V}
    loaded_start_v = (INITIAL_PACK_OCV_V + sqrt(start_disc)) / 2

    uvlo_disc = PACK_UVLO_EARLIEST_V**2 - 4 * input_path_ohm * p_in
    translated_uvlo_v = (
        (PACK_UVLO_EARLIEST_V + sqrt(uvlo_disc)) / 2
        if uvlo_disc > 0 else 0.0
    )
    cutoff_v = max(BOOST_EVIDENCE_FLOOR_V, translated_uvlo_v)

    if loaded_start_v <= cutoff_v:
        hold_s = 0.0
    else:
        hold_s = c_pack / p_in * (
            0.5 * (loaded_start_v**2 - cutoff_v**2)
            - r_total * p_in * log(loaded_start_v / cutoff_v)
        )
    return {
        "hold_s": hold_s,
        "p_in_w": p_in,
        "loaded_start_v": loaded_start_v,
        "cutoff_v": cutoff_v,
    }


def minimum_efficiency(input_path_ohm: float) -> float:
    low, high = 0.50, 0.999
    if hold_time(high, input_path_ohm)["hold_s"] < TARGET_HOLD_S:
        return float("nan")
    for _ in range(100):
        mid = (low + high) / 2
        if hold_time(mid, input_path_ohm)["hold_s"] >= TARGET_HOLD_S:
            high = mid
        else:
            low = mid
    return high


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data" / "eol_efficiency_budget_sensitivity_4s20f.csv",
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for efficiency_pct in range(75, 96):
        efficiency = efficiency_pct / 100
        row = {"boost_efficiency_pct": efficiency_pct}
        for path_ohm in INPUT_PATHS_OHM:
            result = hold_time(efficiency, path_ohm)
            key = int(round(path_ohm * 1000))
            row[f"hold_s_at_{key}mohm_input_path"] = f"{result['hold_s']:.6f}"
            row[f"margin_ms_at_{key}mohm"] = f"{(result['hold_s'] - TARGET_HOLD_S) * 1000:.1f}"
        row["model_scope"] = (
            "4Sx20F EOL constant-power budget; not TPS61088 device-level measurement"
        )
        rows.append(row)

    with args.out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    eta100 = minimum_efficiency(0.100)
    eta150 = minimum_efficiency(0.150)
    h85_100 = hold_time(0.85, 0.100)["hold_s"]
    h85_150 = hold_time(0.85, 0.150)["hold_s"]
    print(f"85% / 100 mOhm: {h85_100:.6f} s")
    print(f"85% / 150 mOhm: {h85_150:.6f} s")
    print(f"Minimum efficiency for 1.2 s / 100 mOhm: {eta100 * 100:.3f}%")
    print(f"Minimum efficiency for 1.2 s / 150 mOhm: {eta150 * 100:.3f}%")

    assert abs(h85_100 - 1.374803) < 1e-5
    assert abs(h85_150 - 1.215724) < 1e-5
    assert 80.0 < eta100 * 100 < 80.2
    assert 84.5 < eta150 * 100 < 84.7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
