#!/usr/bin/env python3
"""First-order feasibility model for the LTC3350 4S x 10 F UPS candidate.

This is an energy/current budget, not a switching-regulator or thermal simulation.
All assumptions are explicit so the model can be reproduced and replaced with
measured values later.
"""
from dataclasses import dataclass
from math import log, sqrt


@dataclass(frozen=True)
class Design:
    cells: int = 4
    cell_cap_eol_f: float = 6.3
    cell_esr_eol_ohm: float = 0.1125
    output_power_w: float = 12.0
    output_path_efficiency: float = 0.99
    backup_efficiency: float = 0.80
    pack_cutoff_v: float = 7.102
    vcap_ref_v: float = 1.2
    vcap_rtop_ohm: float = 86_600.0
    vcap_rbottom_ohm: float = 11_800.0
    vcap_ref_tolerance: float = 0.02
    divider_ratio_tolerance: float = 0.002
    capfb_leakage_a: float = 50e-9
    vout_rtop_ohm: float = 90_000.0
    vout_rbottom_ohm: float = 10_000.0
    voutfb_leakage_a: float = 50e-9
    vshunt_v: float = 2.6
    ballast_ohm: float = 2.7
    ballast_tolerance: float = 0.05
    r_sns_i1_ohm: float = 0.016
    r_sns_i2_ohm: float = 0.075
    r_sns_c_ohm: float = 0.008
    vin_v: float = 12.0
    system_load_a: float = 1.0
    charge_efficiency: float = 0.90


def pack_capacitance(design: Design) -> float:
    return design.cell_cap_eol_f / design.cells


def pack_esr(design: Design) -> float:
    return design.cell_esr_eol_ohm * design.cells


def hold_time_s(voc_v: float, design: Design, backup_efficiency: float | None = None) -> float:
    """Constant-power discharge with series ESR, using loaded terminal cutoff."""
    eta = design.backup_efficiency if backup_efficiency is None else backup_efficiency
    p_pack = design.output_power_w / (design.output_path_efficiency * eta)
    r_pack = pack_esr(design)
    c_pack = pack_capacitance(design)
    discriminant = voc_v * voc_v - 4.0 * r_pack * p_pack
    if discriminant <= 0:
        return 0.0
    v_loaded_start = (voc_v + sqrt(discriminant)) / 2.0
    if v_loaded_start <= design.pack_cutoff_v:
        return 0.0
    integral = (
        (v_loaded_start * v_loaded_start - design.pack_cutoff_v**2) / 2.0
        - r_pack * p_pack * log(v_loaded_start / design.pack_cutoff_v)
    )
    return c_pack * integral / p_pack


def required_vcap_v(target_s: float, design: Design, backup_efficiency: float | None = None) -> float:
    low = design.pack_cutoff_v
    high = 20.0
    for _ in range(100):
        middle = (low + high) / 2.0
        if hold_time_s(middle, design, backup_efficiency) < target_s:
            low = middle
        else:
            high = middle
    return high


def vcap_window(design: Design) -> tuple[float, float, float, float]:
    nominal = design.vcap_ref_v * (1.0 + design.vcap_rtop_ohm / design.vcap_rbottom_ohm)
    leakage_fraction = design.capfb_leakage_a * design.vcap_rtop_ohm / nominal
    total_fraction = design.vcap_ref_tolerance + design.divider_ratio_tolerance + leakage_fraction
    return nominal, nominal * (1.0 - total_fraction), nominal * (1.0 + total_fraction), total_fraction


def vout_window(design: Design) -> tuple[float, float, float, float]:
    nominal = design.vcap_ref_v * (1.0 + design.vout_rtop_ohm / design.vout_rbottom_ohm)
    leakage_fraction = design.voutfb_leakage_a * design.vout_rtop_ohm / nominal
    total_fraction = design.vcap_ref_tolerance + design.divider_ratio_tolerance + leakage_fraction
    return nominal, nominal * (1.0 - total_fraction), nominal * (1.0 + total_fraction), total_fraction


def shunt_budget(design: Design) -> tuple[float, float, float, float]:
    r_max = design.ballast_ohm * (1.0 + design.ballast_tolerance)
    r_min = design.ballast_ohm * (1.0 - design.ballast_tolerance)
    # LTC3350 typical shunt-current approximation: VSHUNT / (2 * RSHUNT).
    min_current = design.vshunt_v / (2.0 * r_max)
    # The data sheet states that the shunt switches have up to 75% duty cycle.
    average_current_ceiling = 0.75 * min_current
    max_resistor_power = 3.0 * design.vshunt_v**2 / (16.0 * r_min)
    nominal_current = design.vshunt_v / (2.0 * design.ballast_ohm)
    return nominal_current, min_current, average_current_ceiling, max_resistor_power


def input_charge_budget(design: Design) -> dict[str, float]:
    r_total = design.r_sns_i1_ohm + design.r_sns_i2_ohm
    i_charge_no_load = 0.032 / r_total
    i_charge_at_load = i_charge_no_load - (
        design.r_sns_i1_ohm / r_total
    ) * design.system_load_a
    vcap_nominal = vcap_window(design)[0]
    i_pack_no_load = (
        i_charge_no_load * design.vin_v * design.charge_efficiency / vcap_nominal
    )
    i_pack_at_load = (
        i_charge_at_load * design.vin_v * design.charge_efficiency / vcap_nominal
    )
    i_pack_no_load_ideal = i_charge_no_load * design.vin_v / vcap_nominal
    i_pack_at_load_ideal = i_charge_at_load * design.vin_v / vcap_nominal
    return {
        "input_charge_current_no_load_a": i_charge_no_load,
        "input_charge_current_at_1a_load_a": i_charge_at_load,
        "pack_charge_current_no_load_a": i_pack_no_load,
        "pack_charge_current_at_1a_load_a": i_pack_at_load,
        "pack_charge_current_no_load_100pct_eff_a": i_pack_no_load_ideal,
        "pack_charge_current_at_1a_load_100pct_eff_a": i_pack_at_load_ideal,
        "total_input_current_at_1a_load_a": design.system_load_a + i_charge_at_load,
    }


def simulate_weak_cell_discharge(
    design: Design,
    cell_capacities_f: list[float],
    cell_esrs_ohm: list[float],
    initial_pack_voltage_v: float,
    cell_cutoff_v: float = 1.0,
    dt_s: float = 1e-4,
) -> dict[str, float | str]:
    """Euler simulation with equalized initial cell voltages and common series charge."""
    if len(cell_capacities_f) != design.cells or len(cell_esrs_ohm) != design.cells:
        raise ValueError("one capacitance and ESR value is required per cell")
    initial_cell_v = initial_pack_voltage_v / design.cells
    charge_c = 0.0
    elapsed_s = 0.0
    p_pack = design.output_power_w / (
        design.output_path_efficiency * design.backup_efficiency
    )
    r_pack = sum(cell_esrs_ohm)

    while elapsed_s < 20.0:
        cell_ocv = [
            initial_cell_v - charge_c / capacitance
            for capacitance in cell_capacities_f
        ]
        pack_ocv = sum(cell_ocv)
        discriminant = pack_ocv**2 - 4.0 * r_pack * p_pack
        if discriminant <= 0.0:
            return {"time_s": elapsed_s, "reason": "power-collapse", "min_cell_v": min(cell_ocv)}
        pack_loaded_v = (pack_ocv + sqrt(discriminant)) / 2.0
        pack_current_a = p_pack / pack_loaded_v
        cell_loaded_v = [
            voltage - pack_current_a * resistance
            for voltage, resistance in zip(cell_ocv, cell_esrs_ohm)
        ]
        if pack_loaded_v <= design.pack_cutoff_v:
            return {
                "time_s": elapsed_s,
                "reason": "pack-cutoff",
                "pack_loaded_v": pack_loaded_v,
                "min_cell_v": min(cell_loaded_v),
            }
        if min(cell_loaded_v) <= cell_cutoff_v:
            return {
                "time_s": elapsed_s,
                "reason": "cell-cutoff",
                "pack_loaded_v": pack_loaded_v,
                "min_cell_v": min(cell_loaded_v),
            }
        charge_c += pack_current_a * dt_s
        elapsed_s += dt_s

    return {"time_s": elapsed_s, "reason": "timeout", "min_cell_v": min(cell_loaded_v)}


def main() -> None:
    d = Design()
    vnom, vmin, vmax, vtol = vcap_window(d)
    out_nom, out_min, out_max, out_tol = vout_window(d)
    shunt_nom, shunt_min, shunt_avg_ceiling, shunt_pmax = shunt_budget(d)
    charge = input_charge_budget(d)
    vshunt_code = round(d.vshunt_v / 183.5e-6)
    vshunt_actual = vshunt_code * 183.5e-6

    print("LTC3350 4S x 10F first-order candidate")
    print(f"VCAP target: {vnom:.4f} V; worst-case window: {vmin:.4f}..{vmax:.4f} V ({vtol*100:.3f}%)")
    print(f"VOUT target: {out_nom:.4f} V; worst-case window: {out_min:.4f}..{out_max:.4f} V ({out_tol*100:.3f}%)")
    print(f"VSHUNT code: 0x{vshunt_code:04X}; quantized value: {vshunt_actual:.6f} V")
    print(f"Shunt current: {shunt_nom:.3f} A nominal, {shunt_min:.3f} A at +5% ballast")
    print(f"Shunt average-current envelope at 75% duty: {shunt_avg_ceiling:.3f} A")
    print(f"Maximum ballast resistor dissipation estimate: {shunt_pmax:.3f} W (use >=2 W part)")
    print(f"R_SNSC peak current-limit estimate: {0.058 / d.r_sns_c_ohm:.2f} A")
    print(f"Input/charge budget: {charge}")
    print(f"EOL pack C={pack_capacitance(d):.4f} F, ESR={pack_esr(d):.4f} ohm")
    print(f"Hold time at worst-low VCAP, 80% backup efficiency: {hold_time_s(vmin, d, 0.80):.4f} s")
    print(f"Hold time at worst-low VCAP, 85% backup efficiency: {hold_time_s(vmin, d, 0.85):.4f} s")
    print(f"Hold time at worst-low VCAP, 90% backup efficiency: {hold_time_s(vmin, d, 0.90):.4f} s")
    print(f"Required initial VCAP for 1.2 s at 80% efficiency: {required_vcap_v(1.2, d, 0.80):.4f} V")
    weak = simulate_weak_cell_discharge(
        d,
        cell_capacities_f=[6.3, 9.0, 9.0, 9.0],
        cell_esrs_ohm=[0.1125, 0.075, 0.075, 0.075],
        initial_pack_voltage_v=vmin,
    )
    print(f"Equalized-start weak-cell case (6.3 F + 3 x 9 F): {weak}")

    assert vmin < vmax
    assert hold_time_s(vmin, d, 0.80) > 1.2
    assert weak["reason"] == "pack-cutoff"
    assert weak["min_cell_v"] > 1.0
    assert shunt_avg_ceiling < charge["pack_charge_current_no_load_100pct_eff_a"]
    assert shunt_avg_ceiling > charge["pack_charge_current_at_1a_load_100pct_eff_a"]
    assert charge["total_input_current_at_1a_load_a"] < 1.5
    assert 0x0000 <= vshunt_code <= 0xFFFF


if __name__ == "__main__":
    main()
