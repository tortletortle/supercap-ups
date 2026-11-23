import unittest
from efuse_variant_model import (
    BackupReadyLatch, ILIM_1650_MAX_A, ILIM_1650_MIN_A, ILIM_1650_TYP_A,
    PG_DEGLITCH_TYP_US, PG_FALL_MAX_V, PG_FALL_MIN_V,
    PG_RISE_MAX_V, PG_RISE_MIN_V, backup_ready_qualified,
    internal_latch_474l, pg_corner_state,
)

GOOD = dict(pack_uv_ok=True, cell_protect_valid=True,
            boost_input_window_ok=True, boost_output_window_ok=True,
            efuse_power_valid=True, pg_valid=True)

class EfuseVariantTests(unittest.TestCase):
    def test_pg_requires_inrush_and_full_path(self):
        self.assertFalse(pg_corner_state(1.30, previous_pg=False, inrush_complete=False))
        self.assertFalse(pg_corner_state(1.30, previous_pg=False, path_fully_on=False))

    def test_pg_rising_threshold_tolerance_band(self):
        self.assertFalse(pg_corner_state(PG_RISE_MIN_V, previous_pg=False))
        self.assertIsNone(pg_corner_state(1.20, previous_pg=False))
        self.assertTrue(pg_corner_state(PG_RISE_MAX_V + 0.001, previous_pg=False))

    def test_pg_falling_threshold_tolerance_band(self):
        self.assertFalse(pg_corner_state(PG_FALL_MIN_V - 0.001, previous_pg=True))
        self.assertIsNone(pg_corner_state(1.09, previous_pg=True))
        self.assertTrue(pg_corner_state(PG_FALL_MAX_V, previous_pg=True))

    def test_non_overcurrent_fault_deasserts_pg(self):
        self.assertFalse(pg_corner_state(1.30, previous_pg=True, non_overcurrent_fault=True))

    def test_output_short_pg_can_remain_high_while_cout_is_charged(self):
        self.assertTrue(pg_corner_state(1.30, previous_pg=True))
        self.assertFalse(pg_corner_state(1.05, previous_pg=True))

    def test_474l_persistent_overload_latches_but_short_does_not(self):
        self.assertTrue(internal_latch_474l("persistent_overload"))
        self.assertTrue(internal_latch_474l("overtemperature"))
        self.assertFalse(internal_latch_474l("output_short_circuit"))

    def test_1650_ohm_rilm_range(self):
        self.assertEqual((ILIM_1650_MIN_A, ILIM_1650_TYP_A, ILIM_1650_MAX_A),
                         (1.8, 2.028, 2.2))
        self.assertGreater(ILIM_1650_MIN_A, 1.0)
        self.assertGreater(ILIM_1650_MAX_A, ILIM_1650_TYP_A)
        self.assertGreater(PG_DEGLITCH_TYP_US, 0)
        self.assertLess(PG_RISE_MIN_V, PG_RISE_MAX_V)
        self.assertLess(PG_FALL_MIN_V, PG_FALL_MAX_V)

    def test_all_ready_qualifiers_are_mandatory(self):
        self.assertTrue(backup_ready_qualified(arm_latched=True, **GOOD))
        for key in GOOD:
            bad = dict(GOOD)
            bad[key] = False
            self.assertFalse(backup_ready_qualified(arm_latched=True, **bad))

    def test_ready_loss_latches_until_arm_low_then_high(self):
        latch = BackupReadyLatch()
        self.assertTrue(latch.update(arm_request=True, **GOOD))
        bad = dict(GOOD)
        bad["pg_valid"] = False
        self.assertFalse(latch.update(arm_request=True, **bad))
        self.assertTrue(latch.fault_latched)
        self.assertFalse(latch.update(arm_request=True, **GOOD))
        self.assertFalse(latch.update(arm_request=False, **GOOD))
        self.assertFalse(latch.fault_latched)
        self.assertTrue(latch.update(arm_request=True, **GOOD))

if __name__ == "__main__":
    unittest.main()
