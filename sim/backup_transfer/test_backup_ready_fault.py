#!/usr/bin/env python3
"""Regression tests for fail-safe BACKUP_READY qualification.

This is a behavioral contract model, not a transistor-level TPS25947 model.
The RC and diagnostic-pulse values are explicit screening assumptions and
must be replaced by final schematic values before hardware sign-off.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp
import unittest


# Illustrative values shared with check_residual_input.py.
IN2_INITIAL_V = 12.0
IN2_BLEED_OHM = 10_000.0
IN2_COUT_F = 100e-6
MUX_UV_EXAMPLE_V = 2.8

# First-pass diagnostic load test. These are test assumptions, not frozen BOM.
PROOF_LOAD_A = 1.0
PROOF_LOAD_S = 200e-6
EFUSE_PATH_R_OHM = 45e-3
MAX_PROOF_PATH_DROP_V = 100e-3
PROOF_LOAD_VMIN_V = 11.8


@dataclass(frozen=True)
class BackupState:
    """Inputs to the system-level backup qualification latch."""

    pack_uv_ok: bool = False
    cell_protect_valid: bool = False
    cell_alert_ok: bool = False
    discharge_armed: bool = False
    boost_en: bool = False
    boost_input_voltage_v: float = 0.0
    efuse_status_ok: bool = False
    load_test_pass: bool = False
    load_test_fresh: bool = False
    fault_latched: bool = True
    startup_timeout: bool = False


def backup_ready(
    state: BackupState,
    *,
    boost_v_min: float = 11.8,
    boost_v_max: float = 12.6,
) -> bool:
    """Active-high, fail-safe qualification; every term is required."""
    return (
        state.pack_uv_ok
        and state.cell_protect_valid
        and state.cell_alert_ok
        and state.discharge_armed
        and state.boost_en
        and boost_v_min <= state.boost_input_voltage_v <= boost_v_max
        and state.efuse_status_ok
        and state.load_test_pass
        and state.load_test_fresh
        and not state.fault_latched
        and not state.startup_timeout
    )


def ov2_inhibit(state: BackupState) -> bool:
    """Active-high system intent: inhibit TPS2121 IN2 unless fully qualified."""
    return not backup_ready(state)


def residual_voltage(
    initial_v: float = IN2_INITIAL_V,
    elapsed_s: float = 1e-3,
    bleed_ohm: float = IN2_BLEED_OHM,
    capacitance_f: float = IN2_COUT_F,
) -> float:
    """Unloaded first-order RC residual; illustrative, not a fitted board model."""
    return initial_v * exp(-elapsed_s / (bleed_ohm * capacitance_f))


def diagnostic_load_test(
    *,
    input_v: float,
    output_v_initial: float,
    output_cap_f: float,
    load_a: float = PROOF_LOAD_A,
    pulse_s: float = PROOF_LOAD_S,
    path_r_ohm: float = EFUSE_PATH_R_OHM,
    max_path_drop_v: float = MAX_PROOF_PATH_DROP_V,
    min_output_v: float = PROOF_LOAD_VMIN_V,
) -> dict[str, float | bool]:
    """Compare a live pass path with a charged-but-isolated output capacitor.

    The live-path result uses I*R. The isolated result uses I*dt/C. This is a
    simple discriminating test model, not an eFuse macro-model.
    """
    if output_cap_f <= 0:
        raise ValueError("output_cap_f must be positive")
    healthy_vout = input_v - load_a * path_r_ohm
    isolated_vout = output_v_initial - load_a * pulse_s / output_cap_f
    healthy_drop = input_v - healthy_vout
    isolated_drop = input_v - isolated_vout
    return {
        "healthy_vout": healthy_vout,
        "isolated_vout": isolated_vout,
        "healthy_drop": healthy_drop,
        "isolated_drop": isolated_drop,
        "healthy_pass": healthy_vout >= min_output_v
        and healthy_drop <= max_path_drop_v,
        "isolated_pass": isolated_vout >= min_output_v
        and isolated_drop <= max_path_drop_v,
    }


def fully_qualified_state(**overrides: object) -> BackupState:
    values: dict[str, object] = {
        "pack_uv_ok": True,
        "cell_protect_valid": True,
        "cell_alert_ok": True,
        "discharge_armed": True,
        "boost_en": True,
        "boost_input_voltage_v": 12.0,
        "efuse_status_ok": True,
        "load_test_pass": True,
        "load_test_fresh": True,
        "fault_latched": False,
        "startup_timeout": False,
    }
    values.update(overrides)
    return BackupState(**values)  # type: ignore[arg-type]


class BackupReadyFaultTests(unittest.TestCase):
    def test_default_state_is_not_ready_and_inhibits_in2(self) -> None:
        state = BackupState()
        self.assertFalse(backup_ready(state))
        self.assertTrue(ov2_inhibit(state))

    def test_nominal_fully_qualified_source_is_ready(self) -> None:
        state = fully_qualified_state()
        self.assertTrue(backup_ready(state))
        self.assertFalse(ov2_inhibit(state))

    def test_residual_voltage_only_is_not_ready(self) -> None:
        v_residual = residual_voltage()
        self.assertAlmostEqual(v_residual, 11.988001, places=5)
        self.assertGreater(v_residual, MUX_UV_EXAMPLE_V)
        state = fully_qualified_state(
            boost_input_voltage_v=v_residual,
            load_test_pass=False,
        )
        self.assertFalse(backup_ready(state))
        self.assertTrue(ov2_inhibit(state))

    def test_470a_status_only_can_false_qualify_output_short_case(self) -> None:
        # TPS259470x AUXOFF stays high for load-side faults. The datasheet's
        # output-short row also lists FLT high. Thus AUXOFF && FLT_N is not
        # a load-capability proof. This is a status-only counterexample.
        auxoff_high = True
        flt_pin_high = True
        voltage_only_valid = residual_voltage() > MUX_UV_EXAMPLE_V
        legacy_status_only_ready = auxoff_high and flt_pin_high and voltage_only_valid
        self.assertTrue(legacy_status_only_ready)
        self.assertFalse(
            backup_ready(fully_qualified_state(load_test_pass=False))
        )

    def test_474l_pg_threshold_can_be_satisfied_by_residual_out(self) -> None:
        # PGTH is derived from OUT. With an illustrative 10% divider, a
        # charged 11.988V output still exceeds the typical 1.09V falling
        # threshold even though the upstream source path is assumed open.
        v_out = residual_voltage()
        pgth_ratio = 0.10
        pgth_v = v_out * pgth_ratio
        pg_high_in_voltage_only_model = pgth_v > 1.09
        self.assertTrue(pg_high_in_voltage_only_model)
        self.assertFalse(
            backup_ready(fully_qualified_state(load_test_pass=False))
        )

    def test_proof_load_separates_live_path_from_residual_cap_100uf(self) -> None:
        result = diagnostic_load_test(
            input_v=12.0,
            output_v_initial=residual_voltage(),
            output_cap_f=100e-6,
        )
        self.assertTrue(result["healthy_pass"])
        self.assertFalse(result["isolated_pass"])
        self.assertGreater(result["healthy_vout"], result["isolated_vout"])

    def test_proof_load_separates_live_path_from_residual_cap_470uf(self) -> None:
        result = diagnostic_load_test(
            input_v=12.0,
            output_v_initial=residual_voltage(),
            output_cap_f=470e-6,
        )
        self.assertTrue(result["healthy_pass"])
        self.assertFalse(result["isolated_pass"])
        self.assertGreater(result["isolated_drop"], MAX_PROOF_PATH_DROP_V)

    def test_pack_uv_revokes_ready_even_if_output_is_still_high(self) -> None:
        self.assertFalse(backup_ready(fully_qualified_state(pack_uv_ok=False)))

    def test_invalid_cell_monitor_revokes_ready(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(cell_protect_valid=False))
        )

    def test_discharge_arm_revocation_revokes_ready(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(discharge_armed=False))
        )

    def test_fault_latch_blocks_automatic_requalification(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(fault_latched=True))
        )

    def test_stale_load_test_revokes_ready(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(load_test_fresh=False))
        )

    def test_startup_timeout_blocks_ready(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(startup_timeout=True))
        )

    def test_boost_voltage_outside_window_blocks_ready(self) -> None:
        self.assertFalse(
            backup_ready(fully_qualified_state(boost_input_voltage_v=10.7))
        )
        self.assertFalse(
            backup_ready(fully_qualified_state(boost_input_voltage_v=13.0))
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
