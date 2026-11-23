"""Analytical EOL hold-up model for the 4S x 10 F HCC supercapacitor pack.

This is a constant-power storage/ESR model, not a switching-converter or
hardware validation model. It intentionally uses the corrected HCC DC ESR
life limit (65 mOhm initial, 2x at EOL), not the legacy 112.5 mOhm/cell value.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

P_OUT_W = 12.0
PATH_EFFICIENCY = 0.99
TASK_S = 1.2
PACK_CUTOFF_V = 7.0
MAX_PACK_VOLTAGE_V = 9.4
BOOST_EFFICIENCIES = (0.90, 0.92, 0.94)
VFB_MIN_V = 0.581
VFB_TYP_V = 0.596
VFB_MAX_V = 0.611
R_TOP_OHM = 142_000.0
R_BOTTOM_OHM = 10_000.0
DIVIDER_TOLERANCE = 0.001


@dataclass(frozen=True)
class PackSpec:
    """Series-pack assumptions derived from the selected HCC capacitor data."""

    series_cells: int = 4
    cell_nominal_cap_f: float = 10.0
    capacity_tolerance_min: float = 0.90
    life_capacity_retention: float = 0.70
    cell_initial_dc_esr_ohm: float = 0.065
    life_esr_multiplier: float = 2.0
    pack_cutoff_v: float = PACK_CUTOFF_V

    @property
    def cell_eol_cap_f(self) -> float:
        return (
            self.cell_nominal_cap_f
            * self.capacity_tolerance_min
            * self.life_capacity_retention
        )

    @property
    def pack_equivalent_cap_f(self) -> float:
        return self.cell_eol_cap_f / self.series_cells

    @property
    def cell_eol_dc_esr_ohm(self) -> float:
        return self.cell_initial_dc_esr_ohm * self.life_esr_multiplier

    @property
    def pack_dc_esr_ohm(self) -> float:
        return self.cell_eol_dc_esr_ohm * self.series_cells


def solve_loaded_state(
    pack_ocv_v: float,
    pack_esr_ohm: float,
    capacitor_input_power_w: float,
) -> tuple[float, float] | None:
    """Return the low-current physical solution (I, Vterminal), or None.

    P = I * (Voc - I*R). The low-current root is the normal operating branch.
    """
    if pack_ocv_v <= 0.0:
        raise ValueError("pack_ocv_v must be positive")
    if pack_esr_ohm < 0.0:
        raise ValueError("pack_esr_ohm must be non-negative")
    if capacitor_input_power_w <= 0.0:
        raise ValueError("capacitor_input_power_w must be positive")

    discriminant = pack_ocv_v**2 - 4.0 * pack_esr_ohm * capacitor_input_power_w
    if discriminant <= 0.0:
        return None

    current_a = (
        2.0
        * capacitor_input_power_w
        / (pack_ocv_v + math.sqrt(discriminant))
    )
    terminal_v = pack_ocv_v - current_a * pack_esr_ohm
    return current_a, terminal_v


def hold_time_s(
    initial_pack_ocv_v: float,
    boost_efficiency: float,
    *,
    pack: PackSpec = PackSpec(),
    output_power_w: float = P_OUT_W,
    path_efficiency: float = PATH_EFFICIENCY,
) -> float:
    """Calculate time to loaded pack cutoff using the closed-form ESR model.

    The model assumes constant output power and constant Boost/path efficiency.
    It does not include cell mismatch, temperature, leakage, balancing loss,
    switching transients, converter current limit, or switchover dynamics.
    """
    return hold_time_from_pack_equivalents_s(
        initial_pack_ocv_v,
        pack.pack_equivalent_cap_f,
        pack.pack_dc_esr_ohm,
        boost_efficiency,
        pack_cutoff_v=pack.pack_cutoff_v,
        output_power_w=output_power_w,
        path_efficiency=path_efficiency,
    )


def hold_time_from_pack_equivalents_s(
    initial_pack_ocv_v: float,
    equivalent_capacitance_f: float,
    pack_dc_esr_ohm: float,
    boost_efficiency: float,
    *,
    pack_cutoff_v: float = PACK_CUTOFF_V,
    output_power_w: float = P_OUT_W,
    path_efficiency: float = PATH_EFFICIENCY,
) -> float:
    """Hold time for arbitrary series-pack Ceq/ESR, including mismatched cells."""
    if equivalent_capacitance_f <= 0.0:
        raise ValueError("equivalent_capacitance_f must be positive")
    if not 0.0 < boost_efficiency <= 1.0:
        raise ValueError("boost_efficiency must be in (0, 1]")
    if not 0.0 < path_efficiency <= 1.0:
        raise ValueError("path_efficiency must be in (0, 1]")
    if output_power_w <= 0.0:
        raise ValueError("output_power_w must be positive")

    capacitor_input_power_w = output_power_w / (
        boost_efficiency * path_efficiency
    )
    state = solve_loaded_state(
        initial_pack_ocv_v, pack_dc_esr_ohm, capacitor_input_power_w
    )
    if state is None:
        return 0.0

    _, initial_terminal_v = state
    if initial_terminal_v <= pack_cutoff_v:
        return 0.0

    resistance_power = pack_dc_esr_ohm * capacitor_input_power_w
    integral_v2 = 0.5 * (
        initial_terminal_v**2 - pack_cutoff_v**2
    ) - resistance_power * math.log(initial_terminal_v / pack_cutoff_v)
    return equivalent_capacitance_f * integral_v2 / capacitor_input_power_w


def first_cell_ovp_charge_state(
    cell_capacitances_f: tuple[float, ...] | list[float],
    cell_ovp_v: float,
) -> dict[str, float | list[float]]:
    """Ideal series-charge state when the lowest-capacitance cell first trips.

    The same charge passes through each series capacitor. This is a worst-case
    capacity-mismatch calculation, not a dynamic balancing simulation.
    """
    if len(cell_capacitances_f) < 2:
        raise ValueError("at least two series cells are required")
    if any(cap <= 0.0 for cap in cell_capacitances_f):
        raise ValueError("cell capacitances must be positive")
    if cell_ovp_v <= 0.0:
        raise ValueError("cell_ovp_v must be positive")

    weakest_cap_f = min(cell_capacitances_f)
    charge_c = weakest_cap_f * cell_ovp_v
    cell_voltages = [charge_c / cap for cap in cell_capacitances_f]
    reciprocal_capacitance = sum(1.0 / cap for cap in cell_capacitances_f)
    equivalent_capacitance_f = 1.0 / reciprocal_capacitance
    return {
        "charge_c": charge_c,
        "pack_ocv_v": sum(cell_voltages),
        "equivalent_capacitance_f": equivalent_capacitance_f,
        "first_trip_cell_v": max(cell_voltages),
        "minimum_cell_v": min(cell_voltages),
        "maximum_cell_v": max(cell_voltages),
        "cell_voltages_v": cell_voltages,
    }


def passive_balancer_current_a(
    cell_voltage_v: float,
    resistance_ohm: float,
) -> float:
    """DC current through a resistor bleeder across one capacitor cell."""
    if cell_voltage_v < 0.0:
        raise ValueError("cell_voltage_v must be non-negative")
    if resistance_ohm <= 0.0:
        raise ValueError("resistance_ohm must be positive")
    return cell_voltage_v / resistance_ohm

def minimum_initial_ocv_v(
    boost_efficiency: float,
    task_s: float = TASK_S,
    *,
    pack: PackSpec = PackSpec(),
    maximum_pack_voltage_v: float = MAX_PACK_VOLTAGE_V,
    output_power_w: float = P_OUT_W,
    path_efficiency: float = PATH_EFFICIENCY,
) -> float | None:
    """Find the minimum initial OCV for task_s, or None if max voltage fails."""
    if task_s <= 0.0:
        raise ValueError("task_s must be positive")
    if maximum_pack_voltage_v <= 0.0:
        raise ValueError("maximum_pack_voltage_v must be positive")

    maximum_hold = hold_time_s(
        maximum_pack_voltage_v,
        boost_efficiency,
        pack=pack,
        output_power_w=output_power_w,
        path_efficiency=path_efficiency,
    )
    if maximum_hold < task_s:
        return None

    low = 0.0
    high = maximum_pack_voltage_v
    for _ in range(100):
        midpoint = (low + high) / 2.0
        if hold_time_s(
            midpoint,
            boost_efficiency,
            pack=pack,
            output_power_w=output_power_w,
            path_efficiency=path_efficiency,
        ) >= task_s:
            high = midpoint
        else:
            low = midpoint
    return high


def buck_output_corners_v(
    *,
    vfb_min_v: float = VFB_MIN_V,
    vfb_typ_v: float = VFB_TYP_V,
    vfb_max_v: float = VFB_MAX_V,
    r_top_ohm: float = R_TOP_OHM,
    r_bottom_ohm: float = R_BOTTOM_OHM,
    divider_tolerance: float = DIVIDER_TOLERANCE,
) -> dict[str, float]:
    """Static TPS54302 output corners for the documented FB divider.

    This computes the Buck output node, not the actual capacitor-pack voltage.
    The series blocking diode and current-sense path can only reduce the pack
    voltage relative to this node while charging.
    """
    if min(vfb_min_v, vfb_typ_v, vfb_max_v, r_top_ohm, r_bottom_ohm) <= 0.0:
        raise ValueError("feedback and resistor values must be positive")
    if not 0.0 <= divider_tolerance < 1.0:
        raise ValueError("divider_tolerance must be in [0, 1)")

    gain_min = 1.0 + (
        r_top_ohm * (1.0 - divider_tolerance)
        / (r_bottom_ohm * (1.0 + divider_tolerance))
    )
    gain_nom = 1.0 + r_top_ohm / r_bottom_ohm
    gain_max = 1.0 + (
        r_top_ohm * (1.0 + divider_tolerance)
        / (r_bottom_ohm * (1.0 - divider_tolerance))
    )
    return {
        "minimum_v": vfb_min_v * gain_min,
        "nominal_v": vfb_typ_v * gain_nom,
        "maximum_v": vfb_max_v * gain_max,
    }


def worst_low_cv_if_high_corner_limited_v(
    maximum_output_v: float = MAX_PACK_VOLTAGE_V,
    *,
    vfb_min_v: float = VFB_MIN_V,
    vfb_max_v: float = VFB_MAX_V,
    r_top_ohm: float = R_TOP_OHM,
    r_bottom_ohm: float = R_BOTTOM_OHM,
    divider_tolerance: float = DIVIDER_TOLERANCE,
) -> float:
    """Worst-low output if the divider is scaled so its worst-high is max V."""
    if maximum_output_v <= 0.0:
        raise ValueError("maximum_output_v must be positive")
    gain_min = 1.0 + (
        r_top_ohm * (1.0 - divider_tolerance)
        / (r_bottom_ohm * (1.0 + divider_tolerance))
    )
    gain_max = 1.0 + (
        r_top_ohm * (1.0 + divider_tolerance)
        / (r_bottom_ohm * (1.0 - divider_tolerance))
    )
    return maximum_output_v * (vfb_min_v * gain_min) / (vfb_max_v * gain_max)


def build_voltage_matrix(
    initial_pack_ocv_values_v: tuple[float, ...] = (8.815, 9.059, 9.305, 9.4),
    efficiencies: tuple[float, ...] = BOOST_EFFICIENCIES,
    *,
    pack: PackSpec = PackSpec(),
) -> list[dict[str, float | bool]]:
    """Build a sensitivity matrix using assumed pack OCVs.

    Voltage points are scenario inputs, not measured pack voltages. In
    particular, Buck-output corners are optimistic upper bounds for the pack.
    """
    rows: list[dict[str, float | bool]] = []
    for initial_v in initial_pack_ocv_values_v:
        for efficiency in efficiencies:
            hold = hold_time_s(initial_v, efficiency, pack=pack)
            rows.append({
                "assumed_initial_pack_ocv_v": initial_v,
                "boost_efficiency": efficiency,
                "hold_time_s": hold,
                "pass_1p2s": hold >= TASK_S,
            })
    return rows


def main() -> None:
    import csv
    import sys

    rows = build_voltage_matrix()
    writer = csv.DictWriter(
        sys.stdout, fieldnames=list(rows[0].keys()), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
