#!/usr/bin/env python3
import math
import unittest

from model import (
    ScanConfig, PermitInputs, ArmLatch,
    adscan_period_ms, alert_routes_cuv,
    cell_input_filter_settle_ms, pmos_gate_turnoff_ms,
    total_estimated_isolation_ms, legacy_4p06_reproduction_ms,
    cow_open_wire_estimate_ms, build_scan_scenarios,
)


class ScanTimingTests(unittest.TestCase):
    def test_legacy_4p06_arithmetic_reproduced(self):
        self.assertAlmostEqual(legacy_4p06_reproduction_ms(), 4.06, places=9)

    def test_four_cell_normal_ads_scan_has_five_slots(self):
        cfg = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366,
                         cow_enabled=False, use_lfo_characterized_slow_drift=False)
        self.assertAlmostEqual(adscan_period_ms(cfg), 5 * 366 / 1000, places=9)

    def test_fast_with_cow_delay_candidate_estimate_under_five(self):
        cfg = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366,
                         cow_enabled=True, cow_delay_ms=1.0)
        self.assertLess(total_estimated_isolation_ms(cfg), 5.0)

    def test_medium_fast_near_zero_gate_estimate_fails_five_ms(self):
        cfg = ScanConfig(cv_slot_us_typ=732, shared_slot_us_typ=732,
                         cow_enabled=False)
        self.assertGreater(total_estimated_isolation_ms(cfg), 5.0)

    def test_half_loop_fast_with_cow_delay_fails(self):
        cfg = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366,
                         loop_slow=1, cow_enabled=True, cow_delay_ms=1.0)
        self.assertGreater(total_estimated_isolation_ms(cfg), 5.0)

    def test_default_slow_scan_fails(self):
        cfg = ScanConfig(cv_slot_us_typ=2930, shared_slot_us_typ=2930,
                         cow_enabled=False)
        self.assertGreater(adscan_period_ms(cfg), 14.0)

    def test_input_filter_is_small_but_not_zero(self):
        value = cell_input_filter_settle_ms()
        self.assertGreater(value, 0.02)
        self.assertLess(value, 0.03)

    def test_existing_pmos_near_zero_gate_estimate_exceeds_legacy_400us(self):
        self.assertGreater(pmos_gate_turnoff_ms(), 1.0)
        self.assertLess(pmos_gate_turnoff_ms(), 1.5)
        self.assertGreater(pmos_gate_turnoff_ms(vgs_target_abs_v=1.2), 0.5)

    def test_cuv_alert_not_routed_by_default_mask(self):
        self.assertFalse(alert_routes_cuv(0xC200))

    def test_cuv_alert_routed_by_candidate_mask(self):
        self.assertTrue(alert_routes_cuv(0xE205))

    def test_open_wire_diagnostic_not_a_five_ms_path(self):
        cfg = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366,
                         cow_enabled=True, cow_delay_ms=1.0)
        estimate = cow_open_wire_estimate_ms(cfg, cowntime_fullscans=1)
        self.assertIsNotNone(estimate)
        self.assertGreater(estimate, 500.0)

    def test_cow_zero_disables_open_wire_check(self):
        cfg = ScanConfig(cow_enabled=False)
        self.assertIsNone(cow_open_wire_estimate_ms(cfg, cowntime_fullscans=0))

    def test_scenarios_include_legacy_and_fail_cases(self):
        names = {r["scenario"] for r in build_scan_scenarios()}
        self.assertIn("legacy_4p06_reproduction", names)
        self.assertIn("fast_half_loop_cow_delay_1ms", names)
        self.assertIn("medium_fast_no_cow_delay", names)


class CellPermitTests(unittest.TestCase):
    def test_all_healthy_inputs_permit(self):
        self.assertTrue(PermitInputs().cell_permit)

    def test_each_fault_input_fails_closed(self):
        fault_fields = [
            "monitor_pg", "config_valid", "heartbeat_ok", "alert_line_ok",
            "alert_high", "open_wire_ok", "cell_uv_ok", "cell_ov_ok",
            "comm_ok", "vref_ok", "por_clear",
        ]
        for field in fault_fields:
            with self.subTest(field=field):
                self.assertFalse(PermitInputs(**{field: False}).cell_permit)

    def test_uv_fault_asynchronously_clears_arm_latch(self):
        latch = ArmLatch()
        self.assertTrue(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(cell_uv_ok=False), manual_arm_req=True))
        self.assertTrue(latch.fault_latched)

    def test_fault_clear_does_not_auto_rearm_while_arm_held_high(self):
        latch = ArmLatch()
        self.assertTrue(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(cell_uv_ok=False), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.armed)

    def test_low_then_high_is_required_to_rearm(self):
        latch = ArmLatch()
        self.assertTrue(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(cell_uv_ok=False), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.update(PermitInputs(), manual_arm_req=False))
        self.assertTrue(latch.update(PermitInputs(), manual_arm_req=True))
        self.assertFalse(latch.fault_latched)

    def test_alert_stuck_high_requires_line_health_input(self):
        # ALERT high by itself is not a fault; a separate line-health monitor
        # must identify stuck-high/open wiring and veto CELL_PERMIT.
        self.assertTrue(PermitInputs(alert_high=True).cell_permit)
        self.assertFalse(PermitInputs(alert_high=True, alert_line_ok=False).cell_permit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
